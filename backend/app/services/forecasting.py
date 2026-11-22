"""Demand forecasting & shortage prediction (scikit-learn).

We build a monthly demand history per product from customer order items, then
train a per-product regression model that extrapolates a trend + seasonality
signal. Outputs predicted demand, confidence bounds, and a shortage flag
against current inventory.
"""
from __future__ import annotations

import io
import math
import time
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from sqlalchemy.orm import Session

from ..models import (
    CustomerOrder, CustomerOrderItem, Product, Inventory, SupplierPerformance,
)
from ..cache import cache_get_json, cache_set_json
from ..core.logging import get_logger

log = get_logger("forecasting")


def _monthly_demand_df(db: Session) -> pd.DataFrame:
    """Aggregate customer order items into monthly demand per product."""
    rows = (
        db.query(
            CustomerOrderItem.product_id,
            CustomerOrder.order_date,
            CustomerOrderItem.quantity,
        )
        .join(CustomerOrder, CustomerOrderItem.co_id == CustomerOrder.id)
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["product_id", "period", "demand"])
    df = pd.DataFrame(rows, columns=["product_id", "order_date", "quantity"])
    df["order_date"] = pd.to_datetime(df["order_date"])
    df["period"] = df["order_date"].dt.to_period("M").astype(str)
    agg = df.groupby(["product_id", "period"])["quantity"].sum().reset_index()
    agg.rename(columns={"quantity": "demand"}, inplace=True)
    return agg


def _encode_period(period: str) -> tuple[int, int]:
    """Return (ordinal month index, month-of-year 1-12)."""
    y, m = period.split("-")
    idx = (int(y) - 2000) * 12 + int(m)
    return idx, int(m)


def forecast_demand(db: Session, product_ids: list[int] | None = None,
                    horizon_months: int = 3) -> list[dict[str, Any]]:
    """Predict demand for each product for the next ``horizon_months``."""
    cache_key = f"forecast:demands:{tuple(product_ids) if product_ids else 'all'}:{horizon_months}"
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    df = _monthly_demand_df(db)
    if df.empty:
        return []

    products_q = db.query(Product)
    if product_ids:
        products_q = products_q.filter(Product.id.in_(product_ids))
    products = products_q.all()
    pid_to_name = {p.id: p.name for p in products}
    inv_by_pid: dict[int, float] = {}
    for p in products:
        inv = db.query(Inventory).filter(Inventory.product_id == p.id).first()
        inv_by_pid[p.id] = float(inv.on_hand - inv.reserved) if inv else 0.0

    results: list[dict[str, Any]] = []
    now_period = datetime_period_now()
    for p in products:
        sub = df[df["product_id"] == p.id].sort_values("period")
        if len(sub) < 3:
            # Not enough history; fall back to mean of available data
            base = float(sub["demand"].mean()) if len(sub) else 0.0
            trend = 0.0
        else:
            X, y = [], []
            for _, r in sub.iterrows():
                idx, month = _encode_period(r["period"])
                # simple sin/cos seasonality
                X.append([idx, math.sin(2 * math.pi * month / 12),
                          math.cos(2 * math.pi * month / 12)])
                y.append(float(r["demand"]))
            X = np.array(X)
            y = np.array(y)
            model = LinearRegression().fit(X, y)
            resid_std = float(np.std(y - model.predict(X))) if len(y) > 2 else max(1.0, float(np.mean(y)) * 0.1)

            last_idx, _ = _encode_period(sub["period"].iloc[-1])
            preds = []
            for h in range(1, horizon_months + 1):
                fidx = last_idx + h
                month = ((fidx - 1) % 12) + 1
                feat = np.array([[fidx, math.sin(2 * math.pi * month / 12),
                                 math.cos(2 * math.pi * month / 12)]])
                pred = max(0.0, float(model.predict(feat)[0]))
                preds.append((fidx, month, pred, resid_std))
        # build output points
        if len(sub) >= 3:
            base = preds[0][2]
            trend = 0.0
        for h in range(1, horizon_months + 1):
            if len(sub) >= 3:
                fidx, month, pred, resid_std = preds[h - 1]
                period_str = period_from_index(fidx)
            else:
                period_str = add_months(now_period, h)
                pred = base
                resid_std = max(1.0, base * 0.1)
            lower = max(0.0, pred - 1.96 * resid_std)
            upper = pred + 1.96 * resid_std
            on_hand = inv_by_pid.get(p.id, 0.0)
            # shortage risk if predicted demand over horizon exceeds on_hand + safety buffer
            is_shortage = (pred * 1.0) > on_hand * 1.2 and pred > 0
            results.append({
                "product_id": p.id,
                "product_name": pid_to_name.get(p.id, ""),
                "period": period_str,
                "predicted_demand": round(pred, 2),
                "lower_bound": round(lower, 2),
                "upper_bound": round(upper, 2),
                "on_hand": round(on_hand, 2),
                "is_shortage_risk": bool(is_shortage),
            })

    cache_set_json(cache_key, results, ttl=600)
    log.info("forecasting.complete", products=len(results))
    return results


def predict_shortages(db: Session, horizon_months: int = 3) -> list[dict[str, Any]]:
    """Products predicted to face shortage in the horizon."""
    forecasts = forecast_demand(db, horizon_months=horizon_months)
    return [f for f in forecasts if f["is_shortage_risk"]]


# ---- small date helpers (kept local to avoid extra imports) ----------------

def datetime_period_now() -> str:
    now = pd.Timestamp.now("UTC").to_pydatetime()
    return f"{now.year}-{now.month:02d}"


def period_from_index(idx: int) -> str:
    y = 2000 + (idx - 1) // 12
    m = ((idx - 1) % 12) + 1
    return f"{y}-{m:02d}"


def add_months(period: str, months: int) -> str:
    y, m = period.split("-")
    total = (int(y) * 12 + int(m)) + months
    ny = total // 12
    nm = total % 12
    if nm == 0:
        nm = 12
        ny -= 1
    return f"{ny}-{nm:02d}"
