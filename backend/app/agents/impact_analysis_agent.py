"""Impact Analysis Agent — maps a disruption to affected products/orders/inventory."""
from __future__ import annotations

from ..core.metrics import AGENT_DURATION, AGENT_RUNS
from ..services.impact_analysis import analyze_impact
from ..models import Disruption, DisruptionStatus
from .common import with_retries


@with_retries()
def impact_analysis_node(state: dict, db) -> dict:
    with AGENT_DURATION.labels(agent="impact_analysis").time():
        disruption_id = state.get("disruption_id")
        disruption = db.get(Disruption, disruption_id) if hasattr(db, "get") else db.query(Disruption).get(disruption_id)
        if not disruption:
            raise ValueError(f"Disruption {disruption_id} not found")

        disruption.status = DisruptionStatus.analyzing
        db.commit()

        result = analyze_impact(db, disruption)

        # persist summary fields on the disruption
        disruption.affected_order_count = result["affected_order_count"]
        disruption.affected_product_count = result["affected_product_count"]
        db.commit()

        AGENT_RUNS.labels(agent="impact_analysis", status="ok").inc()
        return {
            "affected_product_ids": result["affected_product_ids"],
            "affected_po_ids": result["affected_po_ids"],
            "affected_order_count": result["affected_order_count"],
            "affected_product_count": result["affected_product_count"],
            "committed_quantity": result["committed_quantity"],
            "at_risk_value": result["at_risk_value"],
            "inventory_gap": result["inventory_gap"],
            "total_shortfall": result["total_shortfall"],
            "status": "impact_analysis_complete",
        }
