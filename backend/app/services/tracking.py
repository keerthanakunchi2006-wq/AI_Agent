"""Tracking service — records approved decisions and recovery progress."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import (
    DecisionHistory, RecoveryPlan, Disruption, DisruptionStatus,
)
from ..core.logging import get_logger

log = get_logger("tracking")


def record_decision(db: Session, entity_type: str, entity_id: int,
                    action: str, actor: str = "system", details: str = "") -> DecisionHistory:
    rec = DecisionHistory(
        entity_type=entity_type, entity_id=entity_id, action=action,
        actor=actor, details=details, timestamp=datetime.utcnow(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def update_recovery_progress(db: Session, recovery_plan_id: int,
                              progress: str, actor: str = "system") -> RecoveryPlan:
    plan = db.get(RecoveryPlan, recovery_plan_id) if hasattr(db, "get") else db.query(RecoveryPlan).get(recovery_plan_id)
    if not plan:
        raise ValueError(f"Recovery plan {recovery_plan_id} not found")
    plan.status = progress
    db.add(DecisionHistory(
        entity_type="recovery_plan", entity_id=recovery_plan_id,
        action=f"progress_{progress}", actor=actor,
        details=f"Recovery plan {recovery_plan_id} moved to {progress}",
    ))
    db.commit()
    db.refresh(plan)
    log.info("tracking.progress", plan=recovery_plan_id, status=progress)
    return plan


def complete_recovery(db: Session, recovery_plan_id: int,
                      actor: str = "system") -> tuple[RecoveryPlan, Disruption]:
    plan = update_recovery_progress(db, recovery_plan_id, "completed", actor)
    disruption = db.query(Disruption).filter(Disruption.id == plan.disruption_id).first()
    if disruption:
        disruption.status = DisruptionStatus.resolved
        disruption.resolved_at = datetime.utcnow()
        db.add(DecisionHistory(
            entity_type="disruption", entity_id=disruption.id,
            action="disruption_resolved", actor=actor,
            details=f"Disruption {disruption.id} resolved after recovery plan {recovery_plan_id}",
        ))
        db.commit()
        db.refresh(disruption)
    return plan, disruption


def decision_history(db: Session, entity_type: str | None = None,
                     entity_id: int | None = None, limit: int = 100) -> list[DecisionHistory]:
    q = db.query(DecisionHistory)
    if entity_type:
        q = q.filter(DecisionHistory.entity_type == entity_type)
    if entity_id:
        q = q.filter(DecisionHistory.entity_id == entity_id)
    return q.order_by(DecisionHistory.timestamp.desc()).limit(limit).all()
