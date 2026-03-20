from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import logging


logger = logging.getLogger("biz-insights-copilot.langsmith")


@contextmanager
def langsmith_span(name: str, enabled: bool, attributes: Optional[Dict[str, Any]] = None) -> Iterator[None]:
    """
    Stub LangSmith integration point.

    In a real deployment, this would wrap calls with LangSmith tracing.
    """
    if not enabled:
        yield
        return

    # Keep MVP lightweight: no heavy setup required.
    logger.info("LangSmith span (stub): %s attrs=%s", name, attributes or {})
    yield

