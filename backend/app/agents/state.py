"""Shared LangGraph workflow state.

TypedDict flows through every specialist node and is persisted by the
LangGraph checkpointer so runs resume after interruption (e.g. while a plan
awaits human approval).
"""
from __future__ import annotations

from typing import TypedDict, Optional, Any, List


class AgentState(TypedDict, total=False):
    # input
    disruption_id: int
    disruption_type: str
    severity: str
    supplier_id: Optional[int]
    product_id: Optional[int]
    po_id: Optional[int]
    description: str
    estimated_delay_days: float

    # monitoring
    delays: List[dict[str, Any]]
    at_risk_suppliers: List[dict[str, Any]]

    # impact analysis
    affected_product_ids: List[int]
    affected_po_ids: List[int]
    affected_order_count: int
    affected_product_count: int
    committed_quantity: float
    at_risk_value: float
    inventory_gap: List[dict[str, Any]]
    total_shortfall: float

    # forecasting
    demand_forecast: List[dict[str, Any]]
    shortage_predictions: List[dict[str, Any]]

    # supplier evaluation
    alternative_suppliers: List[dict[str, Any]]
    supplier_scores: List[dict[str, Any]]

    # optimization
    original_plan_id: Optional[int]
    optimized_plan_id: Optional[int]
    original_plan_summary: dict[str, Any]
    optimized_plan_summary: dict[str, Any]
    plan_comparison: dict[str, Any]

    # approval
    approval_required: bool
    approval_reason: str
    approval_request_id: Optional[int]
    approval_status: str

    # tracking
    decision_records: List[dict[str, Any]]
    recovery_status: str

    # control
    run_optimization: bool
    request_approval: bool
    status: str
    error: Optional[str]
    summary: str
    errors: List[str]
