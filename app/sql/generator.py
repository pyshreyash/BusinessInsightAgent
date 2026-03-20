from __future__ import annotations

import json
import asyncio
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - MVP should still run without LLM deps
    OpenAI = None  # type: ignore

from app.semantic.loader import SemanticLayer
from app.semantic.metrics import get_metric_definition


@dataclass(frozen=True)
class SqlGenerationResult:
    sql: str
    metrics_used: List[str]
    assumptions: List[str]


def _extract_sql(text: str) -> str:
    # 1) Try fenced ```sql ... ```
    m = re.search(r"```sql\\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    # 2) Try any SELECT ... until end.
    m = re.search(r"(select\\s+.*)", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def build_sql_from_plan(*, semantic_layer: SemanticLayer, plan: Dict[str, Any]) -> SqlGenerationResult:
    metric_name = plan.get("metric") or "revenue"
    metric_def = get_metric_definition(semantic_layer, metric_name)

    assumptions: List[str] = []
    if plan.get("time_mode") == "week_over_week_latest":
        # Compare latest week vs previous week using dim_time.week indexes.
        if metric_def.table != "fact_sales":
            assumptions.append("Mock MVP SQL builder only supports metrics defined on `fact_sales`.")

        where_clauses: List[str] = []
        join_dim_product = False
        if plan.get("category_filter"):
            join_dim_product = True
            where_clauses.append(f"dim_product.category = '{plan['category_filter']}'")
        where_common = " AND ".join(where_clauses) if where_clauses else "1=1"

        join_dim_product_sql = (
            "\nJOIN dim_product ON fact_sales.product_id = dim_product.product_id" if join_dim_product else ""
        )

        sql = f"""
WITH bounds AS (
  SELECT
    max(week) AS current_week,
    max(week) - 1 AS previous_week
  FROM dim_time
)
SELECT
  dim_time.week AS week,
  {metric_def.formula} AS {metric_def.name}
FROM fact_sales
JOIN dim_time ON fact_sales.date = dim_time.date
CROSS JOIN bounds
{join_dim_product_sql}
WHERE
  dim_time.week IN (bounds.current_week, bounds.previous_week)
  AND {where_common}
GROUP BY
  dim_time.week
ORDER BY
  dim_time.week
""".strip()

        # Metric formula usage is satisfied by construction.
        return SqlGenerationResult(sql=sql, metrics_used=[metric_name], assumptions=assumptions)

    assumptions.append("Unknown time_mode; defaulting to week_over_week_latest.")
    return build_sql_from_plan(semantic_layer=semantic_layer, plan={**plan, "time_mode": "week_over_week_latest"})


class LlmSqlRefiner:
    def __init__(self, *, api_key: str, chat_model: str):
        if OpenAI is None:
            raise RuntimeError("openai package not installed; cannot run LLM refinement.")
        self._client = OpenAI(api_key=api_key)
        self._chat_model = chat_model

    async def refine_sql(
        self,
        *,
        question: str,
        context: str,
        semantic_layer: SemanticLayer,
        plan: Dict[str, Any],
        candidate_sql: str,
    ) -> str:
        """
        Best-effort LLM refinement.

        Critical logic remains in deterministic validation and the base SQL template.
        """
        metric_defs = [
            {"name": m.name, "formula": m.formula, "table": m.table, "grain": m.grain} for m in semantic_layer.metrics.values()
        ]
        dimensions = semantic_layer.dimensions
        prompt = {
            "role": "system",
            "content": (
                "You are an assistant that converts business questions into SQL grounded in a semantic layer and a fixed warehouse schema. "
                "Rules: (1) Do not use columns/tables not present in the schema; (2) Use metric formulas exactly as provided in the semantic layer; "
                "(3) No SELECT *; (4) Prefer CTEs for bounds. "
                "Return ONLY a single JSON object with keys {\"sql\": \"...\", \"assumptions\": [\"...\"], \"metrics_used\": [\"...\"]}."
            ),
        }

        user_message = {
            "role": "user",
            "content": (
                "Question:\n"
                f"{question}\n\n"
                "Retrieved context:\n"
                f"{context}\n\n"
                "Plan (may be partially filled):\n"
                f"{json.dumps(plan)}\n\n"
                "Semantic layer:\n"
                f"metrics={json.dumps(metric_defs)}\n"
                f"dimensions={json.dumps(dimensions)}\n\n"
                "Candidate SQL:\n"
                f"{candidate_sql}\n\n"
                "If the candidate SQL already correctly answers the question, return it unchanged."
            ),
        }

        # OpenAI Python SDK calls are synchronous; move to a thread to avoid blocking the event loop.
        def _call_openai() -> str:
            resp = self._client.chat.completions.create(
                model=self._chat_model,
                temperature=0,
                messages=[prompt, user_message],
            )
            return resp.choices[0].message.content or ""

        content = await asyncio.to_thread(_call_openai)

        # Try parse as JSON.
        try:
            parsed = json.loads(content)
            sql = parsed.get("sql") or candidate_sql
            if not isinstance(sql, str) or not sql.strip():
                return candidate_sql
            return sql.strip()
        except Exception:
            # Fallback: extract SQL.
            return _extract_sql(content)


async def generate_sql(
    *,
    question: str,
    context: str,
    semantic_layer: SemanticLayer,
    plan: Dict[str, Any],
    mock_llm: bool,
    llm_api_key: Optional[str],
    llm_chat_model: str,
) -> SqlGenerationResult:
    base = build_sql_from_plan(semantic_layer=semantic_layer, plan=plan)
    metrics_used = base.metrics_used
    assumptions = list(base.assumptions)

    # Deterministic grounding: ensure the retrieved context mentions the metric formula/table we are about to use.
    # This is intentionally conservative and adds "assumptions" rather than changing the SQL.
    try:
        metric_def = get_metric_definition(semantic_layer, metrics_used[0]) if metrics_used else None
        if metric_def:
            ctx_l = (context or "").lower()
            formula_l = metric_def.formula.lower()
            table_l = metric_def.table.lower()
            if formula_l not in ctx_l:
                assumptions.append("RAG grounding check: retrieved context did not contain the exact metric formula text.")
            if table_l not in ctx_l:
                assumptions.append("RAG grounding check: retrieved context did not mention the metric source table.")
    except Exception:
        # Never block SQL generation due to a grounding-check failure in MVP.
        pass

    if mock_llm or not llm_api_key or OpenAI is None:
        assumptions.append("Using deterministic SQL builder (LLM disabled).")
        return SqlGenerationResult(sql=base.sql, metrics_used=metrics_used, assumptions=assumptions)

    # Best-effort: ask LLM to refine; deterministic validator still must pass.
    refiner = LlmSqlRefiner(api_key=llm_api_key, chat_model=llm_chat_model)
    refined_sql = await refiner.refine_sql(
        question=question,
        context=context,
        semantic_layer=semantic_layer,
        plan=plan,
        candidate_sql=base.sql,
    )
    return SqlGenerationResult(sql=refined_sql, metrics_used=metrics_used, assumptions=assumptions + ["LLM refinement applied."])

