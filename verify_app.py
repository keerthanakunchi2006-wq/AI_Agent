"""Verify the FastAPI app boots, DB seeds, and key endpoints respond."""
import sys, os, tempfile, subprocess

py = r"C:\Users\impana\AppData\Local\Python\pythoncore-3.14-64\python.exe"
backend = r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\backend"
out = r"C:\Users\impana\AI_Project\AI_Agent\verify_results.txt"

code = '''
import os, tempfile
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.gettempdir(), "sc_verify.db")
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["REDIS_URL"] = ""
os.environ["CHECKPOINT_DB_URL"] = ""

from fastapi.testclient import TestClient
from app.database import init_db, db_session
from app.seed import seed_database
from app.main import app
from app.auth import hash_password, create_access_token

# boot
init_db()

# seed small dataset
from scripts.generate_dataset import generate
from app.seed import (
    _insert_suppliers, _insert_products, _insert_inventory, _insert_customers,
    _insert_transportation, _insert_purchase_orders, _insert_deliveries,
    _insert_customer_orders, _insert_supplier_performance,
)
from app.models import User, UserRole
from app import database as db_module
tables = generate(n_suppliers=20, n_products=40, n_customers=20, n_pos=80, n_cos=60)
with db_module.db_session() as db:
    _insert_suppliers(db, tables["suppliers"])
    _insert_products(db, tables["products"])
    _insert_inventory(db, tables["inventory"])
    _insert_customers(db, tables["customers"])
    _insert_transportation(db, tables["transportation"])
    _insert_purchase_orders(db, tables["purchase_orders"], tables["purchase_order_items"])
    _insert_deliveries(db, tables["deliveries"])
    _insert_customer_orders(db, tables["customer_orders"], tables["customer_order_items"])
    _insert_supplier_performance(db, tables["supplier_performance"])
    db.add(User(username="admin", email="admin@test.local", full_name="Admin",
                hashed_password=hash_password("admin123"), role=UserRole.admin, is_active=True))
    db.commit()

results = {}
with TestClient(app, raise_server_exceptions=False) as client:
    # get token
    r = client.post("/api/v1/auth/login",
                    data={"username":"admin","password":"admin123"},
                    headers={"Content-Type":"application/x-www-form-urlencoded"})
    results["login"] = r.status_code
    token = r.json().get("access_token","") if r.status_code==200 else ""
    h = {"Authorization": f"Bearer {token}"}

    endpoints = [
        ("GET",  "/health",                              None),
        ("GET",  "/api/v1/dashboard/summary",            h),
        ("GET",  "/api/v1/dashboard/risk-alerts",        h),
        ("GET",  "/api/v1/dashboard/supplier-performance", h),
        ("GET",  "/api/v1/dashboard/demand-forecast",    h),
        ("GET",  "/api/v1/dashboard/low-inventory",      h),
        ("GET",  "/api/v1/master/suppliers?limit=5",     h),
        ("GET",  "/api/v1/master/products?limit=5",      h),
        ("GET",  "/api/v1/master/inventory?limit=5",     h),
        ("GET",  "/api/v1/master/customers?limit=5",     h),
        ("GET",  "/api/v1/master/purchase-orders?limit=5", h),
        ("GET",  "/api/v1/master/deliveries?limit=5",    h),
        ("GET",  "/api/v1/master/transportation",        h),
        ("GET",  "/api/v1/disruptions",                  h),
        ("GET",  "/api/v1/recovery/plans",               h),
        ("GET",  "/api/v1/approvals",                    h),
        ("GET",  "/api/v1/approvals/pending",            h),
        ("GET",  "/api/v1/recovery/decisions",           h),
        ("GET",  "/api/v1/forecasting/demand",           h),
        ("GET",  "/api/v1/forecasting/shortages",        h),
    ]
    for method, url, headers in endpoints:
        r = client.request(method, url, headers=headers or {})
        results[url] = r.status_code

    # test what-if simulation
    sup_id = client.get("/api/v1/master/suppliers?limit=1", headers=h).json()[0]["id"]
    r = client.post("/api/v1/simulations/what-if",
        json={"type":"supplier_unavailable","severity":"high","supplier_id":sup_id,
              "estimated_delay_days":10,"description":"test"},
        headers=h)
    results["POST /simulations/what-if"] = r.status_code

    # test full workflow
    r = client.post("/api/v1/disruptions/run",
        json={"disruption":{"type":"supplier_unavailable","severity":"high",
              "supplier_id":sup_id,"estimated_delay_days":10,
              "description":"verify test"},"run_optimization":True,"request_approval":False},
        headers=h)
    results["POST /disruptions/run"] = r.status_code
    if r.status_code == 200:
        body = r.json()
        results["workflow_thread_id"] = bool(body.get("thread_id"))
        results["workflow_disruption_id"] = body.get("disruption_id")
        results["workflow_status"] = body.get("status")
        results["workflow_has_plan"] = body.get("recovery_plan") is not None
    else:
        results["workflow_error"] = r.text[:500]

    # test recovery alternatives
    prod_id = client.get("/api/v1/master/products?limit=1", headers=h).json()[0]["id"]
    r = client.get(f"/api/v1/recovery/alternatives?product_id={prod_id}&quantity=200", headers=h)
    results["GET /recovery/alternatives"] = r.status_code

print("=" * 60)
for k, v in results.items():
    status = "OK" if (isinstance(v, int) and v < 300) or v is True else f"FAIL({v})"
    print(f"  {status:12s}  {k}")
print("=" * 60)

failures = [k for k,v in results.items() if isinstance(v, int) and v >= 300]
if failures:
    print(f"FAILURES: {failures}")
    sys.exit(1)
else:
    print("ALL ENDPOINTS OK")
'''

result = subprocess.run(
    [py, "-c", code],
    cwd=backend,
    capture_output=True,
    text=True,
    timeout=120,
)
output = result.stdout + "\n---STDERR---\n" + result.stderr
with open(out, "w", encoding="utf-8") as f:
    f.write(output)
print(output[-6000:])
print("RC:", result.returncode)
