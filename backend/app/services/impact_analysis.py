"""Impact analysis — which orders, products and inventory are affected by a
disruption, and what is the resulting inventory gap.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import (
    PurchaseOrder, PurchaseOrderItem, Product, Inventory, CustomerOrder,
    CustomerOrderItem, Supplier, Disruption, DisruptionType,
)
from ..core.logging import get_logger

log = get_logger("impact_analysis")


def affected_products_for_supplier(db: Session, supplier_id: int) -> list[int]:
    return [p.id for p in db.query(Product).filter(Product.primary_supplier_id == supplier_id).all()]


def affected_open_pos(db: Session, supplier_id: int) -> list[PurchaseOrder]:
    return (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.supplier_id == supplier_id)
        .filter(PurchaseOrder.status.in_(["open", "in_transit", "delayed"]))
        .all()
    )


def affected_customer_orders(db: Session, product_ids: list[int]) -> list[CustomerOrder]:
    if not product_ids:
        return []
    co_ids = (
        db.query(CustomerOrderItem.co_id)
        .filter(CustomerOrderItem.product_id.in_(product_ids))
        .distinct()
        .all()
    )
    co_ids = [c[0] for c in co_ids]
    if not co_ids:
        return []
    return db.query(CustomerOrder).filter(CustomerOrder.id.in_(co_ids)).all()


def compute_inventory_gap(db: Session, product_ids: list[int]) -> list[dict[str, Any]]:
    """For each affected product compute on-hand vs safety stock gap."""
    rows = db.query(Inventory).filter(Inventory.product_id.in_(product_ids)).all()
    result = []
    for inv in rows:
        available = max(0.0, inv.on_hand - inv.reserved)
        gap = inv.safety_stock - available
        result.append({
            "product_id": inv.product_id,
            "warehouse": inv.warehouse,
            "on_hand": float(inv.on_hand),
            "reserved": float(inv.reserved),
            "available": float(available),
            "safety_stock": float(inv.safety_stock),
            "reorder_point": float(inv.reorder_point),
            "shortfall": float(round(max(0.0, gap), 2)),
            "is_low": available < inv.reorder_point,
        })
    return result


def analyze_impact(db: Session, disruption: Disruption) -> dict[str, Any]:
    """Full impact analysis for a given disruption record."""
    supplier_id = disruption.supplier_id
    product_id = disruption.product_id

    if disruption.type == DisruptionType.supplier_unavailable and supplier_id:
        affected_products = affected_products_for_supplier(db, supplier_id)
        affected_pos = affected_open_pos(db, supplier_id)
    elif disruption.type == DisruptionType.supplier_delay and disruption.po_id:
        po = db.get(PurchaseOrder, disruption.po_id)
        affected_pos = [po] if po else []
        affected_products = list({it.product_id for po in affected_pos for it in po.items})
    elif product_id:
        affected_products = [product_id]
        affected_pos = []
    elif supplier_id:
        affected_products = affected_products_for_supplier(db, supplier_id)
        affected_pos = affected_open_pos(db, supplier_id)
    else:
        affected_products = []
        affected_pos = []

    affected_co = affected_customer_orders(db, affected_products)
    inventory_gap = compute_inventory_gap(db, affected_products)

    # total committed quantity from affected POs
    committed_qty = sum(it.quantity for po in affected_pos for it in po.items)
    at_risk_value = sum(it.line_total for po in affected_pos for it in po.items)

    result = {
        "disruption_id": disruption.id,
        "disruption_type": disruption.type.value,
        "affected_supplier_id": supplier_id,
        "affected_product_ids": affected_products,
        "affected_product_count": len(affected_products),
        "affected_po_ids": [po.id for po in affected_pos],
        "affected_order_count": len(affected_pos),
        "affected_customer_order_count": len(affected_co),
        "committed_quantity": float(round(committed_qty, 2)),
        "at_risk_value": float(round(at_risk_value, 2)),
        "inventory_gap": inventory_gap,
        "total_shortfall": float(round(sum(g["shortfall"] for g in inventory_gap), 2)),
        "low_inventory_count": sum(1 for g in inventory_gap if g["is_low"]),
    }
    log.info("impact_analysis.complete",
             disruption=disruption.id, products=len(affected_products),
             orders=len(affected_pos), shortfall=result["total_shortfall"])
    return result
