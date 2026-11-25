"""Verify the app starts cleanly using its actual startup path (lifespan)."""
import subprocess, os, sys

py = r"C:\Users\impana\AppData\Local\Python\pythoncore-3.14-64\python.exe"
backend = r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\backend"

code = r'''
import os, tempfile, sys
# point at a fresh temp DB so we seed from scratch
db_path = os.path.join(tempfile.gettempdir(), "sc_startup_test.db")
if os.path.exists(db_path):
    os.remove(db_path)
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["REDIS_URL"] = ""
os.environ["CHECKPOINT_DB_URL"] = ""

from fastapi.testclient import TestClient
from app.main import app

print("--- Starting app with SEED_DEMO_DATA=true ---")
with TestClient(app, raise_server_exceptions=True) as client:
    r = client.get("/health")
    print(f"  /health -> {r.status_code} {r.json()}")
    assert r.status_code == 200

    r = client.post("/api/v1/auth/login",
                    data={"username": "admin", "password": "admin123"},
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    print(f"  login  -> {r.status_code}")
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/dashboard/summary", headers=h)
    s = r.json()
    print(f"  dashboard/summary -> {r.status_code}")
    print(f"    suppliers={s['total_suppliers']} products={s['total_products']} POs={s['active_purchase_orders']}")
    assert r.status_code == 200
    assert s["total_suppliers"] > 0, "No suppliers seeded!"
    assert s["total_products"] > 0, "No products seeded!"

print("--- Startup verification PASSED ---")
'''

result = subprocess.run(
    [py, "-c", code],
    cwd=backend,
    capture_output=True,
    text=True,
    timeout=120,
)
print(result.stdout[-3000:])
if result.stderr:
    # filter out normal JSON log lines
    lines = [l for l in result.stderr.split("\n") if l and not l.startswith("{")]
    if lines:
        print("STDERR:", "\n".join(lines[:20]))
print("RC:", result.returncode)
sys.exit(result.returncode)
