"""Monitoring service — supplier delay detection.

A delay is detected when an open/in-transit PO is past its expected delivery
date with no actual delivery, or when actual delivery exceeded expected by
more than the configured tolerance. We also compute per-supplier on-time
performance from historical deliveries.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import (
    PurchaseOrder, POStatus, Delivery, DeliveryStatus, Supplier,
    SupplierPerformance,
)
from ..core.logging import get_logger

log = get_logger("monitoring")

DELAY_TOLERANCE_DAYS = 1.0


def detect_delays(db: Session, as_of: datetime | None = None) -> list[dict[str, Any]]:
    """Return all currently-delayed shipments with supplier context."""
    as_of = as_of or datetime.utcnow()

    late_pos = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.status.in_([POStatus.open, POStatus.in_transit, POStatus.delayed]))
        .filter(PurchaseOrder.expected_delivery < as_of - timedelta(days=DELAY_TOLERANCE_DAYS))
        .all()
    )

    delays: list[dict[str, Any]] = []
    for po in late_pos:
        supplier = po.supplier
        days_late = (as_of - po.expected_delivery).days
        delays.append({
            "po_id": po.id,
            "po_number": po.po_number,
            "supplier_id": po.supplier_id,
            "supplier_name": supplier.name if supplier else None,
            "supplier_on_time_rate": supplier.on_time_rate if supplier else None,
            "expected_delivery": po.expected_delivery.isoformat(),
            "days_late": days_late,
            "status": po.status.value,
            "total_cost": po.total_cost,
            "items": [
                {
                    "product_id": it.product_id,
                    "quantity": it.quantity,
                    "unit_cost": it.unit_cost,
                    "line_total": it.line_total,
                }
                for it in po.items
            ],
        })
    log.info("monitoring.delays_detected", count=len(delays))
    return delays


def supplier_on_time_summary(db: Session) -> list[dict[str, Any]]:
    """Aggregate on-time performance per supplier from deliveries."""
    deliveries = db.query(Delivery).filter(Delivery.status.in_(
        [DeliveryStatus.delivered, DeliveryStatus.delayed]
    )).all()

    by_supplier: dict[int, dict[str, int | float]] = {}
    for d in deliveries:
        po = d.purchase_order
        if not po:
            continue
        sid = po.supplier_id
        agg = by_supplier.setdefault(sid, {"supplier_id": sid, "on_time": 0, "late": 0, "orders": 0})
        agg["orders"] += 1
        if d.status == DeliveryStatus.delivered:
            agg["on_time"] += 1
        else:
            agg["late"] += 1

    result = []
    for sid, agg in by_supplier.items():
        on_time_rate = (agg["on_time"] / agg["orders"]) if agg["orders"] else 0.0
        result.append({
            "supplier_id": sid,
            "on_time_rate": round(on_time_rate, 3),
            "late_orders": agg["late"],
            "total_orders": agg["orders"],
        })
    return result


def identify_at_risk_suppliers(db: Session, threshold: float = 0.80) -> list[dict[str, Any]]:
    """Suppliers whose on-time rate or rating is below threshold."""
    rows = (
        db.query(Supplier)
        .filter(Supplier.active.is_(True))
        .filter((Supplier.on_time_rate < threshold) | (Supplier.rating < 3.0))
        .all()
    )
    return [
        {
            "supplier_id": s.id,
            "supplier_name": s.name,
            "country": s.country,
            "on_time_rate": s.on_time_rate,
            "rating": s.rating,
            "avg_lead_time_days": s.avg_lead_time_days,
            "risk_factors": [
                factor for factor, cond in [
                    ("low_on_time_rate", s.on_time_rate < threshold),
                    ("low_rating", s.rating < 3.0),
                    ("long_lead_time", s.avg_lead_time_days > 25),
                ] if cond
            ],
        }
        for s in rows
    ]
