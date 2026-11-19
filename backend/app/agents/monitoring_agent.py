"""Monitoring Agent — detects supplier delays and at-risk suppliers."""
from __future__ import annotations

from ..core.metrics import AGENT_DURATION, AGENT_RUNS
from ..services.monitoring import detect_delays, identify_at_risk_suppliers
from ..models import Disruption, DisruptionStatus
from .common import with_retries
from datetime import datetime


@with_retries()
def monitoring_node(state: dict, db) -> dict:
    with AGENT_DURATION.labels(agent="monitoring").time():
        delays = detect_delays(db)
        at_risk = identify_at_risk_suppliers(db)

        # enrich: link delays to the active disruption when present
        disruption_id = state.get("disruption_id")
        if disruption_id and state.get("disruption_type") == "supplier_delay":
            disruption = db.get(Disruption, disruption_id) if hasattr(db, "get") else db.query(Disruption).get(disruption_id)
            if disruption:
                # if linked to a PO, surface that specific delay first
                if disruption.po_id:
                    matched = [d for d in delays if d["po_id"] == disruption.po_id]
                    if matched:
                        disruption.estimated_delay_days = matched[0]["days_late"]
                        db.commit()

        AGENT_RUNS.labels(agent="monitoring", status="ok").inc()
        return {
            "delays": delays,
            "at_risk_suppliers": at_risk,
            "status": "monitoring_complete",
        }
