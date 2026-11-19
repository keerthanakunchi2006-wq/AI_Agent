"""Dashboard aggregation — KPI summary, risk alerts, chart data."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Supplier, Product, Inventory, PurchaseOrder, POStatus, Delivery,
    DeliveryStatus, Disruption, DisruptionStatus, ApprovalRequest, ApprovalStatus,
    SupplierPerformance, CustomerOrder, CustomerOrderItem,
)
from .monitoring import detect_delays, identify_at_risk_suppliers
from .forecasting import predict_shortages
from ..core.logging import get_logger

log = get_logger("dashboard")


def get_summary(db: Session) -> dict[str, Any]:
    total_suppliers = db.query(func.count(Supplier.id)).scalar() or 0
    total_products = db.query(func.count(Product.id)).scalar() or 0
    active_pos = db.query(func.count(PurchaseOrder.id)).filter(
        PurchaseOrder.status.in_([POStatus.open, POStatus.in_transit, POStatus.delayed])
    ).scalar() or 0
    delayed = db.query(func.count(PurchaseOrder.id)).filter(
        PurchaseOrder.status == POStatus.delayed
    ).scalar() or 0

    # low inventory: available < reorder point
    inv_rows = db.query(Inventory).all()
    low_inv = sum(1 for i in inv_rows if max(0.0, i.on_hand - i.reserved) < i.reorder_point)

    # inventory value (efficient single join, no N+1)
    inv_value = 0.0
    value_rows = (
        db.query(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .all()
    )
    for inv, prod in value_rows:
        inv_value += max(0.0, inv.on_hand - inv.reserved) * (prod.unit_cost if prod else 0.0)
    inv_value = round(inv_value, 2)

    open_disruptions = db.query(func.count(Disruption.id)).filter(
        Disruption.status.in_([DisruptionStatus.detected, DisruptionStatus.analyzing,
                               DisruptionStatus.planned, DisruptionStatus.pending_approval,
                               DisruptionStatus.approved, DisruptionStatus.recovering])
    ).scalar() or 0

    pending_approvals = db.query(func.count(ApprovalRequest.id)).filter(
        ApprovalRequest.status == ApprovalStatus.pending
    ).scalar() or 0

    # on-time delivery rate
    delivered = db.query(func.count(Delivery.id)).filter(
        Delivery.status.in_([DeliveryStatus.delivered, DeliveryStatus.delayed])
    ).scalar() or 0
    on_time = db.query(func.count(Delivery.id)).filter(
        Delivery.status == DeliveryStatus.delivered
    ).scalar() or 0
    on_time_rate = round(on_time / delivered, 3) if delivered else 0.0

    return {
        "total_suppliers": total_suppliers,
        "total_products": total_products,
        "active_purchase_orders": active_pos,
        "delayed_shipments": delayed,
        "low_inventory_count": low_inv,
        "open_disruptions": open_disruptions,
        "pending_approvals": pending_approvals,
        "total_inventory_value": round(inv_value, 2),
        "on_time_delivery_rate": on_time_rate,
    }


def get_risk_alerts(db: Session, limit: int = 12) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    # delayed shipments
    delays = detect_delays(db)
    for d in delays[:5]:
        alerts.append({
            "id": -d["po_id"],
            "level": "high" if d["days_late"] > 10 else "medium",
            "category": "supplier_delay",
            "title": f"Delayed shipment {d['po_number']}",
            "description": f"{d['supplier_name']} is {d['days_late']}d late "
                           f"(on-time rate {d.get('supplier_on_time_rate')})",
            "created_at": datetime.utcnow().isoformat(),
        })
    # at-risk suppliers
    for s in identify_at_risk_suppliers(db)[:5]:
        alerts.append({
            "id": s["supplier_id"],
            "level": "medium",
            "category": "supplier_risk",
            "title": f"At-risk supplier {s['supplier_name']}",
            "description": f"On-time {s['on_time_rate']:.2%}, rating {s['rating']}, "
                           f"lead {s['avg_lead_time_days']}d",
            "created_at": datetime.utcnow().isoformat(),
        })
    # shortage risks
    try:
        shortages = predict_shortages(db, horizon_months=1)[:5]
        for sh in shortages:
            alerts.append({
                "id": sh["product_id"],
                "level": "high" if sh["predicted_demand"] > 0 else "low",
                "category": "inventory_shortage",
                "title": f"Shortage risk: {sh['product_name']}",
                "description": f"Predicted demand {sh['predicted_demand']} vs on-hand {sh['on_hand']}",
                "created_at": datetime.utcnow().isoformat(),
            })
    except Exception as e:  # forecasting may fail with tiny datasets
        log.warning("dashboard.shortage_alert_failed", error=str(e))

    # sort by level severity then limit
    severity = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: severity.get(a["level"], 3))
    return alerts[:limit]


def get_supplier_performance_chart(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(SupplierPerformance, Supplier)
        .join(Supplier, SupplierPerformance.supplier_id == Supplier.id)
        .order_by(SupplierPerformance.period)
        .limit(400)
        .all()
    )
    return [
        {
            "supplier_id": perf.supplier_id,
            "supplier_name": sup.name,
            "period": perf.period,
            "on_time_rate": perf.on_time_rate,
            "avg_lead_time": perf.avg_lead_time,
        }
        for perf, sup in rows
    ]


def get_demand_forecast_chart(db: Session, limit: int = 200) -> list[dict[str, Any]]:
    from .forecasting import forecast_demand
    try:
        return forecast_demand(db, horizon_months=3)[:limit]
    except Exception as e:
        log.warning("dashboard.forecast_failed", error=str(e))
        return []


def get_low_inventory_items(db: Session) -> list[dict[str, Any]]:
    rows = (
        db.query(Inventory, Product)
        .join(Product, Inventory.product_id == Product.id)
        .all()
    )
    out = []
    for i, product in rows:
        available = max(0.0, i.on_hand - i.reserved)
        if available < i.reorder_point:
            out.append({
                "inventory_id": i.id,
                "product_id": i.product_id,
                "product_name": product.name if product else "",
                "sku": product.sku if product else "",
                "warehouse": i.warehouse,
                "on_hand": float(i.on_hand),
                "available": float(available),
                "safety_stock": float(i.safety_stock),
                "reorder_point": float(i.reorder_point),
                "status": "critical" if available < i.safety_stock else "low",
            })
    return out
