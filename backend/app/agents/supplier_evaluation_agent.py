"""Supplier Evaluation Agent — compares alternative suppliers for affected products."""
from __future__ import annotations

from ..core.metrics import AGENT_DURATION, AGENT_RUNS
from ..services.supplier_eval import evaluate_alternatives
from ..models import Product, Supplier
from .common import with_retries


@with_retries()
def supplier_evaluation_node(state: dict, db) -> dict:
    with AGENT_DURATION.labels(agent="supplier_evaluation").time():
        affected = state.get("affected_product_ids", [])
        exclude = state.get("supplier_id")  # the disrupted supplier

        alternatives: list[dict] = []
        scores: list[dict] = []
        for pid in affected:
            product = db.get(Product, pid) if hasattr(db, "get") else db.query(Product).get(pid)
            # required quantity: shortfall if known, else a nominal reorder qty
            gap_rows = state.get("inventory_gap", [])
            shortfall = next((g["shortfall"] for g in gap_rows
                              if g["product_id"] == pid and g["shortfall"] > 0), 200.0)
            qty = max(shortfall, 100.0)
            alts = evaluate_alternatives(db, pid, qty, exclude_supplier_id=exclude)
            # fill delay_vs_original vs original supplier baseline
            original_supplier_id = exclude
            if original_supplier_id:
                orig = db.get(Supplier, original_supplier_id) if hasattr(db, "get") else db.query(Supplier).get(original_supplier_id)
                if orig:
                    for a in alts:
                        a["delay_vs_original"] = round(a["delivery_days"] - (orig.avg_lead_time_days + 6), 1)
            alternatives.extend(alts[:5])
            scores.extend([{"product_id": pid, "supplier_id": a["supplier_id"],
                            "supplier_name": a["supplier_name"], "score": a["score"],
                            "total_cost": a["total_cost"], "delivery_days": a["delivery_days"]}
                           for a in alts[:3]])

        AGENT_RUNS.labels(agent="supplier_evaluation", status="ok").inc()
        return {
            "alternative_suppliers": alternatives,
            "supplier_scores": scores,
            "status": "supplier_evaluation_complete",
        }
