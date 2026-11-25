import subprocess, os, tempfile, re

py = r"C:\Users\impana\AppData\Local\Python\pythoncore-3.14-64\python.exe"
backend = r"C:\Users\impana\AI_Project\AI_Agent\AI_Agent\backend"

code = """
import os, tempfile, re

db = os.path.join(tempfile.gettempdir(), "sc_nav3.db")
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

    css = client.get("/css/styles.css").text

    # 1. No display:none on sidebar
    if ".sidebar { display: none;" in css or ".sidebar{display:none" in css:
        issues.append("CSS: sidebar has display:none")
    else:
        print("OK  no display:none on sidebar")

    # 2. Sidebar is a flex item (not sticky)
    if "position: sticky" in css and "sidebar" in css[css.find("position: sticky")-200:css.find("position: sticky")]:
        issues.append("CSS: sidebar still uses position:sticky")
    else:
        print("OK  sidebar is not position:sticky")

    # 3. .sidebar.collapsed hides it
    if ".sidebar.collapsed" in css:
        print("OK  .sidebar.collapsed rule present")
    else:
        issues.append("CSS: .sidebar.collapsed missing")

    # 4. mobile uses transform
    if "transform: translateX(-100%)" in css:
        print("OK  mobile uses transform for hiding")
    else:
        issues.append("CSS: mobile transform rule missing")

    # 5. HTML structure
    html = client.get("/").text
    for el in ['id="sidebar"', 'id="nav"', 'id="nav-toggle"', 'id="app-shell"']:
        if el in html:
            print("OK  HTML has " + el)
        else:
            issues.append("HTML missing: " + el)

    # 6. All routes have view sections
    app_js = client.get("/js/app.js").text
    route_ids = re.findall(r"\\{ id: '([^']+)'", app_js)
    view_ids = set(re.findall(r'id="(view-[^"]+)"', html))
    for rid in route_ids:
        vid = "view-" + rid
        if vid not in view_ids:
            issues.append("Missing: " + vid)
    print("OK  all " + str(len(route_ids)) + " routes have view sections: " + str(route_ids))

    # 7. JS nav toggle handler
    if "nav-toggle" in app_js and "classList.toggle" in app_js:
        print("OK  hamburger handler registered")
    else:
        issues.append("JS: hamburger handler missing")

    # 8. onclick on nav items
    if "item.onclick" in app_js:
        print("OK  nav items have onclick")
    else:
        issues.append("JS: nav item onclick missing")

    # 9. All APIs that the views use
    for url in [
        "/api/v1/dashboard/summary",
        "/api/v1/master/suppliers?limit=3",
        "/api/v1/master/inventory?limit=3",
        "/api/v1/master/products?limit=3",
        "/api/v1/master/purchase-orders?limit=3",
        "/api/v1/forecasting/demand?horizon_months=1",
        "/api/v1/forecasting/shortages?horizon_months=1",
        "/api/v1/recovery/plans?limit=3",
        "/api/v1/approvals/pending",
        "/api/v1/recovery/decisions?limit=3",
    ]:
        s = client.get(url, headers=h).status_code
        if s >= 300:
            issues.append("API FAIL " + str(s) + ": " + url)
        else:
            print("OK  API " + str(s) + ": " + url)

print("")
print("=" * 60)
if issues:
    for iss in issues:
        print("ISSUE: " + iss)
    import sys; sys.exit(1)
else:
    print("ALL CHECKS PASSED")
print("=" * 60)
"""

result = subprocess.run([py, "-c", code], cwd=backend, capture_output=True, text=True, timeout=120)
print(result.stdout[-3000:])
if result.returncode != 0:
    lines = [l for l in result.stderr.split("\n") if l and not l.startswith("{")]
    if lines: print("ERR:", "\n".join(lines[:15]))
