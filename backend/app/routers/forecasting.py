"""Forecasting endpoints: demand forecast and shortage prediction."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..services.forecasting import forecast_demand, predict_shortages
from ..schemas import DemandForecastPoint

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


@router.get("/demand", response_model=list[DemandForecastPoint],
            summary="Demand forecast per product")
def demand(horizon_months: int = Query(3, ge=1, le=12),
           db: Session = Depends(get_db), _=Depends(get_current_user)):
    return forecast_demand(db, horizon_months=horizon_months)


@router.get("/shortages", response_model=list[DemandForecastPoint],
            summary="Products at risk of shortage")
def shortages(horizon_months: int = Query(3, ge=1, le=12),
              db: Session = Depends(get_db), _=Depends(get_current_user)):
    return predict_shortages(db, horizon_months=horizon_months)
