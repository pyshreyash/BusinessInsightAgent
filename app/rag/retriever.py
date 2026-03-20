from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from app.rag.doc_builder import build_rag_documents
from app.rag.embedder import Embedder
from app.rag.faiss_store import FaissDocStore
from app.semantic.loader import SemanticLayer


@dataclass
class RagConfig:
    faiss_index_dir: str
    top_k: int = 5


class RagRetriever:
    def __init__(self, *, store: FaissDocStore, embedder: Embedder, cfg: RagConfig):
        self._store = store
        self._embedder = embedder
        self._cfg = cfg

    def retrieve_context(self, query: str) -> str:
        retrieved = self._store.retrieve(query, embedder=self._embedder, top_k=self._cfg.top_k)
        if not retrieved:
            return ""
        chunks = []
        for doc in retrieved:
            chunks.append(doc.text)
        return "\n\n".join(chunks)


def ensure_retriever(
    *,
    semantic_layer: SemanticLayer,
    business_rules_path: str,
    embedder: Embedder,
    faiss_index_dir: str,
    top_k: int = 5,
) -> RagRetriever:
    cfg = RagConfig(faiss_index_dir=faiss_index_dir, top_k=top_k)
    loaded = FaissDocStore.load(faiss_index_dir)
    if loaded is not None:
        return RagRetriever(store=loaded, embedder=embedder, cfg=cfg)

    docs = build_rag_documents(semantic_layer=semantic_layer, business_rules_path=business_rules_path)
    store = FaissDocStore.build(docs, embedder=embedder)
    store.save(faiss_index_dir)
    return RagRetriever(store=store, embedder=embedder, cfg=cfg)

