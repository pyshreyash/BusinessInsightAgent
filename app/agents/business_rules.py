from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class BusinessRuleSet:
    revenue_drop_threshold: float
    revenue_increase_threshold: float
    anomaly_abs_percent_change: float


def load_business_rules(path: str) -> BusinessRuleSet:
    raw = yaml.safe_load(open(path, "r", encoding="utf-8").read())
    rules = raw.get("rules") or []

    # MVP: fixed mapping based on rule IDs from config/business_rules.yaml.
    drop = 0.10
    inc = 0.10
    anomaly = 0.25
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = rule.get("id")
        thr = rule.get("threshold") or {}
        value = thr.get("value")
        if value is None:
            continue
        try:
            value_f = float(value)
        except Exception:
            continue
        if rid == "revenue_drop_definition":
            drop = value_f
        elif rid == "revenue_increase_definition":
            inc = value_f
        elif rid == "anomaly_hint":
            anomaly = value_f

    return BusinessRuleSet(
        revenue_drop_threshold=drop,
        revenue_increase_threshold=inc,
        anomaly_abs_percent_change=anomaly,
    )

