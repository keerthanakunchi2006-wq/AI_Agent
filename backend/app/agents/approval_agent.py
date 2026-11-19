"""Approval Agent — routes consequential recovery plans to human approval."""
from __future__ import annotations

from ..core.metrics import AGENT_DURATION, AGENT_RUNS, APPROVALS
from ..services.approval import needs_approval, request_approval
from ..models import Disruption, DisruptionStatus, RecoveryPlan
from .common import with_retries


@with_retries()
def approval_node(state: dict, db) -> dict:
    with AGENT_DURATION.labels(agent="approval").time():
        plan_id = state.get("optimized_plan_id")
        if not plan_id or not state.get("request_approval", True):
            AGENT_RUNS.labels(agent="approval", status="skipped").inc()
            return {"approval_required": False, "approval_status": "not_required",
                    "status": "approval_skipped"}

        plan = db.get(RecoveryPlan, plan_id) if hasattr(db, "get") else db.query(RecoveryPlan).get(plan_id)
        if not plan:
            raise ValueError(f"Recovery plan {plan_id} not found")

        required, reason = needs_approval(plan.total_cost, plan.total_delay_days)
        if not required:
            # auto-approve small/routine plans
            plan.status = "auto_approved"
            disruption = db.query(Disruption).filter(Disruption.id == plan.disruption_id).first()
            if disruption:
                disruption.status = DisruptionStatus.approved
            db.commit()
            AGENT_RUNS.labels(agent="approval", status="auto").inc()
            APPROVALS.labels(outcome="auto_approved").inc()
            return {"approval_required": False, "approval_status": "auto_approved",
                    "approval_reason": "below thresholds",
                    "status": "approval_auto"}

        req = request_approval(db, plan, requester="optimization_agent")
        disruption = db.query(Disruption).filter(Disruption.id == plan.disruption_id).first()
        if disruption:
            disruption.status = DisruptionStatus.pending_approval
            db.commit()

        AGENT_RUNS.labels(agent="approval", status="pending").inc()
        APPROVALS.labels(outcome="requested").inc()
        return {
            "approval_required": True,
            "approval_reason": reason,
            "approval_request_id": req.id,
            "approval_status": "pending",
            "status": "approval_pending",
        }
