"""Seed the database from the synthetic dataset and create a demo admin user.

Idempotent: skips tables that already contain rows. Used by the FastAPI
startup event (when ``SEED_DEMO_DATA=true``) and by the CLI script
``scripts/seed_db.py``.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from .database import SessionLocal, init_db, db_session
from .models import (
    User, UserRole, Supplier, Product, Inventory, Customer,
    TransportationRoute, PurchaseOrder, PurchaseOrderItem, Delivery,
    CustomerOrder, CustomerOrderItem, SupplierPerformance,
    POStatus, DeliveryStatus,
)
from .auth import hash_password
from .config import settings
from .core.logging import get_logger

log = get_logger("seed")

ENUM_PO = {e.value: e for e in POStatus}
ENUM_DEL = {e.value: e for e in DeliveryStatus}


def _to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to records, turning NaN/NaT into None so SQLite
    doesn't choke on float NaN for integer/datetime columns."""
    import pandas as pd
    return df.astype(object).where(pd.notnull(df), None).to_dict("records")


def _load_csvs(data_dir: Path) -> dict[str, pd.DataFrame]:
    tables = {}
    for name in [
        "suppliers", "products", "inventory", "customers", "transportation",
        "purchase_orders", "purchase_order_items", "deliveries",
        "customer_orders", "customer_order_items", "supplier_performance",
    ]:
        p = data_dir / f"{name}.csv"
        if p.exists():
            tables[name] = pd.read_csv(p)
    return tables


def _ensure_admin_user(db: Session) -> None:
    if db.query(User).filter(User.username == "admin").first():
        return
    admin = User(
        username="admin", email="admin@supplychain.local",
        full_name="System Admin", role=UserRole.admin,
        hashed_password=hash_password("admin123"), is_active=True,
    )
    db.add(admin)
    # an approver for demo approvals
    approver = User(
        username="approver", email="approver@supplychain.local",
        full_name="Lead Approver", role=UserRole.approver,
        hashed_password=hash_password("approver123"), is_active=True,
    )
    db.add(approver)
    analyst = User(
        username="analyst", email="analyst@supplychain.local",
        full_name="Supply Analyst", role=UserRole.analyst,
        hashed_password=hash_password("analyst123"), is_active=True,
    )
    db.add(analyst)
    db.commit()
    log.info("seed.users_created")


def _insert_suppliers(db: Session, df: pd.DataFrame) -> None:
    if db.query(Supplier).count():
        return
    rows = _to_records(df)
    db.bulk_insert_mappings(Supplier, rows)
    db.commit()
    log.info("seed.suppliers", count=len(rows))


def _insert_products(db: Session, df: pd.DataFrame) -> None:
    if db.query(Product).count():
        return
    rows = _to_records(df)
    db.bulk_insert_mappings(Product, rows)
    db.commit()
    log.info("seed.products", count=len(rows))


def _insert_inventory(db: Session, df: pd.DataFrame) -> None:
    if db.query(Inventory).count():
        return
    df = df.copy()
    df["updated_at"] = pd.to_datetime(df["updated_at"])
    db.bulk_insert_mappings(Inventory, _to_records(df))
    db.commit()
    log.info("seed.inventory", count=len(df))


def _insert_customers(db: Session, df: pd.DataFrame) -> None:
    if db.query(Customer).count():
        return
    df = df.copy()
    df["created_at"] = pd.to_datetime(df["created_at"])
    db.bulk_insert_mappings(Customer, _to_records(df))
    db.commit()
    log.info("seed.customers", count=len(df))


def _insert_transportation(db: Session, df: pd.DataFrame) -> None:
    if db.query(TransportationRoute).count():
        return
    db.bulk_insert_mappings(TransportationRoute, _to_records(df))
    db.commit()
    log.info("seed.transportation", count=len(df))


def _insert_purchase_orders(db: Session, po_df: pd.DataFrame, item_df: pd.DataFrame) -> None:
    if db.query(PurchaseOrder).count():
        return
    po = po_df.copy()
    for c in ["order_date", "expected_delivery", "actual_delivery", "created_at"]:
        po[c] = pd.to_datetime(po[c], errors="coerce")
    po["status"] = po["status"].map(lambda v: ENUM_PO.get(v, POStatus.open))
    # SQLAlchemy enum expects the enum member
    po_records = _to_records(po)
    db.bulk_insert_mappings(PurchaseOrder, po_records)
    db.commit()

    items = item_df.copy()
    db.bulk_insert_mappings(PurchaseOrderItem, _to_records(items))
    db.commit()
    log.info("seed.purchase_orders", pos=len(po), items=len(items))


def _insert_deliveries(db: Session, df: pd.DataFrame) -> None:
    if db.query(Delivery).count():
        return
    df = df.copy()
    for c in ["scheduled_date", "actual_date"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["status"] = df["status"].map(lambda v: ENUM_DEL.get(v, DeliveryStatus.scheduled))
    db.bulk_insert_mappings(Delivery, _to_records(df))
    db.commit()
    log.info("seed.deliveries", count=len(df))


def _insert_customer_orders(db: Session, co_df: pd.DataFrame, item_df: pd.DataFrame) -> None:
    if db.query(CustomerOrder).count():
        return
    co = co_df.copy()
    for c in ["order_date", "required_date", "created_at"]:
        co[c] = pd.to_datetime(co[c], errors="coerce")
    db.bulk_insert_mappings(CustomerOrder, _to_records(co))
    db.commit()
    db.bulk_insert_mappings(CustomerOrderItem, _to_records(item_df))
    db.commit()
    log.info("seed.customer_orders", cos=len(co), items=len(item_df))


def _insert_supplier_performance(db: Session, df: pd.DataFrame) -> None:
    if db.query(SupplierPerformance).count():
        return
    db.bulk_insert_mappings(SupplierPerformance, _to_records(df))
    db.commit()
    log.info("seed.supplier_performance", count=len(df))


def seed_database(data_dir: str | Path | None = None, force: bool = False) -> dict[str, int]:
    """Ensure schema + data exist. Returns counts inserted per table."""
    init_db()
    data_dir = Path(data_dir) if data_dir else Path(settings.DATASET_CSV).parent
    data_dir.mkdir(parents=True, exist_ok=True)

    # generate CSVs if missing
    if not (data_dir / "suppliers.csv").exists():
        from scripts.generate_dataset import generate, write_csvs
        tables = generate()
        write_csvs(tables, data_dir)
        log.info("seed.dataset_generated")
    else:
        tables = _load_csvs(data_dir)

    counts: dict[str, int] = {}
    with db_session() as db:
        if force:
            db.query(User).delete()
            db.query(Supplier).delete()
        _ensure_admin_user(db)
        if "suppliers" in tables:
            before = db.query(Supplier).count()
            _insert_suppliers(db, tables["suppliers"])
            counts["suppliers"] = db.query(Supplier).count() - before
        if "products" in tables:
            _insert_products(db, tables["products"])
            counts["products"] = db.query(Product).count()
        if "inventory" in tables:
            _insert_inventory(db, tables["inventory"])
            counts["inventory"] = db.query(Inventory).count()
        if "customers" in tables:
            _insert_customers(db, tables["customers"])
            counts["customers"] = db.query(Customer).count()
        if "transportation" in tables:
            _insert_transportation(db, tables["transportation"])
            counts["transportation"] = db.query(TransportationRoute).count()
        if "purchase_orders" in tables and "purchase_order_items" in tables:
            _insert_purchase_orders(db, tables["purchase_orders"], tables["purchase_order_items"])
            counts["purchase_orders"] = db.query(PurchaseOrder).count()
        if "deliveries" in tables:
            _insert_deliveries(db, tables["deliveries"])
            counts["deliveries"] = db.query(Delivery).count()
        if "customer_orders" in tables and "customer_order_items" in tables:
            _insert_customer_orders(db, tables["customer_orders"], tables["customer_order_items"])
            counts["customer_orders"] = db.query(CustomerOrder).count()
        if "supplier_performance" in tables:
            _insert_supplier_performance(db, tables["supplier_performance"])
            counts["supplier_performance"] = db.query(SupplierPerformance).count()
    log.info("seed.complete", counts=counts)
    return counts


def is_seeded() -> bool:
    with db_session() as db:
        return db.query(Supplier).count() > 0
