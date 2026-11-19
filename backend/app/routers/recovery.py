"""Recovery plans, plan comparison, alternative supplier comparison, tracking."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import RecoveryPlan, Disruption, Product
from ..schemas import RecoveryPlanOut, AlternativeSupplierOut, DecisionHistoryOut
from ..services.supplier_eval import evaluate_alternatives
from ..services.tracking import decision_history, update_recovery_progress, complete_recovery
from ..core.logging import get_logger

router = APIRouter(prefix="/recovery", tags=["recovery"])
log = get_logger("api.recovery")


@router.get("/plans", response_model=list[RecoveryPlanOut], summary="List recovery plans")
def list_plans(disruption_id: Optional[int] = None, plan_type: Optional[str] = None,
               skip: int = 0, limit: int = Query(100, le=500),
               db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(RecoveryPlan)
    if disruption_id:
        q = q.filter(RecoveryPlan.disruption_id == disruption_id)
    if plan_type:
        q = q.filter(RecoveryPlan.plan_type == plan_type)
    return q.order_by(RecoveryPlan.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/plans/{plan_id}", response_model=RecoveryPlanOut)
def get_plan(plan_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    plan = db.get(RecoveryPlan, plan_id) if hasattr(db, "get") else db.query(RecoveryPlan).get(plan_id)
    if not plan:
        raise HTTPException(404, "Recovery plan not found")
    return plan


@router.get("/plans/{plan_id}/compare", summary="Compare original vs optimized plan")
def compare_plans(plan_id: int, db: Session = Depends(get_db),
                  _=Depends(get_current_user)):
    plan = db.get(RecoveryPlan, plan_id) if hasattr(db, "get") else db.query(RecoveryPlan).get(plan_id)
    if not plan:
        raise HTTPException(404, "Recovery plan not found")
    # find the sibling original plan for the same disruption
    original = db.query(RecoveryPlan).filter(
        RecoveryPlan.disruption_id == plan.disruption_id,
        RecoveryPlan.plan_type == "original",
    ).first()
    return {
        "disruption_id": plan.disruption_id,
        "optimized": {
            "plan_id": plan.id, "total_cost": plan.total_cost,
            "transport_cost": plan.total_transport_cost,
            "delay_days": plan.total_delay_days, "suppliers": plan.supplier_count,
            "summary": plan.summary, "items": len(plan.items),
        },
        "original": {
            "plan_id": original.id if original else None,
            "total_cost": original.total_cost if original else 0.0,
            "transport_cost": original.total_transport_cost if original else 0.0,
            "delay_days": original.total_delay_days if original else 0.0,
            "suppliers": original.supplier_count if original else 0,
            "items": len(original.items) if original else 0,
        } if original else None,
        "cost_savings": (original.total_cost - plan.total_cost) if original else 0.0,
        "delay_savings_days": (original.total_delay_days - plan.total_delay_days) if original else 0.0,
    }


@router.get("/alternatives", response_model=list[AlternativeSupplierOut],
            summary="Compare alternative suppliers for a product")
def alternatives(product_id: int, quantity: float = 200.0,
                 exclude_supplier_id: Optional[int] = None,
                 db: Session = Depends(get_db), _=Depends(get_current_user)):
    product = db.get(Product, product_id) if hasattr(db, "get") else db.query(Product).get(product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    alts = evaluate_alternatives(db, product_id, quantity, exclude_supplier_id=exclude_supplier_id)
    return [
        AlternativeSupplierOut(
            supplier_id=a["supplier_id"], supplier_name=a["supplier_name"],
            country=a["country"], rating=a["rating"], on_time_rate=a["on_time_rate"],
            lead_time_days=a["lead_time_days"], unit_cost=a["unit_cost"],
            total_cost=a["total_cost"], transport_cost=a["transport_cost"],
            delivery_days=a["delivery_days"], delay_vs_original=a.get("delay_vs_original", 0.0),
            score=a["score"],
        )
        for a in alts
    ]


@router.post("/plans/{plan_id}/progress", response_model=RecoveryPlanOut,
             summary="Update recovery plan progress")
def progress(plan_id: int, status: str = "in_progress",
             db: Session = Depends(get_db), _=Depends(get_current_user)):
    plan = update_recovery_progress(db, plan_id, status, actor="api")
    return plan


@router.post("/plans/{plan_id}/complete", summary="Mark recovery complete")
def complete(plan_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    plan, disruption = complete_recovery(db, plan_id, actor="api")
    return {
        "plan_id": plan.id, "status": plan.status,
        "disruption_id": disruption.id if disruption else None,
        "disruption_status": disruption.status.value if disruption else None,
    }


@router.get("/decisions", response_model=list[DecisionHistoryOut],
            summary="Decision history and tracking")
def decisions(entity_type: Optional[str] = None, entity_id: Optional[int] = None,
               limit: int = Query(100, le=500),
               db: Session = Depends(get_db), _=Depends(get_current_user)):
    return decision_history(db, entity_type=entity_type, entity_id=entity_id, limit=limit)
