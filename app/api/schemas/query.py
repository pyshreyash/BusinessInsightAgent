from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)


class QueryResponse(BaseModel):
    sql: str = ""
    result: List[Dict[str, Any]] = Field(default_factory=list)
    insight: str = ""
    assumptions: List[str] = Field(default_factory=list)

