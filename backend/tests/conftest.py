"""Pytest configuration: isolated SQLite test DB, seeded data, auth overrides.

Environment variables are set *before* importing the app so the cached
Settings point at a throwaway **file-based** SQLite DB. A file DB (not
:memory:) is used so that every connection / session — including the ones the
LangGraph agent nodes open via ``app.database.db_session()`` — sees the same
seeded data. Auth is overridden so endpoints are reachable without real JWTs.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ---- configure env BEFORE any app import -------------------------------
os.environ["APP_ENV"] = "test"
os.environ["APP_DEBUG"] = "true"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["JWT_SECRET"] = "test-secret-key-not-for-production"
os.environ["REDIS_URL"] = ""
os.environ["CHECKPOINT_DB_URL"] = ""

# Use a single temp file DB shared across all sessions/threads.
_TEST_DB = os.path.join(tempfile.gettempdir(), "sc_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, get_db, init_db  # noqa: E402
from app import models  # noqa: E402,F401  register tables on metadata
from app.models import User, UserRole  # noqa: E402
from app.auth import hash_password  # noqa: E402

from app.config import settings  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


# Replace the app's engine + sessionmaker with one bound to the temp file so
# the API dependency, the services AND the agent nodes all share one DB.
_test_engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)


@event.listens_for(_test_engine, "connect")
def _enable_fk(dbapi_conn, _):  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


import app.database as db_module  # noqa: E402
db_module.engine = _test_engine
db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False,
                                      bind=_test_engine, future=True)

# also recreate Base metadata on the test engine
init_db()


def _seed_once():
    """Populate the shared DB once with a synthetic subset + demo users."""
    from scripts.generate_dataset import generate
    from app.seed import (
        _insert_suppliers, _insert_products, _insert_inventory, _insert_customers,
        _insert_transportation, _insert_purchase_orders, _insert_deliveries,
        _insert_customer_orders, _insert_supplier_performance,
    )
    tables = generate(n_suppliers=60, n_products=120, n_customers=80,
                      n_pos=400, n_cos=500)
    with db_module.db_session() as session:
        _insert_suppliers(session, tables["suppliers"])
        _insert_products(session, tables["products"])
        _insert_inventory(session, tables["inventory"])
        _insert_customers(session, tables["customers"])
        _insert_transportation(session, tables["transportation"])
        _insert_purchase_orders(session, tables["purchase_orders"], tables["purchase_order_items"])
        _insert_deliveries(session, tables["deliveries"])
        _insert_customer_orders(session, tables["customer_orders"], tables["customer_order_items"])
        _insert_supplier_performance(session, tables["supplier_performance"])
        if not session.query(User).filter(User.username == "admin").first():
            session.add_all([
                User(username="admin", email="admin@test.local", full_name="Admin",
                     hashed_password=hash_password("admin123"), role=UserRole.admin, is_active=True),
                User(username="approver", email="approver@test.local", full_name="Approver",
                     hashed_password=hash_password("approver123"), role=UserRole.approver, is_active=True),
                User(username="analyst", email="analyst@test.local", full_name="Analyst",
                     hashed_password=hash_password("analyst123"), role=UserRole.analyst, is_active=True),
            ])
            session.commit()


@pytest.fixture(scope="session", autouse=True)
def seeded_db_once():
    """Create schema + seed exactly once per test session."""
    init_db()
    _seed_once()
    yield
    # cleanup temp db file
    try:
        _test_engine.dispose()
        if os.path.exists(_TEST_DB):
            os.remove(_TEST_DB)
    except Exception:
        pass


@pytest.fixture()
def db():
    """A plain session against the shared DB (services commit here)."""
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded_db(db):
    """Session for tests that read/extend seeded data (same shared DB)."""
    # ensure demo users exist for the per-test session
    if not db.query(User).filter(User.username == "admin").first():
        db.add_all([
            User(username="admin", email="admin@test.local", full_name="Admin",
                 hashed_password=hash_password("admin123"), role=UserRole.admin, is_active=True),
            User(username="approver", email="approver@test.local", full_name="Approver",
                 hashed_password=hash_password("approver123"), role=UserRole.approver, is_active=True),
        ])
        db.commit()
    return db


@pytest.fixture()
def client(seeded_db):
    """TestClient with get_db -> shared session and a stub admin user."""
    from app.main import app
    from app.deps import get_current_user

    def _override_db():
        try:
            yield seeded_db
        finally:
            pass

    def _override_user():
        return seeded_db.query(User).filter(User.username == "admin").first()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
