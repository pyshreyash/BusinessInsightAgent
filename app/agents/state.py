from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class QueryState(TypedDict, total=False):
    question: str

    plan: Dict[str, Any]
    context: str

    sql: str
    validation_ok: bool
    validation_errors: List[Dict[str, Any]]
    metrics_used: List[str]

    result: List[Dict[str, Any]]

    insight: str
    assumptions: List[str]
    errors: List[str]

    retry_count: int

