"""Approval service — human-in-the-loop for consequential purchase changes.

A recovery plan that exceeds a cost/delay threshold produces an
ApprovalRequest that must be signed off before the plan is enacted.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import (
    ApprovalRequest, ApprovalStatus, RecoveryPlan, DisruptionStatus,
    Disruption, DecisionHistory,
)
from ..config import settings
from ..core.logging import get_logger

log = get_logger("approval")


def needs_approval(total_cost: float, total_delay_days: float) -> tuple[bool, str]:
    if total_cost > settings.APPROVAL_COST_THRESHOLD:
        return True, f"cost {total_cost:.2f} > threshold {settings.APPROVAL_COST_THRESHOLD}"
    if total_delay_days > settings.APPROVAL_DELAY_THRESHOLD_DAYS:
        return True, f"delay {total_delay_days:.1f}d > threshold {settings.APPROVAL_DELAY_THRESHOLD_DAYS}d"
    return False, ""


def request_approval(db: Session, plan: RecoveryPlan,
                     requester: str = "system") -> ApprovalRequest:
    req = ApprovalRequest(
        recovery_plan_id=plan.id,
        requester=requester,
        status=ApprovalStatus.pending,
        requested_at=datetime.utcnow(),
        total_cost=plan.total_cost,
        total_delay_days=plan.total_delay_days,
    )
    db.add(req)
    plan.status = "pending_approval"
    db.add(DecisionHistory(
        entity_type="recovery_plan", entity_id=plan.id,
        action="approval_requested", actor=requester,
        details=f"Plan {plan.id}: cost {plan.total_cost:.2f}, delay {plan.total_delay_days:.1f}d",
    ))
    db.commit()
    db.refresh(req)
    log.info("approval.requested", plan=plan.id, cost=plan.total_cost, delay=plan.total_delay_days)
    return req


def decide_approval(db: Session, approval_id: int, status: str,
                    decided_by: str, decision_note: str = "") -> ApprovalRequest:
    req = db.get(ApprovalRequest, approval_id) if hasattr(db, "get") else db.query(ApprovalRequest).get(approval_id)
    if not req:
        raise ValueError(f"Approval request {approval_id} not found")
    if req.status != ApprovalStatus.pending:
        raise ValueError(f"Approval {approval_id} is already {req.status.value}")

    new_status = ApprovalStatus(status)
    req.status = new_status
    req.decided_at = datetime.utcnow()
    req.decided_by = decided_by
    req.decision_note = decision_note

    plan = db.get(RecoveryPlan, req.recovery_plan_id) if hasattr(db, "get") else db.query(RecoveryPlan).get(req.recovery_plan_id)
    if plan:
        plan.status = "approved" if new_status == ApprovalStatus.approved else "rejected"
        disruption = db.query(Disruption).filter(Disruption.id == plan.disruption_id).first()
        if disruption:
            if new_status == ApprovalStatus.approved:
                disruption.status = DisruptionStatus.approved
            else:
                disruption.status = DisruptionStatus.rejected

    db.add(DecisionHistory(
        entity_type="approval", entity_id=approval_id,
        action=f"approval_{new_status.value}", actor=decided_by,
        details=decision_note,
    ))
    db.commit()
    db.refresh(req)
    log.info("approval.decided", approval=approval_id, status=new_status.value, by=decided_by)
    return req


def list_pending(db: Session) -> list[ApprovalRequest]:
    return db.query(ApprovalRequest).filter(ApprovalRequest.status == ApprovalStatus.pending).all()
