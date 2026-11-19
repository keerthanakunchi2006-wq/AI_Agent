"""HTTP API tests via FastAPI TestClient (auth overridden in conftest)."""
from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_metrics(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "sc_" in r.text


def test_dashboard_summary(client):
    r = client.get("/api/v1/dashboard/summary")
    assert r.status_code == 200
    body = r.json()
    for k in ["total_suppliers", "total_products", "active_purchase_orders",
              "delayed_shipments", "low_inventory_count", "open_disruptions",
              "pending_approvals", "total_inventory_value", "on_time_delivery_rate"]:
        assert k in body
    assert body["total_suppliers"] > 0


def test_risk_alerts(client):
    r = client.get("/api/v1/dashboard/risk-alerts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_suppliers_list(client):
    r = client.get("/api/v1/master/suppliers?limit=10")
    assert r.status_code == 200
    assert len(r.json()) <= 10


def test_products_list(client):
    r = client.get("/api/v1/master/products?limit=5")
    assert r.status_code == 200
    assert len(r.json()) == 5


def test_inventory_list(client):
    r = client.get("/api/v1/master/inventory?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_purchase_orders(client):
    r = client.get("/api/v1/master/purchase-orders?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_forecasting_endpoints(client):
    r = client.get("/api/v1/forecasting/demand?horizon_months=3")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_alternatives(client):
    # pick a real product id
    pid = client.get("/api/v1/master/products?limit=1").json()[0]["id"]
    r = client.get(f"/api/v1/recovery/alternatives?product_id={pid}&quantity=200")
    assert r.status_code == 200
    alts = r.json()
    assert len(alts) > 0
    scores = [a["score"] for a in alts]
    assert scores == sorted(scores, reverse=True)


def test_what_if_simulation(client):
    sup_id = client.get("/api/v1/master/suppliers?limit=1").json()[0]["id"]
    payload = {
        "type": "supplier_unavailable",
        "severity": "high",
        "supplier_id": sup_id,
        "estimated_delay_days": 12,
        "description": "Test disruption",
    }
    r = client.post("/api/v1/simulations/what-if", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scenario"]
    assert "original_plan_cost" in body
    assert "optimized_plan_cost" in body
    assert isinstance(body["alternatives"], list)


def test_disruption_run_workflow(client):
    sup_id = client.get("/api/v1/master/suppliers?limit=1").json()[0]["id"]
    payload = {
        "disruption": {
            "type": "supplier_unavailable",
            "severity": "high",
            "supplier_id": sup_id,
            "estimated_delay_days": 10,
            "description": "API workflow test",
        },
        "run_optimization": True,
        "request_approval": False,
    }
    r = client.post("/api/v1/disruptions/run", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["disruption_id"] > 0
    assert body["thread_id"]
    assert "optimization" in body
    assert "summary" in body


def test_approvals_list(client):
    r = client.get("/api/v1/approvals?limit=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_decisions_list(client):
    r = client.get("/api/v1/recovery/decisions?limit=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_recovery_plans_list(client):
    r = client.get("/api/v1/recovery/plans?limit=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_auth_login_with_demo_user(client):
    # demo users were seeded in seeded_db fixture
    from app.auth import create_access_token
    token = create_access_token("admin", "admin")
    # verify the token decodes
    from app.auth import decode_access_token
    payload = decode_access_token(token)
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"
