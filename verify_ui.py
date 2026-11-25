"""Verify the new UI assets load correctly from the FastAPI server."""
import subprocess, os, tempfile, sys

py = r"C:\Users\impana\AppData\Local\Python\pythoncore-3.14-64\python.exe"
backend = r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\backend"

code = r'''
import os, tempfile
db = os.path.join(tempfile.gettempdir(), "sc_ui_test.db")
if os.path.exists(db): os.remove(db)
os.environ["DATABASE_URL"] = f"sqlite:///{db}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["REDIS_URL"] = ""
os.environ["CHECKPOINT_DB_URL"] = ""

from fastapi.testclient import TestClient
from app.main import app

checks = {}
with TestClient(app, raise_server_exceptions=True) as client:
    # HTML at root
    r = client.get("/")
    checks["/"] = r.status_code
    html = r.text
    checks["has_login_page"]   = 'id="login-page"' in html
    checks["has_app_shell"]    = 'id="app-shell"' in html
    checks["has_view_dashboard"] = 'id="view-dashboard"' in html
    checks["has_sim_type_options"] = '<option value="supplier_delay">' in html
    checks["has_severity_options"] = '<option value="high"' in html

    # Static assets
    r = client.get("/css/styles.css")
    checks["/css/styles.css"] = r.status_code
    checks["css_has_navy"] = "--navy-950" in r.text

    r = client.get("/js/app.js")
    checks["/js/app.js"] = r.status_code
    checks["js_has_loadDashboard"] = "loadDashboard" in r.text

    r = client.get("/js/api.js")
    checks["/js/api.js"] = r.status_code

    r = client.get("/js/charts.js")
    checks["/js/charts.js"] = r.status_code
    checks["charts_has_palette"] = "palette" in r.text

    # Login works
    r = client.post("/api/v1/auth/login",
        data={"username":"admin","password":"admin123"},
        headers={"Content-Type":"application/x-www-form-urlencoded"})
    checks["login_200"] = r.status_code
    token = r.json().get("access_token","") if r.status_code == 200 else ""
    h = {"Authorization": f"Bearer {token}"}

    # Key API endpoints
    for url in ["/api/v1/dashboard/summary", "/api/v1/master/suppliers?limit=3",
                "/api/v1/disruptions", "/api/v1/approvals/pending"]:
        checks[url] = client.get(url, headers=h).status_code

print("=" * 55)
all_ok = True
for k, v in checks.items():
    if isinstance(v, bool):
        status = "OK " if v else "FAIL"
        if not v: all_ok = False
    elif isinstance(v, int):
        status = "OK " if v < 300 else "FAIL"
        if v >= 300: all_ok = False
    else:
        status = "OK "
    print(f"  {status}  {k}: {v}")
print("=" * 55)
print("ALL OK" if all_ok else "FAILURES DETECTED")
import sys; sys.exit(0 if all_ok else 1)
'''

result = subprocess.run([py, "-c", code], cwd=backend, capture_output=True, text=True, timeout=120)
print(result.stdout[-3000:])
if result.returncode != 0 and result.stderr:
    lines = [l for l in result.stderr.split("\n") if l and not l.startswith("{")]
    if lines: print("STDERR:", "\n".join(lines[:20]))
sys.exit(result.returncode)
