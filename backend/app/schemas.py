"""Pydantic v2 request/response schemas (validation boundary for the API)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, ConfigDict


# ---- auth -------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    full_name: str = ""


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str
    password: str = Field(min_length=6, max_length=128)
    full_name: str = ""
    role: Literal["admin", "approver", "analyst"] = "analyst"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool


class LoginIn(BaseModel):
    username: str
    password: str


# ---- master data ------------------------------------------------------------

class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    code: str
    country: str
    region: str
    rating: float
    on_time_rate: float
    avg_lead_time_days: float
    min_order_qty: int
    active: bool


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sku: str
    name: str
    category: str
    unit_cost: float
    unit_price: float
    weight_kg: float
    primary_supplier_id: Optional[int] = None


class InventoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    warehouse: str
    on_hand: float
    safety_stock: float
    reorder_point: float
    reserved: float
    updated_at: datetime


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    code: str
    country: str
    segment: str


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    po_number: str
    supplier_id: int
    status: str
    order_date: datetime
    expected_delivery: datetime
    actual_delivery: Optional[datetime] = None
    total_cost: float
    transport_cost: float
    items: List["PurchaseOrderItemOut"] = Field(default_factory=list)


class PurchaseOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    quantity: float
    unit_cost: float
    line_total: float


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    po_id: int
    scheduled_date: datetime
    actual_date: Optional[datetime] = None
    status: str
    carrier: str
    transport_cost: float
    transit_days: float


class CustomerOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    co_number: str
    customer_id: int
    order_date: datetime
    required_date: datetime
    status: str
    total_value: float


class TransportationRouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    route_code: str
    origin: str
    destination: str
    mode: str
    cost_per_unit: float
    transit_days: float
    carrier: str


class SupplierPerformanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplier_id: int
    period: str
    on_time_rate: float
    defect_rate: float
    avg_lead_time: float
    orders_fulfilled: int


# ---- agent / disruption workflows ------------------------------------------

class DisruptionCreate(BaseModel):
    type: Literal[
        "supplier_delay", "supplier_unavailable", "demand_spike",
        "inventory_shortage", "transport_disruption",
    ]
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    supplier_id: Optional[int] = None
    product_id: Optional[int] = None
    po_id: Optional[int] = None
    description: str = ""
    estimated_delay_days: float = 0.0


class DisruptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    severity: str
    status: str
    supplier_id: Optional[int] = None
    product_id: Optional[int] = None
    po_id: Optional[int] = None
    detected_at: datetime
    description: str
    estimated_delay_days: float
    affected_order_count: int
    affected_product_count: int
    resolved_at: Optional[datetime] = None


class RecoveryPlanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    supplier_id: int
    quantity: float
    unit_cost: float
    transport_cost: float
    delivery_date: datetime
    delay_days: float
    line_total: float


class RecoveryPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    disruption_id: int
    plan_type: str
    total_cost: float
    total_transport_cost: float
    total_delay_days: float
    supplier_count: int
    status: str
    summary: str
    created_at: datetime
    items: List[RecoveryPlanItemOut] = Field(default_factory=list)


class ApprovalRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recovery_plan_id: int
    requester: str
    status: str
    requested_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision_note: str = ""
    total_cost: float
    total_delay_days: float


class ApprovalDecisionIn(BaseModel):
    status: Literal["approved", "rejected"]
    decided_by: str
    decision_note: str = ""


class DecisionHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entity_type: str
    entity_id: int
    action: str
    actor: str
    details: str
    timestamp: datetime


# ---- dashboard -------------------------------------------------------------

class DashboardSummary(BaseModel):
    total_suppliers: int
    total_products: int
    active_purchase_orders: int
    delayed_shipments: int
    low_inventory_count: int
    open_disruptions: int
    pending_approvals: int
    total_inventory_value: float
    on_time_delivery_rate: float


class RiskAlert(BaseModel):
    id: int
    level: str           # high | medium | low
    category: str
    title: str
    description: str
    created_at: datetime


class SupplierPerformancePoint(BaseModel):
    supplier_id: int
    supplier_name: str
    period: str
    on_time_rate: float
    avg_lead_time: float


class DemandForecastPoint(BaseModel):
    product_id: int
    product_name: str
    period: str
    predicted_demand: float
    lower_bound: float
    upper_bound: float
    is_shortage_risk: bool


class AlternativeSupplierOut(BaseModel):
    supplier_id: int
    supplier_name: str
    country: str
    rating: float
    on_time_rate: float
    lead_time_days: float
    unit_cost: float
    total_cost: float
    transport_cost: float
    delivery_days: float
    delay_vs_original: float
    score: float


class SimulationResult(BaseModel):
    scenario: str
    disruption_summary: dict
    affected_orders: int
    affected_products: int
    inventory_gap: float
    original_plan_cost: float
    optimized_plan_cost: float
    original_plan_delay_days: float
    optimized_plan_delay_days: float
    recovery_plan: Optional[RecoveryPlanOut] = None
    alternatives: List[AlternativeSupplierOut] = Field(default_factory=list)
    created_at: datetime


class AgentRunRequest(BaseModel):
    """Trigger the full LangGraph disruption-recovery workflow."""
    disruption: DisruptionCreate
    run_optimization: bool = True
    request_approval: bool = True


class AgentRunResult(BaseModel):
    thread_id: str
    disruption_id: int
    status: str
    monitoring: dict = Field(default_factory=dict)
    impact_analysis: dict = Field(default_factory=dict)
    forecasting: dict = Field(default_factory=dict)
    supplier_evaluation: dict = Field(default_factory=dict)
    optimization: dict = Field(default_factory=dict)
    approval: dict = Field(default_factory=dict)
    tracking: dict = Field(default_factory=dict)
    recovery_plan: Optional[RecoveryPlanOut] = None
    summary: str = ""


PurchaseOrderOut.model_rebuild()
CustomerOrderOut.model_rebuild()
