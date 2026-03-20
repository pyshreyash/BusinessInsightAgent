from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    formula: str
    table: str
    grain: str


@dataclass(frozen=True)
class SemanticLayer:
    metrics: Dict[str, MetricDefinition]
    dimensions: List[str]
    dimension_mappings: Dict[str, Dict[str, str]]


def load_semantic_layer(yaml_path: str) -> SemanticLayer:
    path = Path(yaml_path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Semantic layer YAML must be a mapping/object at the top level.")

    metrics_raw = raw.get("metrics") or {}
    if not isinstance(metrics_raw, dict):
        raise ValueError("`metrics` must be a mapping/object in semantic_layer.yaml.")

    metrics: Dict[str, MetricDefinition] = {}
    for metric_name, metric_def in metrics_raw.items():
        if not isinstance(metric_def, dict):
            raise ValueError(f"Metric definition for `{metric_name}` must be an object.")
        metrics[metric_name] = MetricDefinition(
            name=str(metric_name),
            formula=str(metric_def.get("formula", "")).strip(),
            table=str(metric_def.get("table", "")).strip(),
            grain=str(metric_def.get("grain", "")).strip(),
        )

    dimensions = raw.get("dimensions") or []
    if not isinstance(dimensions, list) or not all(isinstance(d, str) for d in dimensions):
        raise ValueError("`dimensions` must be a list of strings.")

    dimension_mappings = raw.get("dimension_mappings") or {}
    if not isinstance(dimension_mappings, dict):
        raise ValueError("`dimension_mappings` must be an object if present.")

    # Validate mapping values are dict-like.
    cleaned_mappings: Dict[str, Dict[str, str]] = {}
    for dim, mapping in dimension_mappings.items():
        if not isinstance(mapping, dict):
            continue
        cleaned_mappings[str(dim)] = {str(k): str(v) for k, v in mapping.items()}

    return SemanticLayer(metrics=metrics, dimensions=dimensions, dimension_mappings=cleaned_mappings)

