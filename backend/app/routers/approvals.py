"""Human approval interface for consequential purchase changes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import User, UserRole, ApprovalRequest, ApprovalStatus, RecoveryPlan
from ..schemas import ApprovalRequestOut, ApprovalDecisionIn, RecoveryPlanOut
from ..services.approval import decide_approval

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalRequestOut], summary="List approval requests")
def list_approvals(status: Optional[str] = None, skip: int = 0,
                   limit: int = Query(100, le=500),
                   db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(ApprovalRequest)
    if status:
        q = q.filter(ApprovalRequest.status == ApprovalStatus(status))
    return q.order_by(ApprovalRequest.requested_at.desc()).offset(skip).limit(limit).all()


@router.get("/pending", response_model=list[ApprovalRequestOut],
            summary="List pending approvals")
def list_pending(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(ApprovalRequest).filter(
        ApprovalRequest.status == ApprovalStatus.pending
    ).order_by(ApprovalRequest.requested_at.desc()).all()


@router.get("/{approval_id}", response_model=ApprovalRequestOut)
def get_approval(approval_id: int, db: Session = Depends(get_db),
                 _=Depends(get_current_user)):
    a = db.get(ApprovalRequest, approval_id) if hasattr(db, "get") else db.query(ApprovalRequest).get(approval_id)
    if not a:
        raise HTTPException(404, "Approval request not found")
    return a


@router.get("/{approval_id}/plan", response_model=RecoveryPlanOut,
            summary="Get the recovery plan linked to an approval")
def get_approval_plan(approval_id: int, db: Session = Depends(get_db),
                      _=Depends(get_current_user)):
    a = db.get(ApprovalRequest, approval_id) if hasattr(db, "get") else db.query(ApprovalRequest).get(approval_id)
    if not a:
        raise HTTPException(404, "Approval request not found")
    plan = db.get(RecoveryPlan, a.recovery_plan_id) if hasattr(db, "get") else db.query(RecoveryPlan).get(a.recovery_plan_id)
    if not plan:
        raise HTTPException(404, "Recovery plan not found")
    return plan


@router.post("/{approval_id}/decide", response_model=ApprovalRequestOut,
             summary="Approve or reject a request (approver/admin only)")
def decide(approval_id: int, payload: ApprovalDecisionIn,
           db: Session = Depends(get_db),
           user: User = Depends(require_roles(UserRole.approver, UserRole.admin))):
    try:
        return decide_approval(db, approval_id, payload.status,
                               payload.decided_by or user.username,
                               payload.decision_note)
    except ValueError as e:
        raise HTTPException(400, str(e))
