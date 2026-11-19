"""SQLAlchemy ORM models.

Tables cover auth, master data (suppliers/products/inventory/customers),
transactions (purchase + customer orders, deliveries, transportation),
analytics (disruptions, recovery plans, approvals, decision history) and
supplier performance snapshots.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    String, Integer, Float, DateTime, ForeignKey, Enum, Text, Boolean,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


# ---- enums -----------------------------------------------------------------

class POStatus(str, enum.Enum):
    open = "open"
    in_transit = "in_transit"
    delivered = "delivered"
    delayed = "delayed"
    cancelled = "cancelled"


class DeliveryStatus(str, enum.Enum):
    scheduled = "scheduled"
    in_transit = "in_transit"
    delivered = "delivered"
    delayed = "delayed"
    failed = "failed"


class DisruptionType(str, enum.Enum):
    supplier_delay = "supplier_delay"
    supplier_unavailable = "supplier_unavailable"
    demand_spike = "demand_spike"
    inventory_shortage = "inventory_shortage"
    transport_disruption = "transport_disruption"


class DisruptionSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DisruptionStatus(str, enum.Enum):
    detected = "detected"
    analyzing = "analyzing"
    planned = "planned"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    recovering = "recovering"
    resolved = "resolved"


class PlanType(str, enum.Enum):
    original = "original"
    optimized = "optimized"
    whatif = "whatif"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class UserRole(str, enum.Enum):
    admin = "admin"
    approver = "approver"
    analyst = "analyst"


# ---- auth -------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.analyst)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---- master data ------------------------------------------------------------

class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    country: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(64), default="")
    rating: Mapped[float] = mapped_column(Float, default=3.5)           # 0-5
    on_time_rate: Mapped[float] = mapped_column(Float, default=0.85)   # 0-1
    avg_lead_time_days: Mapped[float] = mapped_column(Float, default=14.0)
    min_order_qty: Mapped[int] = mapped_column(Integer, default=50)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    products: Mapped[List["Product"]] = relationship(back_populates="supplier")
    purchase_orders: Mapped[List["PurchaseOrder"]] = relationship(back_populates="supplier")
    performance_records: Mapped[List["SupplierPerformance"]] = relationship(back_populates="supplier")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    weight_kg: Mapped[float] = mapped_column(Float, default=1.0)
    primary_supplier_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier: Mapped[Optional["Supplier"]] = relationship(back_populates="products")
    inventory: Mapped[List["Inventory"]] = relationship(back_populates="product")


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    warehouse: Mapped[str] = mapped_column(String(64), default="DC-1")
    on_hand: Mapped[float] = mapped_column(Float, default=0.0)
    safety_stock: Mapped[float] = mapped_column(Float, default=0.0)
    reorder_point: Mapped[float] = mapped_column(Float, default=0.0)
    reserved: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    product: Mapped["Product"] = relationship(back_populates="inventory")

    __table_args__ = (UniqueConstraint("product_id", "warehouse", name="uq_product_warehouse"),)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    country: Mapped[str] = mapped_column(String(64))
    segment: Mapped[str] = mapped_column(String(64), default="retail")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    orders: Mapped[List["CustomerOrder"]] = relationship(back_populates="customer")


# ---- transportation --------------------------------------------------------

class TransportationRoute(Base):
    __tablename__ = "transportation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    origin: Mapped[str] = mapped_column(String(64))
    destination: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(32))            # air | rail | road | sea
    cost_per_unit: Mapped[float] = mapped_column(Float, default=0.0)
    transit_days: Mapped[float] = mapped_column(Float, default=0.0)
    carrier: Mapped[str] = mapped_column(String(64), default="")


# ---- transactions ----------------------------------------------------------

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[POStatus] = mapped_column(Enum(POStatus), default=POStatus.open, index=True)
    order_date: Mapped[datetime] = mapped_column(DateTime)
    expected_delivery: Mapped[datetime] = mapped_column(DateTime)
    actual_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    transport_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    items: Mapped[List["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )
    deliveries: Mapped[List["Delivery"]] = relationship(back_populates="purchase_order")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, default=0.0)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="items")


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    scheduled_date: Mapped[datetime] = mapped_column(DateTime)
    actual_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[DeliveryStatus] = mapped_column(Enum(DeliveryStatus), default=DeliveryStatus.scheduled)
    carrier: Mapped[str] = mapped_column(String(64), default="")
    transport_cost: Mapped[float] = mapped_column(Float, default=0.0)
    transit_days: Mapped[float] = mapped_column(Float, default=0.0)

    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="deliveries")


class CustomerOrder(Base):
    __tablename__ = "customer_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    co_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_date: Mapped[datetime] = mapped_column(DateTime)
    required_date: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="open")
    total_value: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    items: Mapped[List["CustomerOrderItem"]] = relationship(
        back_populates="customer_order", cascade="all, delete-orphan"
    )


class CustomerOrderItem(Base):
    __tablename__ = "customer_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    co_id: Mapped[int] = mapped_column(ForeignKey("customer_orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)

    customer_order: Mapped["CustomerOrder"] = relationship(back_populates="items")


# ---- analytics -------------------------------------------------------------

class SupplierPerformance(Base):
    __tablename__ = "supplier_performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)        # YYYY-MM
    on_time_rate: Mapped[float] = mapped_column(Float, default=0.0)
    defect_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_lead_time: Mapped[float] = mapped_column(Float, default=0.0)
    orders_fulfilled: Mapped[int] = mapped_column(Integer, default=0)

    supplier: Mapped["Supplier"] = relationship(back_populates="performance_records")


class Disruption(Base):
    __tablename__ = "disruptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[DisruptionType] = mapped_column(Enum(DisruptionType), index=True)
    severity: Mapped[DisruptionSeverity] = mapped_column(Enum(DisruptionSeverity), default=DisruptionSeverity.medium)
    status: Mapped[DisruptionStatus] = mapped_column(Enum(DisruptionStatus), default=DisruptionStatus.detected, index=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    po_id: Mapped[Optional[int]] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    description: Mapped[str] = mapped_column(Text, default="")
    estimated_delay_days: Mapped[float] = mapped_column(Float, default=0.0)
    affected_order_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_product_count: Mapped[int] = mapped_column(Integer, default=0)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    recovery_plans: Mapped[List["RecoveryPlan"]] = relationship(back_populates="disruption")


class RecoveryPlan(Base):
    __tablename__ = "recovery_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disruption_id: Mapped[int] = mapped_column(ForeignKey("disruptions.id"), index=True)
    plan_type: Mapped[PlanType] = mapped_column(Enum(PlanType), default=PlanType.optimized)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_transport_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_delay_days: Mapped[float] = mapped_column(Float, default=0.0)
    supplier_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    disruption: Mapped["Disruption"] = relationship(back_populates="recovery_plans")
    items: Mapped[List["RecoveryPlanItem"]] = relationship(
        back_populates="recovery_plan", cascade="all, delete-orphan"
    )
    approval: Mapped[Optional["ApprovalRequest"]] = relationship(
        back_populates="recovery_plan", uselist=False
    )


class RecoveryPlanItem(Base):
    __tablename__ = "recovery_plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("recovery_plans.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    transport_cost: Mapped[float] = mapped_column(Float, default=0.0)
    delivery_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    delay_days: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, default=0.0)

    recovery_plan: Mapped["RecoveryPlan"] = relationship(back_populates="items")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recovery_plan_id: Mapped[int] = mapped_column(ForeignKey("recovery_plans.id"), index=True)
    requester: Mapped[str] = mapped_column(String(64), default="system")
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.pending, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_delay_days: Mapped[float] = mapped_column(Float, default=0.0)

    recovery_plan: Mapped["RecoveryPlan"] = relationship(back_populates="approval")


class DecisionHistory(Base):
    __tablename__ = "decision_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)   # recovery_plan | approval | disruption
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(64), default="system")
    details: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index("ix_decision_history_entity", "entity_type", "entity_id"),)
