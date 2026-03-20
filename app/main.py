from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI

from app.api.routes.query import router as query_router
from app.db.connection import PostgresConnectionManager
from app.db.seed import build_seed_data
from app.observability.logging import configure_logging, log_event
from app.rag.embedder import create_embedder
from app.rag.retriever import ensure_retriever
from app.semantic.loader import load_semantic_layer
from app.semantic.validator import validate_semantic_layer
from app.agents.workflow import build_agent_graph
from app.utils.env import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger("biz-insights-copilot")

    log_event("startup_begin", {"semantic_layer_path": settings.semantic_layer_path})

    # Semantic layer
    semantic_layer = load_semantic_layer(settings.semantic_layer_path)
    semantic_errors = validate_semantic_layer(semantic_layer, known_tables=["fact_sales", "dim_product", "dim_time"])
    if semantic_errors:
        # MVP: fail fast on misconfiguration.
        for e in semantic_errors:
            logger.error("Semantic layer error: %s - %s", e.code, e.message)
        raise RuntimeError("Invalid semantic layer configuration; aborting startup.")

    # Embeddings + RAG index
    embedder = create_embedder(
        backend=settings.embedding_backend,
        openai_api_key=settings.openai_api_key,
        openai_embed_model=settings.openai_embed_model,
    )
    rag = ensure_retriever(
        semantic_layer=semantic_layer,
        business_rules_path=settings.business_rules_path,
        embedder=embedder,
        faiss_index_dir=settings.faiss_index_dir,
    )

    # Postgres connection
    db = PostgresConnectionManager(settings.postgres_dsn)
    await db.connect()
    await db.init_schema()
    if settings.seed_on_startup:
        seed_data = build_seed_data()
        await db.seed_if_empty(seed_data)

    # Build workflow graph
    graph = await build_agent_graph(semantic_layer=semantic_layer, rag=rag, db_manager=db, settings=settings)

    app.state.runtime = {"settings": settings, "semantic_layer": semantic_layer, "rag": rag, "db": db, "graph": graph}

    log_event("startup_complete", {"faiss_loaded": True})
    try:
        yield
    finally:
        log_event("shutdown_begin", {})
        await db.close()
        log_event("shutdown_complete", {})


app = FastAPI(title="AI Business Insights Copilot", version="0.1.0", lifespan=lifespan)
app.include_router(query_router, prefix="/api")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok"}

