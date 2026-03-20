from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List


def build_seed_data() -> Dict[str, List[Dict[str, Any]]]:
    """
    Deterministic seed dataset for local MVP runs.

    Produces data across several weeks for two product categories.
    """
    start_date = date(2026, 1, 5)  # Monday
    num_weeks = 6
    days_per_week = 7

    dim_product = [
        {"product_id": 1, "category": "Widgets"},
        {"product_id": 2, "category": "Gadgets"},
    ]

    dim_time: List[Dict[str, Any]] = []
    for w in range(num_weeks):
        week_start = start_date + timedelta(weeks=w)
        for d in range(days_per_week):
            dt = week_start + timedelta(days=d)
            # ISO week number may vary across years; keep simple, deterministic "week index".
            dim_time.append(
                {
                    "date": dt,
                    "week": w + 1,
                    "month": dt.month,
                }
            )

    # Revenue = SUM(price * quantity). We'll vary quantity/price by week to create "drop/increase".
    # Week 1-6: revenue trend example: up, down, stable.
    week_multipliers = {
        1: 1.10,
        2: 0.95,
        3: 0.85,  # drop vs week 2
        4: 1.05,  # increase vs week 3
        5: 0.90,  # drop vs week 4
        6: 0.75,  # meaningful decrease vs week 5 to support "drop last week" demo
    }

    fact_sales: List[Dict[str, Any]] = []
    base_price = {1: 25.0, 2: 40.0}
    base_qty = {1: 20, 2: 12}

    for row in dim_time:
        w = int(row["week"])
        dt = row["date"]
        mult = float(week_multipliers[w])
        for product_id in [1, 2]:
            # Small deterministic intra-week variation.
            day_offset = (dt - start_date).days % 7
            qty = int(base_qty[product_id] * mult * (1 + (day_offset - 3) * 0.01))
            price = float(base_price[product_id] * (1 + (day_offset - 3) * 0.005))
            qty = max(1, qty)
            fact_sales.append(
                {
                    "date": dt,
                    "product_id": product_id,
                    "quantity": qty,
                    "price": round(price, 2),
                }
            )

    return {"dim_product": dim_product, "dim_time": dim_time, "fact_sales": fact_sales}

