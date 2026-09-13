from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .auth import AuthenticatedUser
from .usage import UsageRecorder
from .workspaces import UserWorkspaceStore


DEFAULT_EMBEDDING_DIMENSIONS = 768


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _dimensions() -> int:
    try:
        value = int(os.getenv("SCIBRAIN_EMBEDDING_DIMENSIONS", str(DEFAULT_EMBEDDING_DIMENSIONS)))
    except ValueError:
        value = DEFAULT_EMBEDDING_DIMENSIONS
    # Database schema is deliberately fixed at 768 to keep the vector index stable.
    return DEFAULT_EMBEDDING_DIMENSIONS if value != DEFAULT_EMBEDDING_DIMENSIONS else value


def _timeout() -> float:
    raw = os.getenv("SCIBRAIN_EMBEDDING_TIMEOUT_MS") or os.getenv("EDUAI_AI_PROVIDER_TIMEOUT_MS") or "60000"
    try:
        return max(5.0, float(raw) / 1000.0)
    except ValueError:
        return 60.0


def format_document(text: str, title: str | None = None) -> str:
    clean_title = (title or "none").replace("\n", " ").strip() or "none"
    return f"title: {clean_title} | text: {text.strip()}"


def format_query(query: str) -> str:
    return f"task: question answering | query: {query.strip()}"


@dataclass
class GeminiEmbeddingProvider:
    """Gemini Embedding 2 client using 768-dimensional normalized vectors."""

    api_key: str | None = None
    model: str = ""
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS

    def __post_init__(self) -> None:
        self.api_key = self.api_key or _first_env("GEMINI_API_KEY_TEXT", "GEMINI_API_KEY")
        self.model = self.model or os.getenv("SCIBRAIN_EMBEDDING_MODEL", "gemini-embedding-2")
        self.dimensions = _dimensions()
        self.base_url = os.getenv(
            "GOOGLE_GENERATIVE_LANGUAGE_BASE",
            "https://generativelanguage.googleapis.com/v1beta",
        ).rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _values(self, payload: dict[str, Any]) -> list[float]:
        embedding = payload.get("embedding") or {}
        values = embedding.get("values") or []
        if not values and payload.get("embeddings"):
            values = (payload["embeddings"][0] or {}).get("values") or []
        vector = [float(x) for x in values]
        if len(vector) != self.dimensions:
            raise RuntimeError(
                f"Embedding dimension mismatch: expected {self.dimensions}, got {len(vector)}"
            )
        return vector

    def embed_query(self, query: str) -> list[float]:
        if not self.available:
            raise RuntimeError("Gemini embedding provider is not configured")
        response = httpx.post(
            f"{self.base_url}/models/{self.model}:embedContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": str(self.api_key)},
            json={
                "content": {"parts": [{"text": format_query(query)}]},
                "output_dimensionality": self.dimensions,
            },
            timeout=_timeout(),
        )
        response.raise_for_status()
        return self._values(response.json())

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []
        if not self.available:
            raise RuntimeError("Gemini embedding provider is not configured")
        requests = [
            {
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": text}]},
                "output_dimensionality": self.dimensions,
            }
            for text in documents
        ]
        response = httpx.post(
            f"{self.base_url}/models/{self.model}:batchEmbedContents",
            headers={"Content-Type": "application/json", "x-goog-api-key": str(self.api_key)},
            json={"requests": requests},
            timeout=max(_timeout(), 90.0),
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("embeddings") or []
        vectors: list[list[float]] = []
        for item in raw:
            values = [float(x) for x in ((item or {}).get("values") or [])]
            if len(values) != self.dimensions:
                raise RuntimeError(
                    f"Embedding dimension mismatch: expected {self.dimensions}, got {len(values)}"
                )
            vectors.append(values)
        if len(vectors) != len(documents):
            raise RuntimeError(
                f"Embedding batch mismatch: requested {len(documents)}, received {len(vectors)}"
            )
        return vectors


@dataclass
class SemanticPaperRetrieval:
    user: AuthenticatedUser
    folder_id: str

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)
        self.provider = GeminiEmbeddingProvider()
        self.usage = UsageRecorder(self.user, self.folder_id)

    def _paper_title(self, paper_id: str) -> str:
        rows = self.workspace._select(
            "scibrain_folder_papers",
            {
                "folder_id": f"eq.{self.folder_id}",
                "canonical_id": f"eq.{paper_id}",
                "select": "title",
                "limit": "1",
            },
        )
        return str(rows[0].get("title") or "none") if rows else "none"

    def embedding_status(self, paper_id: str) -> dict[str, Any]:
        rows = self.workspace._select(
            "scibrain_paper_chunks",
            {
                "folder_id": f"eq.{self.folder_id}",
                "paper_id": f"eq.{paper_id}",
                "select": "chunk_id,embedding,embedding_model",
                "limit": "1000",
            },
        )
        embedded = sum(row.get("embedding") is not None for row in rows)
        return {
            "configured": self.provider.available,
            "model": self.provider.model,
            "dimensions": self.provider.dimensions,
            "chunks": len(rows),
            "embedded_chunks": embedded,
            "complete": bool(rows) and embedded == len(rows),
        }

    def ensure_embeddings(self, paper_id: str, max_chunks: int = 160, batch_size: int = 20) -> dict[str, Any]:
        if not self.provider.available:
            return {"configured": False, "embedded": 0, "model": self.provider.model}
        max_chunks = max(0, min(int(max_chunks), 400))
        if max_chunks == 0:
            return self.embedding_status(paper_id)
        rows = self.workspace._select(
            "scibrain_paper_chunks",
            {
                "folder_id": f"eq.{self.folder_id}",
                "paper_id": f"eq.{paper_id}",
                "embedding": "is.null",
                "select": "chunk_id,chunk_index,section_label,text",
                "order": "chunk_index.asc",
                "limit": str(max_chunks),
            },
        )
        if not rows:
            return self.embedding_status(paper_id)
        title = self._paper_title(paper_id)
        started = time.perf_counter()
        completed = 0
        size = max(1, min(int(batch_size), 32))
        for start in range(0, len(rows), size):
            batch = rows[start : start + size]
            documents = [
                format_document(str(row.get("text") or ""), title=title)
                for row in batch
            ]
            vectors = self.provider.embed_documents(documents)
            items = [
                {"chunk_id": row["chunk_id"], "embedding": vector}
                for row, vector in zip(batch, vectors)
            ]
            response = httpx.post(
                f"{self.workspace.url}/rest/v1/rpc/scibrain_upsert_chunk_embeddings",
                headers=self.workspace.headers,
                json={
                    "p_folder_id": self.folder_id,
                    "p_paper_id": paper_id,
                    "p_model": self.provider.model,
                    "p_dimensions": self.provider.dimensions,
                    "p_items": items,
                },
                timeout=max(self.workspace.timeout, 60.0),
            )
            response.raise_for_status()
            completed += len(batch)
        duration_ms = int((time.perf_counter() - started) * 1000)
        self.usage.record(
            "paper_embeddings_generated",
            paper_id=paper_id,
            duration_ms=duration_ms,
            metadata={
                "model": self.provider.model,
                "dimensions": self.provider.dimensions,
                "chunks": completed,
            },
        )
        status = self.embedding_status(paper_id)
        status.update({"embedded_now": completed, "duration_ms": duration_ms})
        return status

    def search(self, paper_id: str, query: str, limit: int = 12) -> list[dict[str, Any]]:
        if not self.provider.available or not query.strip():
            return []
        # Fill a bounded amount of legacy/unembedded memory on first use. This is idempotent.
        try:
            self.ensure_embeddings(
                paper_id,
                max_chunks=int(os.getenv("SCIBRAIN_LAZY_EMBED_MAX_CHUNKS", "160")),
            )
        except Exception:
            # Keyword retrieval remains the safe fallback.
            pass
        started = time.perf_counter()
        try:
            vector = self.provider.embed_query(query)
            response = httpx.post(
                f"{self.workspace.url}/rest/v1/rpc/scibrain_hybrid_search_paper_chunks",
                headers=self.workspace.headers,
                json={
                    "p_folder_id": self.folder_id,
                    "p_paper_id": paper_id,
                    "p_query": query,
                    "p_query_embedding": vector,
                    "p_limit": max(1, min(int(limit), 30)),
                    "p_semantic_weight": float(os.getenv("SCIBRAIN_SEMANTIC_WEIGHT", "0.72")),
                },
                timeout=self.workspace.timeout,
            )
            response.raise_for_status()
            rows = response.json()
            self.usage.record(
                "semantic_paper_search",
                paper_id=paper_id,
                duration_ms=int((time.perf_counter() - started) * 1000),
                metadata={"model": self.provider.model, "hits": len(rows)},
            )
            return rows
        except Exception:
            return []
