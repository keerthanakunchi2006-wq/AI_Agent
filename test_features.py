"""
Test Disruption Simulation and Supplier Comparison end-to-end.
Hits the real API and reports exactly what succeeds and what fails.
"""
import subprocess, os, tempfile

py = r"C:\Users\impana\AppData\Local\Python\pythoncore-3.14-64\python.exe"
backend = r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\backend"

code = """
import os, tempfile, json

db = os.path.join(tempfile.gettempdir(), "sc_feat.db")
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
    h = {"Authorization": "Bearer " + r.json()["access_token"]}

    # ====== DISRUPTION SIMULATION ======
    print("\\n=== DISRUPTION SIMULATION ===")

    # Get a supplier to use
    sup_r = client.get("/api/v1/master/suppliers?limit=3", headers=h)
    print("GET /master/suppliers:", sup_r.status_code)
    supplier_id = sup_r.json()[0]["id"] if sup_r.status_code == 200 else None

    # Test each disruption type
    for dtype in ["supplier_unavailable", "supplier_delay", "demand_spike", "inventory_shortage", "transport_disruption"]:
        payload = {
            "type": dtype,
            "severity": "high",
            "supplier_id": supplier_id,
            "estimated_delay_days": 10,
            "description": "test " + dtype,
        }
        r2 = client.post("/api/v1/simulations/what-if",
            json=payload, headers=h)
        if r2.status_code == 200:
            body = r2.json()
            print("OK  POST /simulations/what-if type=" + dtype)
            print("    -> affected_orders=" + str(body.get("affected_orders"))
                  + " affected_products=" + str(body.get("affected_products"))
                  + " original_plan_cost=" + str(body.get("original_plan_cost"))
                  + " alternatives=" + str(len(body.get("alternatives", []))))
        else:
            issues.append("FAIL " + str(r2.status_code) + " POST /simulations/what-if type=" + dtype)
            print("FAIL", r2.status_code, r2.text[:300])

    # Test without supplier_id (demand_spike type)
    r3 = client.post("/api/v1/simulations/what-if",
        json={"type":"demand_spike","severity":"medium","estimated_delay_days":5,"description":"test"},
        headers=h)
    print("POST without supplier_id:", r3.status_code, "(demand_spike)")
    if r3.status_code != 200:
        issues.append("FAIL demand_spike without supplier: " + str(r3.status_code))

    # ====== SUPPLIER COMPARISON ======
    print("\\n=== SUPPLIER COMPARISON ===")

    # Products must load
    prod_r = client.get("/api/v1/master/products?limit=5", headers=h)
    print("GET /master/products:", prod_r.status_code, "count=" + str(len(prod_r.json()) if prod_r.status_code==200 else 0))
    if prod_r.status_code != 200:
        issues.append("FAIL GET /master/products: " + str(prod_r.status_code))

    # Test alternatives for each of first 3 products
    if prod_r.status_code == 200:
        products = prod_r.json()
        for prod in products[:3]:
            pid = prod["id"]
            alt_r = client.get("/api/v1/recovery/alternatives?product_id=" + str(pid) + "&quantity=200", headers=h)
            if alt_r.status_code == 200:
                alts = alt_r.json()
                # check scores are present and sorted descending
                scores = [a["score"] for a in alts]
                is_sorted = scores == sorted(scores, reverse=True)
                print("OK  GET /recovery/alternatives product=" + str(pid)
                      + " count=" + str(len(alts))
                      + " scores_sorted=" + str(is_sorted))
                if alts:
                    # verify required fields exist
                    a0 = alts[0]
                    for field in ["supplier_id","supplier_name","country","rating","on_time_rate",
                                  "lead_time_days","unit_cost","transport_cost","total_cost",
                                  "delivery_days","delay_vs_original","score"]:
                        if field not in a0:
                            issues.append("MISSING FIELD '" + field + "' in alternatives response")
            else:
                issues.append("FAIL GET /recovery/alternatives product=" + str(pid) + ": " + str(alt_r.status_code))
                print("FAIL", alt_r.status_code, alt_r.text[:200])

    # Test with exclude_supplier_id
    if prod_r.status_code == 200 and products:
        pid = products[0]["id"]
        all_alts = client.get("/api/v1/recovery/alternatives?product_id=" + str(pid) + "&quantity=200", headers=h).json()
        if all_alts:
            excl = all_alts[0]["supplier_id"]
            filtered = client.get("/api/v1/recovery/alternatives?product_id=" + str(pid)
                                  + "&quantity=200&exclude_supplier_id=" + str(excl), headers=h).json()
            excluded_ids = [a["supplier_id"] for a in filtered]
            if excl not in excluded_ids:
                print("OK  exclude_supplier_id works")
            else:
                issues.append("exclude_supplier_id not filtering: supplier " + str(excl) + " still in results")

    print("\\n" + "="*55)
    if issues:
        for iss in issues:
            print("ISSUE:", iss)
    else:
        print("ALL FEATURE TESTS PASSED")
    print("="*55)
"""

result = subprocess.run([py, "-c", code], cwd=backend, capture_output=True, text=True, timeout=120)
output = result.stdout + result.stderr
# filter out JSON log lines
lines = [l for l in output.split("\n") if not l.startswith("{") or "ISSUE" in l or "FAIL" in l or "OK" in l]
print("\n".join(lines[-60:]))
print("RC:", result.returncode)
