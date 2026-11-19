"""Suppliers, products, inventory, customers, POs, deliveries, transportation."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import (
    Supplier, Product, Inventory, Customer, PurchaseOrder, Delivery,
    TransportationRoute, SupplierPerformance,
)
from ..schemas import (
    SupplierOut, ProductOut, InventoryOut, CustomerOut, PurchaseOrderOut,
    DeliveryOut, TransportationRouteOut, SupplierPerformanceOut,
)

router = APIRouter(prefix="/master", tags=["master-data"])


# ---- suppliers ---------------------------------------------------------------

@router.get("/suppliers", response_model=list[SupplierOut], summary="List suppliers")
def list_suppliers(
    active_only: bool = False,
    search: Optional[str] = None,
    skip: int = 0, limit: int = Query(100, le=500),
    db: Session = Depends(get_db), _=Depends(get_current_user),
):
    q = db.query(Supplier)
    if active_only:
        q = q.filter(Supplier.active.is_(True))
    if search:
        q = q.filter(Supplier.name.ilike(f"%{search}%"))
    return q.offset(skip).limit(limit).all()


@router.get("/suppliers/{supplier_id}", response_model=SupplierOut)
def get_supplier(supplier_id: int, db: Session = Depends(get_db),
                 _=Depends(get_current_user)):
    s = db.get(Supplier, supplier_id) if hasattr(db, "get") else db.query(Supplier).get(supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found")
    return s


@router.get("/suppliers/{supplier_id}/performance",
            response_model=list[SupplierPerformanceOut])
def supplier_performance(supplier_id: int, db: Session = Depends(get_db),
                         _=Depends(get_current_user)):
    return db.query(SupplierPerformance).filter(
        SupplierPerformance.supplier_id == supplier_id
    ).order_by(SupplierPerformance.period).all()


# ---- products ---------------------------------------------------------------

@router.get("/products", response_model=list[ProductOut], summary="List products")
def list_products(category: Optional[str] = None, search: Optional[str] = None,
                  skip: int = 0, limit: int = Query(100, le=500),
                  db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Product)
    if category:
        q = q.filter(Product.category == category)
    if search:
        q = q.filter(Product.name.ilike(f"%{search}%") | Product.sku.ilike(f"%{search}%"))
    return q.offset(skip).limit(limit).all()


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db),
                _=Depends(get_current_user)):
    p = db.get(Product, product_id) if hasattr(db, "get") else db.query(Product).get(product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    return p


# ---- inventory --------------------------------------------------------------

@router.get("/inventory", response_model=list[InventoryOut], summary="List inventory")
def list_inventory(product_id: Optional[int] = None, low_only: bool = False,
                   skip: int = 0, limit: int = Query(200, le=1000),
                   db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Inventory)
    if product_id:
        q = q.filter(Inventory.product_id == product_id)
    rows = q.offset(skip).limit(limit).all()
    if low_only:
        rows = [r for r in rows if max(0.0, r.on_hand - r.reserved) < r.reorder_point]
    return rows


# ---- customers --------------------------------------------------------------

@router.get("/customers", response_model=list[CustomerOut], summary="List customers")
def list_customers(skip: int = 0, limit: int = Query(100, le=500),
                   db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Customer).offset(skip).limit(limit).all()


# ---- purchase orders --------------------------------------------------------

@router.get("/purchase-orders", response_model=list[PurchaseOrderOut],
            summary="List purchase orders")
def list_pos(status: Optional[str] = None, supplier_id: Optional[int] = None,
             skip: int = 0, limit: int = Query(100, le=500),
             db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(PurchaseOrder)
    if status:
        q = q.filter(PurchaseOrder.status == status)
    if supplier_id:
        q = q.filter(PurchaseOrder.supplier_id == supplier_id)
    return q.order_by(PurchaseOrder.order_date.desc()).offset(skip).limit(limit).all()


@router.get("/purchase-orders/{po_id}", response_model=PurchaseOrderOut)
def get_po(po_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    po = db.get(PurchaseOrder, po_id) if hasattr(db, "get") else db.query(PurchaseOrder).get(po_id)
    if not po:
        raise HTTPException(404, "Purchase order not found")
    return po


# ---- deliveries -------------------------------------------------------------

@router.get("/deliveries", response_model=list[DeliveryOut], summary="List deliveries")
def list_deliveries(status: Optional[str] = None, po_id: Optional[int] = None,
                    skip: int = 0, limit: int = Query(100, le=500),
                    db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Delivery)
    if status:
        q = q.filter(Delivery.status == status)
    if po_id:
        q = q.filter(Delivery.po_id == po_id)
    return q.order_by(Delivery.scheduled_date.desc()).offset(skip).limit(limit).all()


# ---- transportation ---------------------------------------------------------

@router.get("/transportation", response_model=list[TransportationRouteOut],
            summary="List transportation routes")
def list_transportation(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(TransportationRoute).all()
