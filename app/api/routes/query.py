from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request

from app.api.schemas.query import QueryRequest, QueryResponse


router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(payload: QueryRequest, request: Request) -> QueryResponse:
    runtime = request.app.state.runtime
    graph = runtime["graph"]

    state_in: Dict[str, Any] = {"question": payload.question}
    state_out = await graph.ainvoke(state_in)

    return QueryResponse(
        sql=state_out.get("sql") or "",
        result=state_out.get("result") or [],
        insight=state_out.get("insight") or "",
        assumptions=state_out.get("assumptions") or [],
    )

