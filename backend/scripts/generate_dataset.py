"""Generate a realistic synthetic supply-chain dataset (>10,000 records).

Run as a script to write per-table CSVs plus a combined denormalised CSV to
``data/``. Importable: ``generate()`` returns a dict of DataFrames so the
app can seed the database directly.

Produces ~45,000+ rows across tables; the combined dataset CSV alone has
>12,000 purchase-order line rows.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Fixed seed for reproducible "realistic" data.
RNG_SEED = 42
BASE_DATE = datetime(2024, 1, 1)


# ---- helpers ---------------------------------------------------------------

def _choice(rng, options, size=None):
    return rng.choice(options, size=size)


def _round(x, n=2):
    return np.round(x, n)


# ---- generators ------------------------------------------------------------

def gen_suppliers(n: int, rng: np.random.Generator) -> pd.DataFrame:
    countries = ["USA", "Germany", "China", "India", "Vietnam", "Mexico",
                 "Japan", "South Korea", "Brazil", "UK", "Italy", "Taiwan"]
    regions = {
        "USA": "Americas", "Mexico": "Americas", "Brazil": "Americas",
        "Germany": "Europe", "UK": "Europe", "Italy": "Europe",
        "China": "Asia", "India": "Asia", "Vietnam": "Asia",
        "Japan": "Asia", "South Korea": "Asia", "Taiwan": "Asia",
    }
    names_prefix = ["Global", "Prime", "Apex", "Nexa", "Vertex", "Orbit",
                    "Summit", "Cobalt", "Atlas", "Helix", "Nova", "Delta"]
    names_suffix = ["Components", "Logistics", "Supply", "Industries",
                    "Manufacturing", "Trade", "Parts", "Materials", "Works"]

    rows = []
    for i in range(1, n + 1):
        country = rng.choice(countries)
        # on_time_rate skewed: most suppliers decent, a few poor.
        on_time = np.clip(rng.beta(8, 2), 0.4, 0.99)
        lead = float(np.round(rng.normal(14, 6)))
        lead = max(3, min(45, lead))
        rating = float(_round(np.clip(rng.normal(3.6, 0.7), 1.5, 5.0), 1))
        rows.append({
            "id": i,
            "name": f"{rng.choice(names_prefix)} {rng.choice(names_suffix)} {i}",
            "code": f"SUP-{i:04d}",
            "country": country,
            "region": regions[country],
            "rating": rating,
            "on_time_rate": float(_round(on_time, 3)),
            "avg_lead_time_days": lead,
            "min_order_qty": int(rng.choice([50, 100, 150, 200, 250])),
            "active": bool(rng.random() > 0.06),
        })
    return pd.DataFrame(rows)


def gen_products(n: int, suppliers: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    categories = ["Electronics", "Raw Materials", "Packaging", "Hardware",
                  "Chemicals", "Textiles", "Automotive", "Medical", "Food", "Plastics"]
    materials = ["Aluminum", "Steel", "Plastic", "Copper", "Composite",
                 "Rubber", "Glass", "Circuit", "Wire", "Fabric"]
    rows = []
    sup_ids = suppliers.loc[suppliers["active"], "id"].to_numpy()
    for i in range(1, n + 1):
        cat = rng.choice(categories)
        unit_cost = float(_round(rng.gamma(2.0, 8.0) + 1.5))
        unit_price = float(_round(unit_cost * rng.uniform(1.4, 2.6)))
        rows.append({
            "id": i,
            "sku": f"PROD-{i:05d}",
            "name": f"{cat[:-1] if cat.endswith('s') else cat} {rng.choice(materials)} {i}",
            "category": cat,
            "unit_cost": unit_cost,
            "unit_price": unit_price,
            "weight_kg": float(_round(rng.uniform(0.05, 25.0), 3)),
            "primary_supplier_id": int(rng.choice(sup_ids)),
        })
    return pd.DataFrame(rows)


def gen_inventory(products: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    warehouses = ["DC-1", "DC-2"]
    rows = []
    rid = 1
    for _, p in products.iterrows():
        for wh in warehouses:
            on_hand = float(rng.poisson(rng.integers(40, 600)))
            safety = float(rng.integers(20, 120))
            reorder = float(safety + rng.integers(30, 150))
            rows.append({
                "id": rid,
                "product_id": int(p["id"]),
                "warehouse": wh,
                "on_hand": on_hand,
                "safety_stock": safety,
                "reorder_point": reorder,
                "reserved": float(min(on_hand, rng.integers(0, 60))),
                "updated_at": BASE_DATE + timedelta(days=int(rng.integers(0, 365))),
            })
            rid += 1
    return pd.DataFrame(rows)


def gen_customers(n: int, rng: np.random.Generator) -> pd.DataFrame:
    countries = ["USA", "Canada", "UK", "Germany", "France", "Australia",
                 "Singapore", "UAE", "Spain", "Netherlands"]
    segments = ["retail", "wholesale", "enterprise", "distributor"]
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "id": i,
            "name": f"Customer {i:04d}",
            "code": f"CUST-{i:04d}",
            "country": rng.choice(countries),
            "segment": rng.choice(segments, p=[0.4, 0.3, 0.2, 0.1]),
            "created_at": BASE_DATE - timedelta(days=int(rng.integers(30, 900))),
        })
    return pd.DataFrame(rows)


def gen_transportation(n: int, rng: np.random.Generator) -> pd.DataFrame:
    hubs = ["Shanghai", "Shenzhen", "Mumbai", "Hamburg", "Rotterdam",
            "Los Angeles", "New York", "Mexico City", "Tokyo", "Singapore"]
    modes = [("air", 2.5, 4), ("rail", 0.9, 12), ("road", 1.3, 6), ("sea", 0.4, 28)]
    carriers = ["DHL", "Maersk", "FedEx", "UPS", "Yang Ming", "DB Schenker", "Kuehne+Nagel"]
    rows = []
    for i in range(1, n + 1):
        mode, cpu, days = modes[int(rng.integers(0, len(modes)))]
        o, d = rng.choice(hubs, size=2, replace=False)
        rows.append({
            "id": i,
            "route_code": f"RTE-{i:03d}",
            "origin": o,
            "destination": d,
            "mode": mode,
            "cost_per_unit": float(_round(cpu * rng.uniform(0.8, 1.4), 3)),
            "transit_days": float(_round(days * rng.uniform(0.8, 1.3), 1)),
            "carrier": rng.choice(carriers),
        })
    return pd.DataFrame(rows)


def gen_purchase_orders(n: int, suppliers: pd.DataFrame, products: pd.DataFrame,
                       rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    sup_ids = suppliers.loc[suppliers["active"], "id"].to_numpy()
    prod_ids = products["id"].to_numpy()
    statuses = ["open", "in_transit", "delivered", "delayed", "cancelled"]
    status_p = [0.18, 0.22, 0.45, 0.12, 0.03]

    po_rows = []
    item_rows = []
    item_id = 1
    for i in range(1, n + 1):
        sup = int(rng.choice(sup_ids))
        order_date = BASE_DATE + timedelta(days=int(rng.integers(0, 720)))
        lead = float(suppliers.loc[suppliers["id"] == sup, "avg_lead_time_days"].iloc[0])
        expected = order_date + timedelta(days=int(lead))
        status = str(rng.choice(statuses, p=status_p))
        # delays actually arrive later than expected
        if status == "delivered":
            actual = expected + timedelta(days=int(rng.integers(-2, 3)))
        elif status == "delayed":
            actual = expected + timedelta(days=int(rng.integers(4, 25)))
        elif status == "in_transit":
            actual = None
        else:
            actual = None if status == "open" else expected

        n_items = int(rng.integers(1, 6))
        chosen = rng.choice(prod_ids, size=n_items, replace=False)
        total = 0.0
        transport = float(_round(rng.gamma(2.5, 220)))
        for pid in chosen:
            uc = float(products.loc[products["id"] == pid, "unit_cost"].iloc[0])
            qty = float(rng.integers(50, 1200))
            line = float(_round(uc * qty))
            total += line
            item_rows.append({
                "id": item_id,
                "po_id": i,
                "product_id": int(pid),
                "quantity": qty,
                "unit_cost": uc,
                "line_total": line,
            })
            item_id += 1
        po_rows.append({
            "id": i,
            "po_number": f"PO-{i:06d}",
            "supplier_id": sup,
            "status": status,
            "order_date": order_date,
            "expected_delivery": expected,
            "actual_delivery": actual,
            "total_cost": float(_round(total)),
            "transport_cost": transport,
            "created_at": order_date,
        })
    return pd.DataFrame(po_rows), pd.DataFrame(item_rows)


def gen_deliveries(purchase_orders: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    did = 1
    carriers = ["DHL", "FedEx", "UPS", "Maersk", "DB Schenker"]
    for _, po in purchase_orders.iterrows():
        st = po["status"]
        if st == "delivered":
            status = "delivered"
            actual = po["actual_delivery"]
        elif st == "delayed":
            status = "delayed"
            actual = po["actual_delivery"]
        elif st == "in_transit":
            status = "in_transit"
            actual = None
        elif st == "cancelled":
            status = "failed"
            actual = None
        else:
            status = "scheduled"
            actual = None
        rows.append({
            "id": did,
            "po_id": int(po["id"]),
            "scheduled_date": po["expected_delivery"],
            "actual_date": actual,
            "status": status,
            "carrier": rng.choice(carriers),
            "transport_cost": float(po["transport_cost"]),
            "transit_days": float(_round(rng.uniform(2, 30), 1)),
        })
        did += 1
    return pd.DataFrame(rows)


def gen_customer_orders(n: int, customers: pd.DataFrame, products: pd.DataFrame,
                        rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    cust_ids = customers["id"].to_numpy()
    prod_ids = products["id"].to_numpy()
    statuses = ["open", "fulfilled", "backordered", "cancelled"]
    status_p = [0.35, 0.5, 0.12, 0.03]
    co_rows, item_rows = [], []
    item_id = 1
    for i in range(1, n + 1):
        order_date = BASE_DATE + timedelta(days=int(rng.integers(0, 720)))
        required = order_date + timedelta(days=int(rng.integers(3, 30)))
        n_items = int(rng.integers(1, 5))
        chosen = rng.choice(prod_ids, size=n_items, replace=False)
        total = 0.0
        for pid in chosen:
            up = float(products.loc[products["id"] == pid, "unit_price"].iloc[0])
            qty = float(rng.integers(10, 400))
            total += up * qty
            item_rows.append({
                "id": item_id,
                "co_id": i,
                "product_id": int(pid),
                "quantity": qty,
                "unit_price": float(_round(up)),
            })
            item_id += 1
        co_rows.append({
            "id": i,
            "co_number": f"CO-{i:06d}",
            "customer_id": int(rng.choice(cust_ids)),
            "order_date": order_date,
            "required_date": required,
            "status": str(rng.choice(statuses, p=status_p)),
            "total_value": float(_round(total)),
            "created_at": order_date,
        })
    return pd.DataFrame(co_rows), pd.DataFrame(item_rows)


def gen_supplier_performance(suppliers: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Monthly performance over 12 months for each active supplier."""
    months = [(BASE_DATE + timedelta(days=30 * m)).strftime("%Y-%m") for m in range(12)]
    rows = []
    rid = 1
    for _, s in suppliers.loc[suppliers["active"]].iterrows():
        for m in months:
            noise = rng.normal(0, 0.06)
            rows.append({
                "id": rid,
                "supplier_id": int(s["id"]),
                "period": m,
                "on_time_rate": float(_round(np.clip(s["on_time_rate"] + noise, 0.3, 0.99), 3)),
                "defect_rate": float(_round(np.clip(abs(rng.normal(0.02, 0.015)), 0, 0.1), 4)),
                "avg_lead_time": float(_round(max(3, s["avg_lead_time_days"] + rng.normal(0, 1.5)), 1)),
                "orders_fulfilled": int(rng.integers(8, 120)),
            })
            rid += 1
    return pd.DataFrame(rows)


def generate(
    n_suppliers: int = 150,
    n_products: int = 500,
    n_customers: int = 300,
    n_pos: int = 4200,
    n_cos: int = 4000,
    seed: int = RNG_SEED,
) -> dict[str, pd.DataFrame]:
    """Generate all tables as DataFrames and return them in a dict."""
    rng = np.random.default_rng(seed)

    suppliers = gen_suppliers(n_suppliers, rng)
    products = gen_products(n_products, suppliers, rng)
    inventory = gen_inventory(products, rng)
    customers = gen_customers(n_customers, rng)
    transportation = gen_transportation(60, rng)
    pos, po_items = gen_purchase_orders(n_pos, suppliers, products, rng)
    deliveries = gen_deliveries(pos, rng)
    cos, co_items = gen_customer_orders(n_cos, customers, products, rng)
    performance = gen_supplier_performance(suppliers, rng)

    tables = {
        "suppliers": suppliers,
        "products": products,
        "inventory": inventory,
        "customers": customers,
        "transportation": transportation,
        "purchase_orders": pos,
        "purchase_order_items": po_items,
        "deliveries": deliveries,
        "customer_orders": cos,
        "customer_order_items": co_items,
        "supplier_performance": performance,
    }
    return tables


def build_combined_dataset(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Denormalised fact table: one row per purchase-order line item (>10k rows)."""
    df = tables["purchase_order_items"].merge(
        tables["purchase_orders"], left_on="po_id", right_on="id", suffixes=("", "_po")
    ).merge(
        tables["suppliers"], left_on="supplier_id", right_on="id", suffixes=("", "_sup")
    ).merge(
        tables["products"], left_on="product_id", right_on="id", suffixes=("", "_prod")
    )
    keep = [
        "po_number", "supplier_id", "supplier_name", "supplier_country",
        "status", "order_date", "expected_delivery", "actual_delivery",
        "sku", "product_name", "category", "quantity", "unit_cost",
        "line_total", "total_cost", "transport_cost", "on_time_rate",
        "avg_lead_time_days", "rating",
    ]
    df = df.rename(columns={
        "name": "supplier_name",
        "country": "supplier_country",
        "name_prod": "product_name",
    })
    return df[keep].copy()


def validate_tables(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Lightweight data cleaning + validation; returns list of issues found."""
    issues = []
    # Drop duplicates
    for name, df in tables.items():
        before = len(df)
        df.drop_duplicates(inplace=True)
        # Fill numeric NaN with 0 where sensible
        for col in df.select_dtypes(include="number").columns:
            df[col] = df[col].fillna(0)
        if len(df) != before:
            issues.append(f"{name}: dropped {before - len(df)} duplicate rows")

    # Referential integrity checks
    sup_ids = set(tables["suppliers"]["id"])
    if not tables["products"]["primary_supplier_id"].isin(sup_ids).all():
        bad = (~tables["products"]["primary_supplier_id"].isin(sup_ids)).sum()
        issues.append(f"products: {bad} rows with invalid supplier reference")

    # Non-negative sanity checks
    for col in ["on_hand", "safety_stock", "reorder_point"]:
        if (tables["inventory"][col] < 0).any():
            issues.append(f"inventory.{col}: negative values found")

    # Quantities positive
    if (tables["purchase_order_items"]["quantity"] <= 0).any():
        issues.append("purchase_order_items: non-positive quantities")

    return issues


def write_csvs(tables: dict[str, pd.DataFrame], out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df in tables.items():
        p = out / f"{name}.csv"
        df.to_csv(p, index=False)
        paths[name] = p
    combined = build_combined_dataset(tables)
    cp = out / "supply_chain_dataset.csv"
    combined.to_csv(cp, index=False)
    paths["combined"] = cp
    return paths


def total_records(tables: dict[str, pd.DataFrame]) -> int:
    return int(sum(len(df) for df in tables.values()))


def main() -> None:
    out_dir = os.environ.get("DATA_DIR", "data")
    tables = generate()
    issues = validate_tables(tables)
    paths = write_csvs(tables, out_dir)
    print("=== Dataset generation complete ===")
    for name, df in tables.items():
        print(f"  {name:<26} {len(df):>7} rows")
    print(f"  {'combined_dataset':<26} {len(build_combined_dataset(tables)):>7} rows")
    print(f"  TOTAL records            {total_records(tables):>7}")
    if issues:
        print("--- validation notes ---")
        for i in issues:
            print("  -", i)
    else:
        print("--- validation: OK (no issues) ---")
    print("CSV files written to:", out_dir)


if __name__ == "__main__":
    main()
