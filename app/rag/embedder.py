from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
try:
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


@dataclass(frozen=True)
class EmbedderResult:
    vectors: np.ndarray  # shape: (n, dim)
    dim: int


class Embedder:
    dim: int

    def embed_texts(self, texts: List[str]) -> EmbedderResult:
        raise NotImplementedError


class HashEmbeddingBackend(Embedder):
    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed_texts(self, texts: List[str]) -> EmbedderResult:
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            seed = int.from_bytes(hashlib.sha256(t.encode("utf-8")).digest()[:8], "little", signed=False)
            rng = np.random.default_rng(seed)
            v = rng.normal(loc=0.0, scale=1.0, size=(self.dim,)).astype(np.float32)
            # L2 normalize for cosine similarity.
            denom = np.linalg.norm(v) + 1e-12
            vectors[i] = v / denom
        return EmbedderResult(vectors=vectors, dim=self.dim)


class OpenAIEmbeddingBackend(Embedder):
    def __init__(self, *, api_key: str, model: str, dim: Optional[int] = None):
        if OpenAI is None:
            raise RuntimeError("openai package not installed; cannot use OpenAI embeddings.")
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dim = int(dim) if dim is not None else 1536  # default for text-embedding-3-small

    def embed_texts(self, texts: List[str]) -> EmbedderResult:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        data = resp.data
        vectors = np.array([d.embedding for d in data], dtype=np.float32)
        # Normalize.
        norms = np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12
        vectors = vectors / norms
        return EmbedderResult(vectors=vectors, dim=vectors.shape[1])


def create_embedder(*, backend: str, openai_api_key: Optional[str], openai_embed_model: str) -> Embedder:
    backend = (backend or "auto").lower().strip()
    if backend == "openai":
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set when EMBEDDING_BACKEND=openai.")
        if OpenAI is None:
            raise RuntimeError("openai package not installed; cannot create OpenAI embedder.")
        return OpenAIEmbeddingBackend(api_key=openai_api_key, model=openai_embed_model)
    if backend == "hash":
        return HashEmbeddingBackend()

    # auto: prefer openai if key exists, else hash.
    if openai_api_key:
        if OpenAI is None:
            return HashEmbeddingBackend()
        return OpenAIEmbeddingBackend(api_key=openai_api_key, model=openai_embed_model)
    return HashEmbeddingBackend()

