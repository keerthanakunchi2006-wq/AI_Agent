"""Supplier evaluation — score alternative suppliers for a product/quantity.

For a given product and required quantity, enumerate candidate suppliers that
can produce the product's category, compute per-unit cost (with a category
multiplier), transport cost (from transportation routes), and expected
delivery days. Score each supplier with a weighted multi-objective function.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Supplier, Product, TransportationRoute
from ..core.logging import get_logger

log = get_logger("supplier_eval")

# weights for the composite score (0-1, normalised)
W_COST = 0.40
W_DELAY = 0.30
W_RELIABILITY = 0.20
W_QUALITY = 0.10

# Category-based cost multipliers: how much more/less expensive a supplier is
# relative to the product's base unit cost depending on its category alignment.
CATEGORY_COST_FACTOR = {
    "Electronics": 1.0, "Raw Materials": 0.85, "Packaging": 0.9,
    "Hardware": 0.95, "Chemicals": 1.05, "Textiles": 0.9, "Automotive": 1.0,
    "Medical": 1.15, "Food": 0.92, "Plastics": 0.95,
}


def _candidate_cost(supplier: Supplier, product: Product, quantity: float) -> float:
    """Per-unit cost offered by a supplier for a product."""
    base = product.unit_cost
    factor = CATEGORY_COST_FACTOR.get(product.category, 1.0)
    # suppliers with higher rating are slightly more expensive but reliable
    premium = 1.0 + max(0.0, (supplier.rating - 3.5)) * 0.04
    # quantity discount
    discount = 0.95 if quantity >= supplier.min_order_qty else 1.02
    return round(base * factor * premium * discount, 2)


def _transport_cost(db: Session, supplier: Supplier, route: TransportationRoute,
                    product: Product, quantity: float) -> float:
    # cost scales with weight and units shipped
    units = max(1.0, quantity / 100.0)
    return round(route.cost_per_unit * units * max(0.5, product.weight_kg * 0.05), 2)


def _pick_route(db: Session, supplier: Supplier) -> TransportationRoute | None:
    routes = db.query(TransportationRoute).filter(
        TransportationRoute.origin == supplier.country
    ).all()
    if not routes:
        routes = db.query(TransportationRoute).all()
    if not routes:
        return None
    # pick fastest route as default heuristic
    return min(routes, key=lambda r: r.transit_days)


def evaluate_alternatives(db: Session, product_id: int, quantity: float,
                         exclude_supplier_id: int | None = None) -> list[dict[str, Any]]:
    """Return scored alternative suppliers for a product/quantity."""
    product = db.get(Product, product_id) if hasattr(db, "get") else db.query(Product).get(product_id)
    if not product:
        return []

    suppliers = db.query(Supplier).filter(Supplier.active.is_(True)).all()
    candidates = [s for s in suppliers if s.id != exclude_supplier_id]
    if not candidates:
        return []

    # gather cost/delay vectors for normalisation
    scored: list[dict[str, Any]] = []
    for s in candidates:
        unit_cost = _candidate_cost(s, product, quantity)
        route = _pick_route(db, s)
        transport_cost = _transport_cost(db, s, route, product, quantity) if route else round(quantity * 0.05, 2)
        delivery_days = float(route.transit_days) + s.avg_lead_time_days if route else s.avg_lead_time_days
        total_cost = round(unit_cost * quantity + transport_cost, 2)
        scored.append({
            "supplier_id": s.id,
            "supplier_name": s.name,
            "country": s.country,
            "rating": s.rating,
            "on_time_rate": s.on_time_rate,
            "lead_time_days": s.avg_lead_time_days,
            "unit_cost": unit_cost,
            "transport_cost": transport_cost,
            "delivery_days": round(delivery_days, 1),
            "total_cost": total_cost,
        })

    if not scored:
        return []

    costs = np_list([c["total_cost"] for c in scored])
    delays = np_list([c["delivery_days"] for c in scored])
    cost_min, cost_max = min(costs), max(costs)
    delay_min, delay_max = min(delays), max(delays)

    for c in scored:
        cost_norm = norm(c["total_cost"], cost_min, cost_max)          # lower is better -> invert
        delay_norm = norm(c["delivery_days"], delay_min, delay_max)
        reliability = c["on_time_rate"]                                  # higher better
        quality = c["rating"] / 5.0
        # score: higher is better
        c["delay_vs_original"] = 0.0  # filled by caller with original baseline
        c["score"] = round(
            W_COST * (1 - cost_norm) + W_DELAY * (1 - delay_norm)
            + W_RELIABILITY * reliability + W_QUALITY * quality, 4
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    log.info("supplier_eval.complete", product=product_id, candidates=len(scored))
    return scored


def best_alternative(db: Session, product_id: int, quantity: float,
                    exclude_supplier_id: int | None = None) -> dict[str, Any] | None:
    alts = evaluate_alternatives(db, product_id, quantity, exclude_supplier_id)
    return alts[0] if alts else None


# ---- tiny helpers to avoid hard numpy dependency in this module -----------

def np_list(x):
    return x


def norm(value: float, lo: float, hi: float) -> float:
    if hi == lo:
        return 0.0
    return (value - lo) / (hi - lo)
