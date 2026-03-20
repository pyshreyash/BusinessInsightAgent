from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.semantic.loader import SemanticLayer


@dataclass(frozen=True)
class SemanticLayerValidationError:
    code: str
    message: str
    details: Optional[dict] = None


def validate_semantic_layer(layer: SemanticLayer, *, known_tables: Optional[List[str]] = None) -> List[SemanticLayerValidationError]:
    errors: List[SemanticLayerValidationError] = []

    for name, metric in layer.metrics.items():
        if not metric.formula or metric.formula.strip() == "":
            errors.append(
                SemanticLayerValidationError(
                    code="EMPTY_FORMULA",
                    message=f"Metric `{name}` has an empty formula.",
                    details={"metric": name},
                )
            )
        if not metric.table:
            errors.append(
                SemanticLayerValidationError(
                    code="EMPTY_TABLE",
                    message=f"Metric `{name}` has an empty table.",
                    details={"metric": name},
                )
            )
        if not metric.grain:
            errors.append(
                SemanticLayerValidationError(
                    code="EMPTY_GRAIN",
                    message=f"Metric `{name}` has an empty grain.",
                    details={"metric": name},
                )
            )

        if known_tables is not None and metric.table and metric.table not in known_tables:
            errors.append(
                SemanticLayerValidationError(
                    code="UNKNOWN_TABLE",
                    message=f"Metric `{name}` references unknown table `{metric.table}`.",
                    details={"metric": name, "table": metric.table},
                )
            )

    return errors

