"""What-if disruption simulation: run impact + alternatives + optimisation for a
hypothetical disruption without persisting a full agent run.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Disruption, DisruptionType, DisruptionStatus, DisruptionSeverity, RecoveryPlan
from ..schemas import SimulationResult, DisruptionCreate, AlternativeSupplierOut, RecoveryPlanOut
from ..services.impact_analysis import analyze_impact
from ..services.supplier_eval import evaluate_alternatives
from ..services.optimization import generate_recovery_plan, generate_original_plan
from ..core.logging import get_logger

router = APIRouter(prefix="/simulations", tags=["simulation"])
log = get_logger("api.simulations")


@router.post("/what-if", response_model=SimulationResult,
             summary="Simulate a disruption and compare recovery strategies")
def what_if(payload: DisruptionCreate, db: Session = Depends(get_db),
            _=Depends(get_current_user)):
    """Deterministic what-if: build a transient disruption, analyse impact,
    evaluate alternatives, build both original and optimised plans, compare."""
    disruption = Disruption(
        type=payload.type, severity=payload.severity,
        supplier_id=payload.supplier_id, product_id=payload.product_id,
        po_id=payload.po_id, description=payload.description,
        estimated_delay_days=payload.estimated_delay_days,
        status=DisruptionStatus.detected,
    )
    db.add(disruption)
    db.commit()
    db.refresh(disruption)

    impact = analyze_impact(db, disruption)
    affected = impact["affected_product_ids"]

    # alternatives for the first affected product (most common demo case)
    alternatives: list[AlternativeSupplierOut] = []
    if affected:
        gap_rows = impact["inventory_gap"]
        for pid in affected[:5]:
            qty = max(100.0, next((g["shortfall"] for g in gap_rows
                                   if g["product_id"] == pid and g["shortfall"] > 0), 200.0))
            alts = evaluate_alternatives(db, pid, qty, exclude_supplier_id=payload.supplier_id)
            for a in alts[:5]:
                alternatives.append(AlternativeSupplierOut(
                    supplier_id=a["supplier_id"], supplier_name=a["supplier_name"],
                    country=a["country"], rating=a["rating"],
                    on_time_rate=a["on_time_rate"], lead_time_days=a["lead_time_days"],
                    unit_cost=a["unit_cost"], total_cost=a["total_cost"],
                    transport_cost=a["transport_cost"], delivery_days=a["delivery_days"],
                    delay_vs_original=a.get("delay_vs_original", 0.0), score=a["score"],
                ))

    # build original + optimized plans
    orig_plan, _ = generate_original_plan(db, disruption, affected,
                                           impact["inventory_gap"], payload.supplier_id)
    opt_plan, _ = generate_recovery_plan(db, disruption, affected,
                                          impact["inventory_gap"],
                                          exclude_supplier_id=payload.supplier_id,
                                          plan_type="optimized")

    disruption_summary = {
        "type": payload.type, "severity": payload.severity,
        "supplier_id": payload.supplier_id, "product_id": payload.product_id,
        "estimated_delay_days": payload.estimated_delay_days,
        "description": payload.description,
    }

    return SimulationResult(
        scenario=f"{payload.type} ({payload.severity})",
        disruption_summary=disruption_summary,
        affected_orders=impact["affected_order_count"],
        affected_products=impact["affected_product_count"],
        inventory_gap=impact["total_shortfall"],
        original_plan_cost=orig_plan.total_cost,
        optimized_plan_cost=opt_plan.total_cost,
        original_plan_delay_days=orig_plan.total_delay_days,
        optimized_plan_delay_days=opt_plan.total_delay_days,
        recovery_plan=RecoveryPlanOut.model_validate(opt_plan, from_attributes=True),
        alternatives=alternatives,
        created_at=datetime.utcnow(),
    )
