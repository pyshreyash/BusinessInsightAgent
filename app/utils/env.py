from __future__ import annotations

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    semantic_layer_path: str = Field(
        default="config/semantic_layer.yaml",
        description="Path to YAML semantic layer configuration.",
    )
    business_rules_path: str = Field(
        default="config/business_rules.yaml",
        description="Path to YAML business rules configuration.",
    )

    postgres_dsn: str = Field(default="postgresql://postgres:postgres@localhost:5432/bi_copilot")
    seed_on_startup: bool = Field(default=True, description="Seed mock tables/data on startup.")

    faiss_index_dir: str = Field(default="data/faiss_index", description="Local directory for FAISS index files.")
    embedding_backend: str = Field(default="auto", description="auto|openai|hash")
    openai_embed_model: str = Field(default="text-embedding-3-small")
    openai_chat_model: str = Field(default="gpt-4o-mini")
    openai_api_key: Optional[str] = Field(default=None, description="OPENAI_API_KEY (optional; enables LLM/RAG embeddings if set).")

    mock_llm: bool = Field(
        default=False,
        description="If true, never call the LLM (deterministic SQL+insight heuristics only).",
    )

    webhook_url: Optional[str] = Field(default=None, description="Optional webhook URL for action triggers.")
    log_level: str = Field(default="INFO")

    langsmith_enabled: bool = Field(
        default=False,
        description="If true, attach minimal LangSmith hooks (stub behavior in MVP).",
    )

    # Retry loop for validator failures.
    sql_generation_max_retries: int = Field(default=2)

    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE") or None,
        extra="ignore",
    )


def get_settings() -> Settings:
    # Allow quick override with explicit ENV var injection patterns.
    return Settings()

