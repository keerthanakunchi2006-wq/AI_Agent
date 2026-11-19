"""Dashboard KPIs, risk alerts and chart data."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..services import dashboard as dash_svc
from ..schemas import DashboardSummary, RiskAlert, SupplierPerformancePoint, DemandForecastPoint, InventoryOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary, summary="KPI summary")
def summary(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return dash_svc.get_summary(db)


@router.get("/risk-alerts", response_model=list[RiskAlert], summary="Active risk alerts")
def risk_alerts(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return dash_svc.get_risk_alerts(db)


@router.get("/supplier-performance", response_model=list[SupplierPerformancePoint],
            summary="Supplier performance chart data")
def supplier_performance(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return dash_svc.get_supplier_performance_chart(db)


@router.get("/demand-forecast", response_model=list[DemandForecastPoint],
            summary="Demand forecast chart data")
def demand_forecast(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return dash_svc.get_demand_forecast_chart(db)


@router.get("/low-inventory", response_model=list[InventoryOut],
            summary="Low-inventory items")
def low_inventory(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = dash_svc.get_low_inventory_items(db)
    # map to InventoryOut via DB query
    ids = [r["inventory_id"] for r in rows]
    if not ids:
        return []
    from ..models import Inventory
    items = db.query(Inventory).filter(Inventory.id.in_(ids)).all()
    return items
