from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def log_event(event: str, payload: Optional[Dict[str, Any]] = None) -> None:
    logger = logging.getLogger("biz-insights-copilot")
    if payload is None:
        logger.info(event)
        return
    logger.info("%s %s", event, json.dumps(payload, default=str))


@contextmanager
def timing_span(span_name: str, extra: Optional[Dict[str, Any]] = None) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        payload = {"span": span_name, "elapsed_ms": elapsed_ms}
        if extra:
            payload.update(extra)
        log_event("timing_span", payload)

