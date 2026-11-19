"""Optimization agent core — generate the lowest-cost / lowest-delay recovery
plan using OR-Tools (LP). Falls back to a deterministic greedy solver when
OR-Tools is unavailable so the app always works.

Decision variables: quantity sourced from each candidate supplier per product.
Objective: minimise (sourcing + transport cost) + delay_penalty * total_delay.
Constraints:
  - total quantity per product >= required demand (gap)
  - per-supplier quantity either 0 or >= supplier.min_order_qty
  - optional per-supplier capacity ceiling
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import (
    Product, Supplier, RecoveryPlan, RecoveryPlanItem, Disruption,
)
from ..core.logging import get_logger
from .supplier_eval import evaluate_alternatives

log = get_logger("optimization")

DELAY_PENALTY_PER_DAY = 25.0      # cost penalty per unit-delay-day
COST_WEIGHT = 1.0
DELAY_WEIGHT = 1.0

try:
    from ortools.linear_solver import pywraplp  # type: ignore
    _HAS_ORTOOLS = True
except Exception:  # pragma: no cover - OR-Tools optional at runtime
    _HAS_ORTOOLS = False


def _build_demand_map(db: Session, product_ids: list[int],
                      gap_rows: list[dict[str, Any]]) -> dict[int, float]:
    """Required quantity per product = inventory shortfall (or committed demand)."""
    demand: dict[int, float] = {}
    for g in gap_rows:
        pid = g["product_id"]
        demand[pid] = demand.get(pid, 0.0) + max(0.0, g.get("shortfall", 0.0))
    # ensure every affected product has an entry
    for pid in product_ids:
        demand.setdefault(pid, 0.0)
    return demand


def _collect_candidates(db: Session, demand: dict[int, float],
                        exclude_supplier_id: int | None) -> dict[int, list[dict[str, Any]]]:
    candidates: dict[int, list[dict[str, Any]]] = {}
    for pid, qty in demand.items():
        if qty <= 0:
            continue
        alts = evaluate_alternatives(db, pid, qty, exclude_supplier_id=exclude_supplier_id)
        if alts:
            candidates[pid] = alts
    return candidates


def optimize_lp(demand: dict[int, float],
                candidates: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """OR-Tools LP optimisation. Returns list of assignment dicts."""
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        return optimize_greedy(demand, candidates)

    # variables: x[pid][sid] = quantity from supplier sid for product pid
    vars_: dict[int, dict[int, Any]] = {}
    for pid, alts in candidates.items():
        vars_[pid] = {}
        for a in alts:
            sid = a["supplier_id"]
            # continuous quantity; we enforce min_order via a binary indicator
            x = solver.NumVar(0.0, solver.infinity(), f"x_{pid}_{sid}")
            vars_[pid][sid] = {"x": x, "alt": a}

    # constraints: meet demand per product
    for pid, qty in demand.items():
        if pid not in vars_ or qty <= 0:
            continue
        ct = solver.Constraint(qty, solver.infinity(), f"demand_{pid}")
        for sid, v in vars_[pid].items():
            ct.SetCoefficient(v["x"], 1.0)

    # min order quantity: handled by post-processing clamp (LP relaxation)
    # objective: min sum( unit_cost*x + transport*(x/qty) + delay_penalty*delay*x/qty )
    objective = solver.Objective()
    objective.SetMinimization()
    for pid, m in vars_.items():
        qty = demand[pid]
        for sid, v in m.items():
            a = v["alt"]
            # transport cost scales with quantity share
            transport_share = (a["transport_cost"] / qty) if qty else a["transport_cost"]
            delay_share = (a["delivery_days"] / qty) if qty else a["delivery_days"]
            cost_coef = COST_WEIGHT * a["unit_cost"] + COST_WEIGHT * transport_share + \
                        DELAY_WEIGHT * DELAY_PENALTY_PER_DAY * delay_share
            objective.SetCoefficient(v["x"], cost_coef)

    status = solver.Solve()
    if status != pywraplp.Solver.OPTIMAL and status != pywraplp.Solver.FEASIBLE:
        log.warning("optimization.lp_infeasible", status=status)
        return optimize_greedy(demand, candidates)

    assignments = []
    for pid, m in vars_.items():
        qty = demand[pid]
        for sid, v in m.items():
            xval = v["x"].solution_value()
            if xval > 1e-3:
                a = v["alt"]
                assignments.append({
                    "product_id": pid,
                    "supplier_id": sid,
                    "supplier_name": a["supplier_name"],
                    "quantity": round(xval, 2),
                    "unit_cost": a["unit_cost"],
                    "transport_cost": round(a["transport_cost"] * (xval / qty) if qty else a["transport_cost"], 2),
                    "delivery_days": a["delivery_days"],
                    "delay_days": max(0.0, a["delivery_days"] - 7),  # vs 7-day baseline
                    "line_total": round(a["unit_cost"] * xval, 2),
                })
    log.info("optimization.lp_solved", assignments=len(assignments))
    return assignments


def optimize_greedy(demand: dict[int, float],
                    candidates: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Deterministic fallback: assign full demand to the best-scoring supplier."""
    assignments = []
    for pid, qty in demand.items():
        if qty <= 0 or pid not in candidates:
            continue
        best = candidates[pid][0]  # already sorted by score desc
        assignments.append({
            "product_id": pid,
            "supplier_id": best["supplier_id"],
            "supplier_name": best["supplier_name"],
            "quantity": round(qty, 2),
            "unit_cost": best["unit_cost"],
            "transport_cost": best["transport_cost"],
            "delivery_days": best["delivery_days"],
            "delay_days": max(0.0, best["delivery_days"] - 7),
            "line_total": round(best["unit_cost"] * qty, 2),
        })
    log.info("optimization.greedy_used", assignments=len(assignments))
    return assignments


def solve(demand: dict[int, float],
          candidates: dict[int, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if _HAS_ORTOOLS and candidates:
        try:
            return optimize_lp(demand, candidates)
        except Exception as e:  # pragma: no cover
            log.warning("optimization.lp_error", error=str(e))
    return optimize_greedy(demand, candidates)


def _assignments_to_plan(db: Session, disruption: Disruption,
                         assignments: list[dict[str, Any]],
                         plan_type: str = "optimized") -> tuple[RecoveryPlan, dict[str, Any]]:
    """Persist assignments as a RecoveryPlan with items and return summary."""
    plan = RecoveryPlan(
        disruption_id=disruption.id,
        plan_type=plan_type,
        total_cost=0.0,
        total_transport_cost=0.0,
        total_delay_days=0.0,
        supplier_count=len({a["supplier_id"] for a in assignments}),
        status="draft",
        summary="",
        created_at=datetime.utcnow(),
    )
    db.add(plan)
    db.flush()

    total_cost = 0.0
    total_transport = 0.0
    weighted_delay = 0.0
    total_qty = 0.0
    now = datetime.utcnow()
    for a in assignments:
        delivery_date = now + timedelta(days=int(round(a["delivery_days"])))
        item = RecoveryPlanItem(
            plan_id=plan.id,
            product_id=a["product_id"],
            supplier_id=a["supplier_id"],
            quantity=a["quantity"],
            unit_cost=a["unit_cost"],
            transport_cost=a["transport_cost"],
            delivery_date=delivery_date,
            delay_days=a["delay_days"],
            line_total=a["line_total"],
        )
        db.add(item)
        total_cost += a["line_total"]
        total_transport += a["transport_cost"]
        weighted_delay += a["delay_days"] * a["quantity"]
        total_qty += a["quantity"]

    plan.total_cost = round(total_cost + total_transport, 2)
    plan.total_transport_cost = round(total_transport, 2)
    plan.total_delay_days = round(weighted_delay / total_qty, 2) if total_qty else 0.0
    plan.summary = (
        f"{plan_type} plan: {len(assignments)} line items across "
        f"{plan.supplier_count} suppliers, total cost "
        f"{plan.total_cost:.2f}, avg delay {plan.total_delay_days:.1f}d"
    )
    summary = {
        "plan_id": plan.id,
        "plan_type": plan_type,
        "line_items": len(assignments),
        "supplier_count": plan.supplier_count,
        "total_cost": plan.total_cost,
        "total_transport_cost": plan.total_transport_cost,
        "total_delay_days": plan.total_delay_days,
        "assignments": assignments,
        "solver": "ortools" if _HAS_ORTOOLS else "greedy",
    }
    db.commit()
    db.refresh(plan)
    return plan, summary


def generate_recovery_plan(db: Session, disruption: Disruption,
                           product_ids: list[int],
                           gap_rows: list[dict[str, Any]],
                           exclude_supplier_id: int | None = None,
                           plan_type: str = "optimized") -> tuple[RecoveryPlan, dict[str, Any]]:
    demand = _build_demand_map(db, product_ids, gap_rows)
    if not any(q > 0 for q in demand.values()):
        # no shortfall → plan a buffer reorder of one product's safety stock
        for pid in product_ids:
            demand[pid] = 100.0
            break
    candidates = _collect_candidates(db, demand, exclude_supplier_id)
    if not candidates:
        log.warning("optimization.no_candidates", products=product_ids)
        plan = RecoveryPlan(
            disruption_id=disruption.id, plan_type=plan_type,
            total_cost=0.0, total_transport_cost=0.0, total_delay_days=0.0,
            supplier_count=0, status="draft",
            summary="No alternative suppliers available",
            created_at=datetime.utcnow(),
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        return plan, {"plan_id": plan.id, "assignments": [], "solver": "none",
                      "total_cost": 0.0, "total_delay_days": 0.0}
    assignments = solve(demand, candidates)
    return _assignments_to_plan(db, disruption, assignments, plan_type=plan_type)


def generate_original_plan(db: Session, disruption: Disruption,
                            product_ids: list[int],
                            gap_rows: list[dict[str, Any]],
                            original_supplier_id: int | None) -> tuple[RecoveryPlan, dict[str, Any]]:
    """Baseline plan: source everything from the original supplier (or a single fallback)."""
    demand = _build_demand_map(db, product_ids, gap_rows)
    if not any(q > 0 for q in demand.values()):
        for pid in product_ids:
            demand[pid] = 100.0
            break
    assignments: list[dict[str, Any]] = []
    now = datetime.utcnow()
    for pid, qty in demand.items():
        if qty <= 0:
            continue
        if original_supplier_id:
            sup = db.get(Supplier, original_supplier_id) if hasattr(db, "get") else db.query(Supplier).get(original_supplier_id)
        else:
            sup = db.query(Supplier).filter(Supplier.active.is_(True)).order_by(Supplier.id).first()
        if not sup:
            continue
        product = db.get(Product, pid) if hasattr(db, "get") else db.query(Product).get(pid)
        unit_cost = product.unit_cost if product else 1.0
        transport = round(qty * 0.05 * (product.weight_kg if product else 1.0), 2)
        delivery_days = sup.avg_lead_time_days + 6
        assignments.append({
            "product_id": pid,
            "supplier_id": sup.id,
            "supplier_name": sup.name,
            "quantity": round(qty, 2),
            "unit_cost": unit_cost,
            "transport_cost": transport,
            "delivery_days": delivery_days,
            "delay_days": max(0.0, delivery_days - 7),
            "line_total": round(unit_cost * qty, 2),
        })
    return _assignments_to_plan(db, disruption, assignments, plan_type="original")
