import subprocess, os, tempfile, sys, re

py = r"C:\Users\impana\AppData\Local\Python\pythoncore-3.14-64\python.exe"
backend = r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\backend"

code = """
import os, tempfile, re

db = os.path.join(tempfile.gettempdir(), "sc_nav_test.db")
if os.path.exists(db): os.remove(db)
os.environ["DATABASE_URL"] = "sqlite:///" + db
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["REDIS_URL"] = ""
os.environ["CHECKPOINT_DB_URL"] = ""

from fastapi.testclient import TestClient
from app.main import app

issues = []

with TestClient(app, raise_server_exceptions=False) as client:
    r = client.post("/api/v1/auth/login",
        data={"username":"admin","password":"admin123"},
        headers={"Content-Type":"application/x-www-form-urlencoded"})
    assert r.status_code == 200, "Login failed: " + str(r.status_code)
    h = {"Authorization": "Bearer " + r.json()["access_token"]}

    html = client.get("/").text
    view_ids = re.findall(r'id="(view-[^"]+)"', html)
    print("View sections in HTML:", view_ids)

    app_js = client.get("/js/app.js").text
    route_ids = re.findall(r"\\{ id: '([^']+)'", app_js)
    print("Routes in app.js:", route_ids)

    for rid in route_ids:
        expected = "view-" + rid
        if expected not in view_ids:
            issues.append("MISSING VIEW: route '" + rid + "' needs <section id='" + expected + "'> but not in HTML")

    api_checks = [
        ("GET", "/api/v1/dashboard/summary"),
        ("GET", "/api/v1/dashboard/risk-alerts"),
        ("GET", "/api/v1/dashboard/supplier-performance"),
        ("GET", "/api/v1/dashboard/demand-forecast"),
        ("GET", "/api/v1/dashboard/low-inventory"),
        ("GET", "/api/v1/master/suppliers?limit=5"),
        ("GET", "/api/v1/master/inventory?limit=5"),
        ("GET", "/api/v1/master/products?limit=5"),
        ("GET", "/api/v1/master/purchase-orders?limit=5"),
        ("GET", "/api/v1/forecasting/demand?horizon_months=3"),
        ("GET", "/api/v1/forecasting/shortages?horizon_months=3"),
        ("GET", "/api/v1/recovery/plans?limit=5"),
        ("GET", "/api/v1/approvals/pending"),
        ("GET", "/api/v1/approvals?limit=5"),
        ("GET", "/api/v1/recovery/decisions?limit=5"),
    ]
    for method, url in api_checks:
        r2 = client.request(method, url, headers=h)
        s = r2.status_code
        marker = "OK " if s < 300 else "FAIL"
        if s >= 300:
            issues.append("API " + str(s) + ": " + method + " " + url)
        print("  " + marker + " " + str(s) + "  " + url)

    api_js = client.get("/js/api.js").text
    has_suppliers = "suppliers:" in api_js
    has_navigate = "function navigate(" in app_js
    has_case_sup = "case 'suppliers'" in app_js
    has_load_sup = "function loadSuppliers(" in app_js or "async function loadSuppliers(" in app_js

    print("")
    print("api.js has API.suppliers:    " + str(has_suppliers))
    print("app.js navigate() exists:    " + str(has_navigate))
    print("app.js case suppliers:       " + str(has_case_sup))
    print("app.js loadSuppliers():      " + str(has_load_sup))

print("")
print("=" * 55)
if issues:
    print("ISSUES FOUND:")
    for iss in issues:
        print("  BAD: " + iss)
else:
    print("No structural issues found.")
print("=" * 55)
"""

result = subprocess.run([py, "-c", code], cwd=backend, capture_output=True, text=True, timeout=120)
print(result.stdout[-4000:])
if result.returncode != 0:
    lines = [l for l in result.stderr.split("\n") if l and not l.startswith("{")]
    if lines: print("STDERR:", "\n".join(lines[:20]))
