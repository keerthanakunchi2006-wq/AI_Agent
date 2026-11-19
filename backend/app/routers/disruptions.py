"""Disruptions and the LangGraph disruption-recovery workflow trigger."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Disruption, User, RecoveryPlan
from ..schemas import DisruptionCreate, DisruptionOut, AgentRunRequest, AgentRunResult, RecoveryPlanOut
from ..services.monitoring import detect_delays
from ..core.logging import get_logger

router = APIRouter(prefix="/disruptions", tags=["disruptions"])
log = get_logger("api.disruptions")


@router.get("", response_model=list[DisruptionOut], summary="List disruptions")
def list_disruptions(status: Optional[str] = None, skip: int = 0,
                     limit: int = Query(100, le=500),
                     db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Disruption)
    if status:
        q = q.filter(Disruption.status == status)
    return q.order_by(Disruption.detected_at.desc()).offset(skip).limit(limit).all()


@router.get("/{disruption_id}", response_model=DisruptionOut)
def get_disruption(disruption_id: int, db: Session = Depends(get_db),
                   _=Depends(get_current_user)):
    d = db.get(Disruption, disruption_id) if hasattr(db, "get") else db.query(Disruption).get(disruption_id)
    if not d:
        raise HTTPException(404, "Disruption not found")
    return d


@router.post("", response_model=DisruptionOut, summary="Create a disruption record")
def create_disruption(payload: DisruptionCreate, db: Session = Depends(get_db),
                       _=Depends(get_current_user)):
    d = Disruption(
        type=payload.type, severity=payload.severity,
        supplier_id=payload.supplier_id, product_id=payload.product_id,
        po_id=payload.po_id, description=payload.description,
        estimated_delay_days=payload.estimated_delay_days,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


@router.post("/run", response_model=AgentRunResult,
             summary="Run the full LangGraph disruption-recovery workflow")
def run_agent_workflow(payload: AgentRunRequest, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """Create the disruption, then execute the seven-agent LangGraph graph."""
    from ..agents.orchestrator import run_workflow
    from ..models import DisruptionStatus

    # 1. create disruption record if not provided
    disruption = Disruption(
        type=payload.disruption.type, severity=payload.disruption.severity,
        supplier_id=payload.disruption.supplier_id,
        product_id=payload.disruption.product_id,
        po_id=payload.disruption.po_id,
        description=payload.disruption.description,
        estimated_delay_days=payload.disruption.estimated_delay_days,
        status=DisruptionStatus.detected,
    )
    db.add(disruption)
    db.commit()
    db.refresh(disruption)
    disruption_id = disruption.id

    # 2. run the workflow (uses its own db session per node)
    initial = {
        "disruption_id": disruption_id,
        "disruption_type": payload.disruption.type,
        "severity": payload.disruption.severity,
        "supplier_id": payload.disruption.supplier_id,
        "product_id": payload.disruption.product_id,
        "po_id": payload.disruption.po_id,
        "description": payload.disruption.description,
        "estimated_delay_days": payload.disruption.estimated_delay_days,
        "run_optimization": payload.run_optimization,
        "request_approval": payload.request_approval,
    }
    try:
        thread_id, final_state = run_workflow(initial)
    except Exception as e:  # noqa: BLE001
        log.error("workflow.run_failed", error=str(e))
        raise HTTPException(500, f"Workflow failed: {e}")

    # 3. fetch the optimized recovery plan for the response
    optimized_plan = None
    opt_id = final_state.get("optimized_plan_id")
    if opt_id:
        plan = db.get(RecoveryPlan, opt_id) if hasattr(db, "get") else db.query(RecoveryPlan).get(opt_id)
        if plan:
            optimized_plan = RecoveryPlanOut.model_validate(plan, from_attributes=True)

    comparison = final_state.get("plan_comparison", {})
    summary = (
        f"Workflow complete for disruption {disruption_id}. "
        f"Affected orders: {final_state.get('affected_order_count', 0)}, "
        f"products: {final_state.get('affected_product_count', 0)}, "
        f"shortfall: {final_state.get('total_shortfall', 0):.0f}. "
        f"Optimized plan cost {comparison.get('optimized_total_cost', 0):.0f} "
        f"vs original {comparison.get('original_total_cost', 0):.0f} "
        f"(savings {comparison.get('cost_savings', 0):.0f}). "
        f"Approval: {final_state.get('approval_status', 'n/a')}."
    )

    return AgentRunResult(
        thread_id=thread_id,
        disruption_id=disruption_id,
        status=final_state.get("status", "completed"),
        monitoring={"delays": final_state.get("delays", []),
                    "at_risk_suppliers": final_state.get("at_risk_suppliers", [])},
        impact_analysis={
            "affected_product_ids": final_state.get("affected_product_ids", []),
            "affected_po_ids": final_state.get("affected_po_ids", []),
            "affected_order_count": final_state.get("affected_order_count", 0),
            "affected_product_count": final_state.get("affected_product_count", 0),
            "committed_quantity": final_state.get("committed_quantity", 0),
            "at_risk_value": final_state.get("at_risk_value", 0),
            "total_shortfall": final_state.get("total_shortfall", 0),
            "inventory_gap": final_state.get("inventory_gap", []),
        },
        forecasting={
            "demand_forecast": final_state.get("demand_forecast", [])[:10],
            "shortage_predictions": final_state.get("shortage_predictions", []),
        },
        supplier_evaluation={
            "alternatives": final_state.get("alternative_suppliers", [])[:20],
            "scores": final_state.get("supplier_scores", []),
        },
        optimization=comparison,
        approval={
            "approval_required": final_state.get("approval_required", False),
            "approval_reason": final_state.get("approval_reason", ""),
            "approval_request_id": final_state.get("approval_request_id"),
            "approval_status": final_state.get("approval_status", ""),
        },
        tracking={
            "decision_records": final_state.get("decision_records", []),
            "recovery_status": final_state.get("recovery_status", ""),
        },
        recovery_plan=optimized_plan,
        summary=summary,
    )


@router.get("/delays/monitor", summary="Trigger monitoring and list current delays")
def monitor_delays(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return detect_delays(db)
