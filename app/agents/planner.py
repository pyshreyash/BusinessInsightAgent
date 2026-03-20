from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


def _detect_category_filter(question: str) -> Optional[str]:
    q = question.lower()
    # MVP: two categories from seed.
    if "widgets" in q:
        return "Widgets"
    if "gadgets" in q:
        return "Gadgets"
    return None


def plan_query(question: str) -> Dict[str, Any]:
    q = question.lower()

    metric = "revenue"
    if "revenue" in q:
        metric = "revenue"
    elif any(k in q for k in ["quantity", "units", "sold"]):
        metric = "quantity_sold"

    # MVP: only week-over-week latest comparisons.
    time_mode = "week_over_week_latest" if ("last week" in q or "week over week" in q or "wo w" in q) else "week_over_week_latest"

    category_filter = _detect_category_filter(question)

    return {
        "metric": metric,
        "time_mode": time_mode,
        "category_filter": category_filter,
        "deterministic_scaffold": True,
    }


def initial_assumptions(question: str) -> List[str]:
    return [
        "Assumes the question refers to the most recent available week-over-week comparison in the dataset.",
        "Driver-level causes (product-level breakdowns) are not computed in MVP; only total change is analyzed.",
    ]

