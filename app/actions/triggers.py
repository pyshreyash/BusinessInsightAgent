from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx


logger = logging.getLogger("biz-insights-copilot.actions")


@dataclass(frozen=True)
class TriggerResult:
    triggered: bool
    reason: Optional[str] = None


def _insight_keywords(insight: str) -> List[str]:
    return re.findall(r"\b(drop|increase|anomaly)\b", insight.lower())


async def trigger_action(
    *,
    insight: str,
    result: List[Dict[str, Any]],
    webhook_url: Optional[str],
) -> TriggerResult:
    keywords = _insight_keywords(insight)
    if not keywords:
        return TriggerResult(triggered=False)

    reason = f"Insight contained keyword(s): {', '.join(sorted(set(keywords)))}"
    logger.warning("Action trigger fired: %s", reason)

    # MVP: always console alert.
    logger.warning("ALERT: %s", insight)

    if webhook_url:
        payload = {"insight": insight, "keywords": sorted(set(keywords)), "result": result}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(webhook_url, json=payload)
        except Exception:
            logger.exception("Webhook trigger failed (ignored in MVP).")

    return TriggerResult(triggered=True, reason=reason)

