from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from app.actions.triggers import trigger_action
from app.agents.business_rules import BusinessRuleSet
from app.agents.planner import initial_assumptions, plan_query
from app.agents.state import QueryState
from app.observability.logging import log_event, timing_span
from app.rag.retriever import RagRetriever
from app.semantic.loader import SemanticLayer
from app.sql.generator import generate_sql
from app.sql.validation import validate_sql


logger = logging.getLogger("biz-insights-copilot.agent")


def _analyze_week_over_week(
    *,
    question: str,
    metric: str,
    rows: List[Dict[str, Any]],
    business_rules: BusinessRuleSet,
) -> Dict[str, Any]:
    assumptions: List[str] = initial_assumptions(question)

    if not rows:
        return {
            "insight": "No data returned for the requested time window.",
            "assumptions": assumptions + ["Assumes data exists for the latest week window in `dim_time`. (No rows returned.)"],
        }

    # Expect columns: week, revenue
    # Choose numeric value column heuristically.
    value_key = None
    for k in ["revenue", "quantity_sold"]:
        if any(k in r for r in rows):
            value_key = k
            break
    if value_key is None:
        # Fallback: take first non-week key.
        keys = list(rows[0].keys())
        value_key = next((k for k in keys if k.lower() != "week"), None)

    if value_key is None:
        return {
            "insight": "Unable to interpret SQL result shape for insight generation.",
            "assumptions": assumptions + ["Assumes SQL result includes a time-series metric column."],
        }

    # Determine latest and previous week by week index.
    def to_int(x: Any) -> Optional[int]:
        try:
            return int(x)
        except Exception:
            return None

    parsed_rows = []
    for r in rows:
        w = to_int(r.get("week"))
        v = r.get(value_key)
        if w is None:
            continue
        try:
            v_f = float(v)
        except Exception:
            continue
        parsed_rows.append((w, v_f))

    if len(parsed_rows) < 2:
        return {
            "insight": "Not enough time points returned to compare week-over-week change.",
            "assumptions": assumptions + ["Assumes the SQL includes at least two weeks for comparison."],
        }

    latest_week, latest_value = max(parsed_rows, key=lambda x: x[0])
    prev_week, prev_value = sorted(parsed_rows, key=lambda x: x[0])[-2]

    if prev_value == 0:
        pct_change = float("inf") if latest_value != 0 else 0.0
    else:
        pct_change = (latest_value - prev_value) / prev_value

    abs_pct = abs(pct_change) if pct_change != float("inf") else float("inf")

    direction = "stable"
    keyword = None
    if pct_change <= -business_rules.revenue_drop_threshold:
        direction = "drop"
        keyword = "drop"
    elif pct_change >= business_rules.revenue_increase_threshold:
        direction = "increase"
        keyword = "increase"
    elif abs_pct >= business_rules.anomaly_abs_percent_change:
        direction = "anomaly"
        keyword = "anomaly"

    metric_label = "revenue" if metric == "revenue" else "quantity_sold"
    pct_display = "N/A" if pct_change == float("inf") else f"{pct_change * 100:.1f}%"

    insight = f"{metric_label.capitalize()} {direction} of {pct_display} in week {latest_week} compared to week {prev_week}."

    caveats: List[str] = [
        "MVP caveat: insight is based on aggregate week-over-week change only (no driver decomposition).",
        "Assumes `week` indexes in `dim_time` reflect consecutive periods.",
    ]
    if keyword:
        insight += " Possible anomaly detected." if keyword == "anomaly" else ""

    return {"insight": insight, "assumptions": assumptions + caveats}


async def build_agent_graph(*, semantic_layer: SemanticLayer, rag: RagRetriever, db_manager: Any, settings: Any) -> Any:
    """
    Build and compile the LangGraph agent workflow.

    db_manager must provide:
      - execute_select(sql) -> List[Dict[str, Any]]
    """

    from app.agents.business_rules import load_business_rules

    business_rules: BusinessRuleSet = load_business_rules(settings.business_rules_path)

    openai_key = getattr(settings, "openai_api_key", None)  # optional in settings

    graph: StateGraph[QueryState] = StateGraph(QueryState)

    async def planner_node(state: QueryState) -> Dict[str, Any]:
        question = state["question"]
        with timing_span("planner"):
            plan = plan_query(question)
            assumptions = initial_assumptions(question)
            log_event("planner_input", {"question": question})
        return {"plan": plan, "assumptions": assumptions, "retry_count": state.get("retry_count", 0), "errors": []}

    async def retriever_node(state: QueryState) -> Dict[str, Any]:
        question = state["question"]
        with timing_span("retriever"):
            context = rag.retrieve_context(question)
        log_event("retriever_context", {"question": question, "context_len": len(context)})
        return {"context": context}

    async def sql_generator_node(state: QueryState) -> Dict[str, Any]:
        question = state["question"]
        plan = state.get("plan") or {}
        context = state.get("context") or ""
        retry_count = int(state.get("retry_count", 0))

        with timing_span("sql_generation", {"retry_count": retry_count}):
            res = await generate_sql(
                question=question,
                context=context,
                semantic_layer=semantic_layer,
                plan=plan,
                mock_llm=settings.mock_llm,
                llm_api_key=openai_key,
                llm_chat_model=settings.openai_chat_model,
            )
        log_event("generated_sql", {"sql": res.sql, "metrics_used": res.metrics_used})

        # Validate and potentially refine assumptions.
        return {"sql": res.sql, "metrics_used": res.metrics_used, "assumptions": state.get("assumptions", []) + res.assumptions, "retry_count": retry_count}

    async def sql_validator_node(state: QueryState) -> Dict[str, Any]:
        sql = state.get("sql") or ""
        retry_count = int(state.get("retry_count", 0))
        with timing_span("sql_validation"):
            v = validate_sql(sql=sql, semantic_layer=semantic_layer)

        if v.ok:
            return {"validation_ok": True, "validation_errors": [], "validation_ok_reason": "OK"}

        errors_payload = [
            {"code": e.code, "message": e.message, "details": e.details} for e in (v.errors or [])
        ]
        log_event("sql_validation_errors", {"errors": errors_payload})

        # Increment retry count when validation fails so conditional routing can be pure.
        next_retry = retry_count + 1
        return {
            "validation_ok": False,
            "validation_errors": errors_payload,
            "errors": [e.message for e in (v.errors or [])],
            "retry_count": next_retry,
        }

    async def executor_node(state: QueryState) -> Dict[str, Any]:
        sql = state.get("sql") or ""
        with timing_span("sql_execution"):
            rows = await db_manager.execute_select(sql)
        log_event("execution_complete", {"rows": len(rows)})
        return {"result": rows}

    async def analyzer_node(state: QueryState) -> Dict[str, Any]:
        question = state["question"]
        plan = state.get("plan") or {}
        metric = plan.get("metric") or "revenue"
        rows = state.get("result") or []

        with timing_span("analysis"):
            analysis = _analyze_week_over_week(
                question=question,
                metric=metric,
                rows=rows,
                business_rules=business_rules,
            )

        return {"insight": analysis.get("insight") or "", "assumptions": analysis.get("assumptions") or []}

    async def action_trigger_node(state: QueryState) -> Dict[str, Any]:
        insight = state.get("insight") or ""
        result = state.get("result") or []

        with timing_span("action_trigger"):
            triggered = await trigger_action(
                insight=insight,
                result=result,
                webhook_url=settings.webhook_url,
            )
        return {"action_triggered": triggered.triggered}

    async def error_node(state: QueryState) -> Dict[str, Any]:
        errors = state.get("errors") or []
        sql = state.get("sql") or ""
        insight = "Unable to answer the question due to deterministic SQL validation errors."
        assumptions = list(state.get("assumptions") or [])
        assumptions.append("Fix required: validator rejected the generated SQL.")
        return {
            "sql": sql,
            "result": [],
            "insight": insight,
            "assumptions": assumptions,
            "errors": errors,
        }

    graph.add_node("planner", planner_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("sql_generator", sql_generator_node)
    graph.add_node("sql_validator", sql_validator_node)
    graph.add_node("executor", executor_node)
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("action_trigger", action_trigger_node)
    graph.add_node("error", error_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "retriever")
    graph.add_edge("retriever", "sql_generator")
    graph.add_edge("sql_generator", "sql_validator")

    def decide_after_validation(state: QueryState) -> str:
        ok = bool(state.get("validation_ok"))
        retry_count = int(state.get("retry_count", 0))
        max_retries = int(getattr(settings, "sql_generation_max_retries", 2))
        if ok:
            return "executor"
        # `retry_count` starts at 0 (initial attempt). Each validation failure increments it.
        # Allow up to `max_retries` retries after the initial attempt.
        if retry_count <= max_retries:
            return "sql_generator"
        return "error"

    graph.add_conditional_edges(
        "sql_validator",
        decide_after_validation,
        {"executor": "executor", "sql_generator": "sql_generator", "error": "error"},
    )

    graph.add_edge("executor", "analyzer")
    graph.add_edge("analyzer", "action_trigger")
    graph.add_edge("action_trigger", END)
    graph.add_edge("error", END)

    return graph.compile()

