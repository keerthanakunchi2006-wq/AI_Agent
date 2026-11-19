"""Forecasting Agent — demand forecasting + shortage prediction for affected products."""
from __future__ import annotations

from ..core.metrics import AGENT_DURATION, AGENT_RUNS
from ..services.forecasting import forecast_demand, predict_shortages
from .common import with_retries


@with_retries()
def forecasting_node(state: dict, db) -> dict:
    with AGENT_DURATION.labels(agent="forecasting").time():
        affected = state.get("affected_product_ids", [])
        # forecast for affected products if any, else top products
        forecasts = forecast_demand(db, product_ids=affected or None, horizon_months=3)
        shortages = [f for f in forecasts if f["is_shortage_risk"]]

        AGENT_RUNS.labels(agent="forecasting", status="ok").inc()
        return {
            "demand_forecast": forecasts,
            "shortage_predictions": shortages,
            "status": "forecasting_complete",
        }
