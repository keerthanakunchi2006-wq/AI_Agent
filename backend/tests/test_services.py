"""Tests for the deterministic services: monitoring, impact analysis,
forecasting, supplier evaluation, optimisation, approval, tracking."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from app.models import (
    Supplier, Product, Inventory, PurchaseOrder, PurchaseOrderItem, POStatus,
    Disruption, DisruptionType, DisruptionSeverity, CustomerOrder,
    CustomerOrderItem, Customer, TransportationRoute, Delivery, DeliveryStatus,
)
from app.services import monitoring, impact_analysis, forecasting, supplier_eval
from app.services import optimization, approval, tracking


def test_detect_delays_finds_late_pos(seeded_db):
    # create a deliberately late PO
    sup = seeded_db.query(Supplier).first()
    po_num = f"PO-LATE-{uuid.uuid4().hex[:8].upper()}"
    po = PurchaseOrder(
        po_number=po_num, supplier_id=sup.id, status=POStatus.in_transit,
        order_date=datetime.utcnow() - timedelta(days=40),
        expected_delivery=datetime.utcnow() - timedelta(days=10),
        total_cost=1000, transport_cost=50,
    )
    seeded_db.add(po)
    seeded_db.commit()
    delays = monitoring.detect_delays(seeded_db)
    assert any(d["po_number"] == po_num for d in delays)
    late = next(d for d in delays if d["po_number"] == po_num)
    assert late["days_late"] > 0


def test_at_risk_suppliers(seeded_db):
    risk = monitoring.identify_at_risk_suppliers(seeded_db, threshold=0.95)
    # at least some suppliers fall below 0.95 on-time in synthetic data
    assert isinstance(risk, list)
    for r in risk:
        assert "risk_factors" in r
        assert r["supplier_id"]


def test_impact_analysis_supplier_unavailable(seeded_db):
    sup = seeded_db.query(Supplier).first()
    d = Disruption(
        type=DisruptionType.supplier_unavailable, severity=DisruptionSeverity.high,
        supplier_id=sup.id, description="Strike at supplier plant",
    )
    seeded_db.add(d)
    seeded_db.commit()
    result = impact_analysis.analyze_impact(seeded_db, d)
    assert result["affected_supplier_id"] == sup.id
    assert result["affected_product_count"] >= 0
    assert "inventory_gap" in result
    assert "total_shortfall" in result


def test_impact_analysis_supplier_delay_linked_po(seeded_db):
    sup = seeded_db.query(Supplier).first()
    prod = seeded_db.query(Product).filter(Product.primary_supplier_id == sup.id).first()
    if not prod:
        pytest.skip("no product for supplier")
    po_num = f"PO-IMPACT-{uuid.uuid4().hex[:8].upper()}"
    po = PurchaseOrder(
        po_number=po_num, supplier_id=sup.id, status=POStatus.delayed,
        order_date=datetime.utcnow() - timedelta(days=20),
        expected_delivery=datetime.utcnow() - timedelta(days=3),
        total_cost=500, transport_cost=20,
    )
    seeded_db.add(po)
    seeded_db.flush()
    seeded_db.add(PurchaseOrderItem(po_id=po.id, product_id=prod.id, quantity=100,
                                    unit_cost=5, line_total=500))
    seeded_db.commit()
    d = Disruption(
        type=DisruptionType.supplier_delay, severity=DisruptionSeverity.medium,
        supplier_id=sup.id, po_id=po.id, estimated_delay_days=8,
    )
    seeded_db.add(d)
    seeded_db.commit()
    result = impact_analysis.analyze_impact(seeded_db, d)
    assert result["affected_order_count"] == 1
    assert prod.id in result["affected_product_ids"]
    assert result["committed_quantity"] == 100


def test_forecasting_returns_predictions(seeded_db):
    forecasts = forecasting.forecast_demand(seeded_db, horizon_months=3)
    assert isinstance(forecasts, list)
    if forecasts:
        f = forecasts[0]
        assert "product_id" in f and "predicted_demand" in f
        assert f["predicted_demand"] >= 0
        assert f["lower_bound"] <= f["predicted_demand"] <= f["upper_bound"]


def test_supplier_evaluation_ranks_and_scores(seeded_db):
    product = seeded_db.query(Product).first()
    alts = supplier_eval.evaluate_alternatives(seeded_db, product.id, 250)
    assert len(alts) > 0
    # scores descending
    scores = [a["score"] for a in alts]
    assert scores == sorted(scores, reverse=True)
    best = alts[0]
    assert best["total_cost"] > 0
    assert 0 <= best["score"] <= 1.0


def test_supplier_evaluation_excludes_supplier(seeded_db):
    product = seeded_db.query(Product).first()
    all_alts = supplier_eval.evaluate_alternatives(seeded_db, product.id, 100)
    if not all_alts:
        pytest.skip("no alternatives")
    excluded = all_alts[0]["supplier_id"]
    filtered = supplier_eval.evaluate_alternatives(seeded_db, product.id, 100, exclude_supplier_id=excluded)
    assert excluded not in [a["supplier_id"] for a in filtered]


def test_optimization_generates_plans(seeded_db):
    sup = seeded_db.query(Supplier).first()
    products = seeded_db.query(Product).filter(Product.primary_supplier_id == sup.id).limit(3).all()
    if not products:
        pytest.skip("no products for supplier")
    gap_rows = [{"product_id": p.id, "shortfall": 300.0} for p in products]
    d = Disruption(type=DisruptionType.supplier_unavailable, severity=DisruptionSeverity.high,
                   supplier_id=sup.id)
    seeded_db.add(d)
    seeded_db.commit()
    orig_plan, orig_summary = optimization.generate_original_plan(
        seeded_db, d, [p.id for p in products], gap_rows, sup.id)
    opt_plan, opt_summary = optimization.generate_recovery_plan(
        seeded_db, d, [p.id for p in products], gap_rows, exclude_supplier_id=sup.id)
    assert orig_plan.total_cost >= 0
    assert opt_plan.total_cost >= 0
    assert opt_plan.supplier_count >= 1
    assert len(opt_plan.items) >= 1


def test_approval_threshold_and_decision(seeded_db):
    sup = seeded_db.query(Supplier).first()
    d = Disruption(type=DisruptionType.supplier_unavailable, supplier_id=sup.id)
    seeded_db.add(d)
    seeded_db.commit()
    plan, _ = optimization.generate_recovery_plan(seeded_db, d, [],
                                                   [{"product_id": seeded_db.query(Product).first().id, "shortfall": 5000.0}],
                                                   exclude_supplier_id=sup.id)
    # large plan should require approval
    req = approval.request_approval(seeded_db, plan, requester="test")
    assert req.status.value == "pending"
    decided = approval.decide_approval(seeded_db, req.id, "approved", "test_approver", "ok")
    assert decided.status.value == "approved"
    seeded_db.refresh(plan)
    assert plan.status == "approved"


def test_tracking_records_decisions(seeded_db):
    rec = tracking.record_decision(seeded_db, "test_entity", 1, "created", "tester", "unit")
    assert rec.id
    hist = tracking.decision_history(seeded_db, entity_type="test_entity")
    assert any(h.id == rec.id for h in hist)
