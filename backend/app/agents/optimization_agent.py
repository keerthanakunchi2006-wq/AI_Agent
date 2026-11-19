"""Optimization Agent — builds the original (baseline) and optimized recovery
plans using OR-Tools, then compares them on total cost and delivery delay.
"""
from __future__ import annotations

from ..core.metrics import AGENT_DURATION, AGENT_RUNS
from ..services.optimization import generate_recovery_plan, generate_original_plan
from ..models import Disruption, DisruptionStatus
from .common import with_retries


@with_retries()
def optimization_node(state: dict, db) -> dict:
    with AGENT_DURATION.labels(agent="optimization").time():
        disruption_id = state.get("disruption_id")
        disruption = db.get(Disruption, disruption_id) if hasattr(db, "get") else db.query(Disruption).get(disruption_id)
        if not disruption:
            raise ValueError(f"Disruption {disruption_id} not found")

        affected = state.get("affected_product_ids", [])
        gap_rows = state.get("inventory_gap", [])
        exclude = state.get("supplier_id")

        # baseline: keep using the original supplier
        orig_plan, orig_summary = generate_original_plan(
            db, disruption, affected, gap_rows, original_supplier_id=exclude
        )
        # optimized: source from best-scored alternatives
        opt_plan, opt_summary = generate_recovery_plan(
            db, disruption, affected, gap_rows,
            exclude_supplier_id=exclude, plan_type="optimized"
        )

        comparison = {
            "original_plan_id": orig_plan.id,
            "optimized_plan_id": opt_plan.id,
            "original_total_cost": orig_plan.total_cost,
            "optimized_total_cost": opt_plan.total_cost,
            "original_delay_days": orig_plan.total_delay_days,
            "optimized_delay_days": opt_plan.total_delay_days,
            "cost_savings": round(max(0.0, orig_plan.total_cost - opt_plan.total_cost), 2),
            "delay_savings_days": round(max(0.0, orig_plan.total_delay_days - opt_plan.total_delay_days), 2),
            "original_supplier_count": orig_plan.supplier_count,
            "optimized_supplier_count": opt_plan.supplier_count,
            "solver": opt_summary.get("solver", "unknown"),
        }

        disruption.status = DisruptionStatus.planned
        db.commit()

        AGENT_RUNS.labels(agent="optimization", status="ok").inc()
        return {
            "original_plan_id": orig_plan.id,
            "optimized_plan_id": opt_plan.id,
            "original_plan_summary": orig_summary,
            "optimized_plan_summary": opt_summary,
            "plan_comparison": comparison,
            "status": "optimization_complete",
        }
