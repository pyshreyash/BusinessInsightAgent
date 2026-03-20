from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: Dict[str, str]  # column_name -> postgres type (informational)


TABLE_SCHEMAS: Dict[str, TableSchema] = {
    "fact_sales": TableSchema(
        name="fact_sales",
        columns={
            "date": "date",
            "product_id": "integer",
            "quantity": "numeric",
            "price": "numeric",
        },
    ),
    "dim_product": TableSchema(
        name="dim_product",
        columns={
            "product_id": "integer",
            "category": "text",
        },
    ),
    "dim_time": TableSchema(
        name="dim_time",
        columns={
            "date": "date",
            "week": "integer",
            "month": "integer",
        },
    ),
}

KNOWN_TABLES = sorted(TABLE_SCHEMAS.keys())


# For deterministic validation: allowed join relationships.
ALLOWED_JOIN_CONDITIONS: List[Tuple[str, str, str, str]] = [
    # (left_table, left_col, right_table, right_col)
    ("fact_sales", "product_id", "dim_product", "product_id"),
    ("fact_sales", "date", "dim_time", "date"),
]

