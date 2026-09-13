from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .auth import AuthenticatedUser
from .fulltext import FullTextDocument, TextPage
from .workspaces import UserWorkspaceStore


_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "are", "was", "were",
    "una", "unos", "unas", "para", "con", "del", "los", "las", "que", "por", "como", "sobre",
    "or", "not", "but", "between", "using", "use", "used", "their", "there", "what",
    "cual", "cuáles", "donde", "cuando", "cómo", "qué", "cuales", "desde", "hasta",
}


@dataclass
class PaperMemoryStore:
    """Persistent, user-scoped cache of extracted PDF text.

    The cache stores the page-marked full text once. Page objects are reconstructed from
    the markers when needed, avoiding a second full copy of large PDFs in JSONB.
    """

    user: AuthenticatedUser
    folder_id: str

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)

    def get(self, paper_id: str) -> dict[str, Any] | None:
        rows = self.workspace._select(
            "scibrain_paper_memory",
            {
                "folder_id": f"eq.{self.folder_id}",
                "paper_id": f"eq.{paper_id}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    @staticmethod
    def _pages(row: dict[str, Any]) -> list[TextPage]:
        stored = row.get("pages") or []
        if stored:
            return [
                TextPage(page=int(item.get("page") or i + 1), text=str(item.get("text") or ""))
                for i, item in enumerate(stored)
            ]
        full_text = str(row.get("full_text") or "")
        if not full_text:
            return []
        parts = re.split(r"\[\[PAGE\s+(\d+)\]\]\s*\n?", full_text)
        pages: list[TextPage] = []
        if len(parts) > 1:
            for i in range(1, len(parts), 2):
                try:
                    page_no = int(parts[i])
                except (TypeError, ValueError):
                    continue
                text = parts[i + 1].strip() if i + 1 < len(parts) else ""
                pages.append(TextPage(page=page_no, text=text))
        if not pages:
            pages = [TextPage(page=1, text=full_text)]
        return pages

    def save_document(self, document: FullTextDocument) -> dict[str, Any]:
        full_text = document.text
        payload = {
            "owner_id": self.user.user_id,
            "folder_id": self.folder_id,
            "paper_id": document.paper_id,
            "source_url": document.source_url,
            "content_hash": hashlib.sha256(full_text.encode("utf-8", errors="ignore")).hexdigest(),
            "page_count": document.page_count,
            "word_count": len(re.findall(r"\S+", full_text)),
            "char_count": len(full_text),
            "full_text": full_text,
            "pages": [],
            "extraction_version": "pypdf-page-markers-v2",
        }
        existing = self.get(document.paper_id)
        if existing:
            return self.workspace._patch(
                "scibrain_paper_memory",
                {"memory_id": f"eq.{existing['memory_id']}"},
                payload,
            )
        return self.workspace._insert("scibrain_paper_memory", payload)

    def load_document(self, paper_id: str) -> FullTextDocument | None:
        row = self.get(paper_id)
        if not row:
            return None
        pages = self._pages(row)
        if not pages:
            return None
        return FullTextDocument(
            paper_id=paper_id,
            source_url=str(row.get("source_url") or "cached://paper-memory"),
            pages=pages,
        )

    def search_pages(self, paper_id: str, question: str, max_pages: int = 8) -> list[dict[str, Any]]:
        row = self.get(paper_id)
        if not row:
            return []
        pages = self._pages(row)
        terms = {
            token.lower()
            for token in re.findall(r"[A-Za-zÀ-ÿ0-9_\-]{3,}", question)
            if token.lower() not in _STOPWORDS
        }
        ranked: list[tuple[int, int, str]] = []
        for item in pages:
            low = item.text.lower()
            score = sum(low.count(term) for term in terms)
            ranked.append((score, item.page, item.text))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        positive = [item for item in ranked if item[0] > 0]
        chosen = (positive or ranked)[: max(1, min(max_pages, 12))]
        chosen.sort(key=lambda x: x[1])
        return [{"score": score, "page": page, "text": text} for score, page, text in chosen]

    def status(self, paper_id: str) -> dict[str, Any]:
        row = self.get(paper_id)
        if not row:
            return {"cached": False, "paper_id": paper_id}
        return {
            "cached": True,
            "paper_id": paper_id,
            "page_count": row.get("page_count"),
            "word_count": row.get("word_count"),
            "char_count": row.get("char_count"),
            "content_hash": row.get("content_hash"),
            "source_url": row.get("source_url"),
            "updated_at": row.get("updated_at"),
        }
