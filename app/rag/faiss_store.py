from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np

from app.rag.embedder import Embedder


@dataclass(frozen=True)
class RetrievedDoc:
    text: str
    score: float


class FaissDocStore:
    def __init__(self, *, index: faiss.Index, docs: List[str], dim: int):
        self._index = index
        self._docs = docs
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @classmethod
    def build(cls, docs: List[str], embedder: Embedder) -> "FaissDocStore":
        emb = embedder.embed_texts(docs)
        vectors = emb.vectors.astype(np.float32)

        # Cosine similarity via inner product of normalized vectors.
        index = faiss.IndexFlatIP(emb.dim)
        index.add(vectors)
        return cls(index=index, docs=docs, dim=emb.dim)

    def save(self, dir_path: str) -> None:
        base = Path(dir_path)
        base.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._index, str(base / "index.faiss"))
        (base / "docs.json").write_text(json.dumps(self._docs, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, dir_path: str) -> Optional["FaissDocStore"]:
        base = Path(dir_path)
        index_path = base / "index.faiss"
        docs_path = base / "docs.json"
        if not index_path.exists() or not docs_path.exists():
            return None

        index = faiss.read_index(str(index_path))
        docs = json.loads(docs_path.read_text(encoding="utf-8"))
        dim = int(index.d)
        return cls(index=index, docs=docs, dim=dim)

    def retrieve(self, query: str, *, embedder: Embedder, top_k: int = 5) -> List[RetrievedDoc]:
        emb = embedder.embed_texts([query])
        q = emb.vectors.astype(np.float32)
        scores, ids = self._index.search(q, top_k)

        out: List[RetrievedDoc] = []
        for score, idx in zip(scores[0].tolist(), ids[0].tolist()):
            if idx < 0:
                continue
            out.append(RetrievedDoc(text=self._docs[idx], score=float(score)))
        return out

