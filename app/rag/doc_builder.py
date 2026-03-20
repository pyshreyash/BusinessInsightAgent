from __future__ import annotations

from typing import Any, Dict, List

import yaml

from app.db.schema import TABLE_SCHEMAS
from app.semantic.loader import SemanticLayer


SCHEMA_DOCS = [
    "Warehouse schema summary:",
    "- fact_sales(date, product_id, quantity, price)",
    "- dim_product(product_id, category)",
    "- dim_time(date, week, month)",
]


def build_rag_documents(*, semantic_layer: SemanticLayer, business_rules_path: str) -> List[str]:
    docs: List[str] = []

    # Metric definition docs.
    docs.append("Semantic metric definitions:")
    for metric_name, metric_def in semantic_layer.metrics.items():
        docs.append(
            f"- Metric `{metric_name}`: formula={metric_def.formula}; table={metric_def.table}; grain={metric_def.grain}"
        )

    # Schema docs.
    docs.append("")
    docs.extend(SCHEMA_DOCS)
    for table_name, table_schema in TABLE_SCHEMAS.items():
        cols = ", ".join([f"{c}({t})" for c, t in table_schema.columns.items()])
        docs.append(f"- {table_name} columns: {cols}")

    # Business rules docs.
    rules_raw = yaml.safe_load(open(business_rules_path, "r", encoding="utf-8").read())
    rules = rules_raw.get("rules") or []
    docs.append("")
    docs.append("Business rules:")
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("id")
        description = rule.get("description")
        docs.append(f"- Rule `{rule_id}`: {description}")

    docs.append("")
    docs.append("Retrieval instruction: Use these docs to ground SQL generation and interpretation.")

    return docs

