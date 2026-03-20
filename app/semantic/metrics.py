from __future__ import annotations

import re
from typing import Dict, List, Tuple

from app.semantic.loader import MetricDefinition, SemanticLayer


def get_metric_definition(layer: SemanticLayer, name: str) -> MetricDefinition:
    if name not in layer.metrics:
        raise KeyError(f"Unknown metric `{name}` in semantic layer.")
    return layer.metrics[name]


def _normalize_sql_fragment(fragment: str) -> str:
    # Remove whitespace and normalize casing to allow deterministic matching.
    s = fragment.strip().lower()
    s = re.sub(r"\s+", "", s)
    return s


def validate_metric_usage(sql: str, layer: SemanticLayer) -> Tuple[List[str], List[str]]:
    """
    Deterministically check that the SQL uses at least one metric formula defined in the semantic layer.

    This is intentionally conservative and relies on formula-string inclusion. SQL generation should inject
    the formula snippet verbatim, enabling validation.
    """
    normalized_sql = _normalize_sql_fragment(sql)

    used_metrics: List[str] = []
    errors: List[str] = []
    for metric_name, metric_def in layer.metrics.items():
        formula_norm = _normalize_sql_fragment(metric_def.formula)
        if formula_norm and formula_norm in normalized_sql:
            used_metrics.append(metric_name)

    if not used_metrics:
        errors.append(
            "SQL does not appear to use any metric formula from the semantic layer (deterministic match failed)."
        )

    return used_metrics, errors

