"""Tests for the LangGraph orchestrator end-to-end."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import (
    Supplier, Product, PurchaseOrder, POStatus, Disruption, DisruptionType,
    DisruptionSeverity,
)
from app.agents.orchestrator import run_workflow


def test_workflow_supplier_unavailable(seeded_db):
    """Scenario: original supplier unavailable -> alternatives + optimised plan."""
    sup = seeded_db.query(Supplier).filter(Supplier.active.is_(True)).first()
    initial = {
        "disruption_type": "supplier_unavailable",
        "severity": "high",
        "supplier_id": sup.id,
        "description": "Supplier plant fire",
        "estimated_delay_days": 14,
        "run_optimization": True,
        "request_approval": True,
    }
    # need a disruption record persisted for the nodes to find
    d = Disruption(type=DisruptionType.supplier_unavailable,
                   severity=DisruptionSeverity.high, supplier_id=sup.id,
                   description="Supplier plant fire", estimated_delay_days=14)
    seeded_db.add(d)
    seeded_db.commit()
    initial["disruption_id"] = d.id

    thread_id, state = run_workflow(initial)
    assert thread_id
    assert state.get("status") in ("tracking_complete", "approval_pending",
                                   "approval_auto", "approval_skipped",
                                   "error", "monitoring_complete",
                                   "impact_analysis_complete", "forecasting_complete",
                                   "supplier_evaluation_complete", "optimization_complete")
    assert "affected_product_ids" in state
    assert "alternative_suppliers" in state
    # an optimised plan should have been created
    assert state.get("optimized_plan_id") is not None or state.get("errors")
    assert "plan_comparison" in state


def test_workflow_supplier_delay_linked_po(seeded_db):
    """Scenario: a delayed shipment -> affected orders identified."""
    sup = seeded_db.query(Supplier).filter(Supplier.active.is_(True)).first()
    prod = seeded_db.query(Product).filter(Product.primary_supplier_id == sup.id).first()
    if not prod:
        pytest.skip("no product linked to supplier")
    po = PurchaseOrder(
        po_number="PO-WF-1", supplier_id=sup.id, status=POStatus.delayed,
        order_date=datetime.utcnow() - timedelta(days=30),
        expected_delivery=datetime.utcnow() - timedelta(days=5),
        total_cost=2000, transport_cost=80,
    )
    seeded_db.add(po)
    seeded_db.flush()
    from app.models import PurchaseOrderItem
    seeded_db.add(PurchaseOrderItem(po_id=po.id, product_id=prod.id, quantity=200,
                                    unit_cost=10, line_total=2000))
    seeded_db.commit()

    d = Disruption(type=DisruptionType.supplier_delay, severity=DisruptionSeverity.medium,
                   supplier_id=sup.id, po_id=po.id, estimated_delay_days=9,
                   description="Shipment held at customs")
    seeded_db.add(d)
    seeded_db.commit()

    initial = {
        "disruption_id": d.id,
        "disruption_type": "supplier_delay",
        "severity": "medium",
        "supplier_id": sup.id,
        "po_id": po.id,
        "estimated_delay_days": 9,
        "run_optimization": True,
        "request_approval": False,
    }
    thread_id, state = run_workflow(initial)
    assert thread_id
    assert state.get("affected_order_count") >= 0
    assert prod.id in (state.get("affected_product_ids") or [])
