"""Tracking Agent — records decisions and recovery progress for audit."""
from __future__ import annotations

from ..core.metrics import AGENT_DURATION, AGENT_RUNS
from ..services.tracking import record_decision
from .common import with_retries


@with_retries()
def tracking_node(state: dict, db) -> dict:
    with AGENT_DURATION.labels(agent="tracking").time():
        records: list[dict] = []
        disruption_id = state.get("disruption_id")
        opt_plan = state.get("optimized_plan_id")

        # record the run outcome
        if disruption_id:
            rec = record_decision(
                db, entity_type="disruption", entity_id=disruption_id,
                action="recovery_workflow_completed",
                actor="langgraph_orchestrator",
                details=state.get("summary", f"Disruption {disruption_id} processed"),
            )
            records.append({
                "id": rec.id, "entity_type": rec.entity_type, "entity_id": rec.entity_id,
                "action": rec.action, "actor": rec.actor, "timestamp": rec.timestamp.isoformat(),
            })

        recovery_status = "pending_approval" if state.get("approval_required") else "approved"
        AGENT_RUNS.labels(agent="tracking", status="ok").inc()
        return {
            "decision_records": records,
            "recovery_status": recovery_status,
            "status": "tracking_complete",
        }
