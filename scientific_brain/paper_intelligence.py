from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import httpx

from .auth import AuthenticatedUser
from .fulltext import FullTextDocument, fetch_pdf, resolve_open_access_pdf
from .models import Paper
from .user_snapshot import UserSnapshotStore
from .workspaces import UserWorkspaceStore

try:  # Optional at import time; installed in web/runtime dependencies.
    import fitz  # type: ignore
except Exception:  # pragma: no cover - graceful fallback for minimal environments
    fitz = None


_STANDARD_HEADINGS = {
    "abstract", "resumen", "introduction", "introducción", "background", "methods", "methodology",
    "materials and methods", "métodos", "metodología", "results", "resultados", "discussion", "discusión",
    "conclusion", "conclusions", "conclusión", "conclusiones", "references", "referencias", "appendix", "apéndice",
}
_FIGURE_RE = re.compile(r"^\s*(fig(?:ure)?|figura)\s*\.?\s*([0-9]+[a-z]?)\s*[:.\-]?\s*(.{4,700})$", re.I)
_TABLE_RE = re.compile(r"^\s*(table|tabla)\s*\.?\s*([0-9]+[a-z]?)\s*[:.\-]?\s*(.{4,700})$", re.I)
_SECTION_NUMBER_RE = re.compile(r"^\s*(?:[IVXLC]+\.?|\d+(?:\.\d+){0,4}\.?)\s+\S+")
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_\-]{3,}")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "are", "was", "were", "using", "used",
    "una", "unos", "unas", "para", "con", "del", "los", "las", "que", "por", "como", "sobre", "entre",
    "what", "which", "where", "when", "cual", "cuáles", "donde", "cuando", "cómo", "qué", "desde", "hasta",
}


def _hash(text: str | bytes) -> str:
    raw = text if isinstance(text, bytes) else text.encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def _heading_candidate(line: str) -> bool:
    text = re.sub(r"\s+", " ", line).strip()
    if not text or len(text) > 120 or len(text.split()) > 14:
        return False
    low = text.lower().strip(" .:-")
    if low in _STANDARD_HEADINGS:
        return True
    if _SECTION_NUMBER_RE.match(text):
        return True
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > 0.86


def _equation_candidate(line: str) -> bool:
    text = re.sub(r"\s+", " ", line).strip()
    if len(text) < 5 or len(text) > 260 or "=" not in text:
        return False
    if "http://" in text.lower() or "https://" in text.lower() or "@" in text:
        return False
    math_signals = sum(token in text for token in ("=", "+", "−", "-", "×", "*", "/", "^", "_", "∂", "∇", "Δ", "Σ", "π", "λ", "μ", "ω"))
    return math_signals >= 2 and bool(re.search(r"[A-Za-zΑ-ω0-9]", text))


def _page_section(text: str) -> str | None:
    for raw in text.splitlines()[:45]:
        line = raw.strip()
        if _heading_candidate(line):
            return re.sub(r"\s+", " ", line)[:120]
    return None


def build_structure(document: FullTextDocument) -> dict[str, Any]:
    headings: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for page in document.pages:
        for raw in page.text.splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if _heading_candidate(line):
                key = (page.page, line.lower())
                if key not in seen:
                    headings.append({"page": page.page, "title": line[:120]})
                    seen.add(key)
    return {
        "headings": headings[:160],
        "page_count": document.page_count,
        "extraction": "text+layout_inventory",
    }


def chunk_document(document: FullTextDocument, target_chars: int = 5200, overlap_chars: int = 500) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    index = 0
    for page in document.pages:
        text = page.text.strip()
        if not text:
            continue
        section = _page_section(text)
        start = 0
        while start < len(text):
            end = min(len(text), start + target_chars)
            if end < len(text):
                split_at = text.rfind("\n\n", start + max(1000, target_chars // 2), end)
                if split_at > start:
                    end = split_at
            piece = text[start:end].strip()
            if piece:
                chunks.append({
                    "chunk_index": index,
                    "page_start": page.page,
                    "page_end": page.page,
                    "section_label": section,
                    "kind": "text",
                    "text": piece,
                    "content_hash": _hash(piece),
                    "token_estimate": max(1, len(piece) // 4),
                    "metadata": {"char_start": start, "char_end": end},
                })
                index += 1
            if end >= len(text):
                break
            start = max(start + 1, end - overlap_chars)
    return chunks


def extract_text_assets(document: FullTextDocument) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for page in document.pages:
        equation_count = 0
        for raw in page.text.splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if not line:
                continue
            match = _FIGURE_RE.match(line)
            if match:
                caption = match.group(3).strip()
                assets.append({
                    "page": page.page, "asset_type": "figure_caption", "label": f"Figure {match.group(2)}",
                    "caption": caption, "text": line, "content_hash": _hash(f"fig:{page.page}:{line}"),
                    "metadata": {"source": "caption_text", "confidence": "heuristic"},
                })
                continue
            match = _TABLE_RE.match(line)
            if match:
                caption = match.group(3).strip()
                assets.append({
                    "page": page.page, "asset_type": "table_caption", "label": f"Table {match.group(2)}",
                    "caption": caption, "text": line, "content_hash": _hash(f"table:{page.page}:{line}"),
                    "metadata": {"source": "caption_text", "confidence": "heuristic"},
                })
                continue
            if equation_count < 16 and _equation_candidate(line):
                assets.append({
                    "page": page.page, "asset_type": "equation_candidate", "label": None,
                    "caption": None, "text": line, "content_hash": _hash(f"eq:{page.page}:{line}"),
                    "metadata": {"source": "extracted_text", "confidence": "heuristic"},
                })
                equation_count += 1
    return assets


def visual_inventory(pdf_bytes: bytes | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not pdf_bytes or fitz is None:
        return [], {"renderer": "unavailable" if fitz is None else "not_provided", "visual_pages": 0}
    assets: list[dict[str, Any]] = []
    pages_with_visuals = 0
    embedded_images = 0
    drawing_objects = 0
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for i in range(len(doc)):
            page = doc[i]
            images = page.get_images(full=True)
            drawings = page.get_drawings()
            embedded_images += len(images)
            drawing_objects += len(drawings)
            if images or drawings:
                pages_with_visuals += 1
                meta = {
                    "embedded_image_count": len(images),
                    "vector_drawing_count": len(drawings),
                    "width_pt": float(page.rect.width),
                    "height_pt": float(page.rect.height),
                    "renderable": True,
                }
                assets.append({
                    "page": i + 1,
                    "asset_type": "visual_page_inventory",
                    "label": f"Page {i + 1}",
                    "caption": None,
                    "text": None,
                    "content_hash": _hash(json.dumps(meta, sort_keys=True) + f":{i+1}"),
                    "metadata": meta,
                })
        doc.close()
    except Exception as exc:
        return [], {"renderer": "pymupdf", "error": f"{type(exc).__name__}: {exc}", "visual_pages": 0}
    return assets, {
        "renderer": "pymupdf",
        "visual_pages": pages_with_visuals,
        "embedded_images": embedded_images,
        "vector_drawing_objects": drawing_objects,
    }


def render_pdf_page(pdf_bytes: bytes, page_number: int, dpi: int = 150) -> bytes:
    if fitz is None:
        raise RuntimeError("PyMuPDF is required for visual paper analysis")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page_number < 1 or page_number > len(doc):
            raise ValueError(f"page_number must be between 1 and {len(doc)}")
        page = doc[page_number - 1]
        scale = max(1.0, min(float(dpi) / 72.0, 3.2))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


@dataclass
class PaperIntelligenceStore:
    user: AuthenticatedUser
    folder_id: str

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)

    def _bulk_insert(self, table: str, rows: list[dict[str, Any]], batch_size: int = 40) -> None:
        if not rows:
            return
        # Keep PostgREST requests bounded even for very large papers. A single huge JSON
        # payload is more likely to hit function/network limits than several idempotent batches.
        for start in range(0, len(rows), max(1, batch_size)):
            batch = rows[start : start + batch_size]
            response = httpx.post(
                self.workspace._endpoint(table),
                headers={**self.workspace.headers, "Prefer": "return=minimal"},
                json=batch,
                timeout=max(self.workspace.timeout, 60.0),
            )
            response.raise_for_status()

    def index_document(self, document: FullTextDocument, pdf_bytes: bytes | None = None) -> dict[str, Any]:
        structure = build_structure(document)
        chunks = chunk_document(document)
        text_assets = extract_text_assets(document)
        visual_assets, visual_summary = visual_inventory(pdf_bytes)
        assets = text_assets + visual_assets

        self.workspace._delete("scibrain_paper_chunks", {
            "folder_id": f"eq.{self.folder_id}", "paper_id": f"eq.{document.paper_id}",
        })
        self.workspace._delete("scibrain_paper_assets", {
            "folder_id": f"eq.{self.folder_id}", "paper_id": f"eq.{document.paper_id}",
        })

        owner_id = self.user.user_id
        self._bulk_insert("scibrain_paper_chunks", [
            {"owner_id": owner_id, "folder_id": self.folder_id, "paper_id": document.paper_id, **row}
            for row in chunks
        ])
        self._bulk_insert("scibrain_paper_assets", [
            {"owner_id": owner_id, "folder_id": self.folder_id, "paper_id": document.paper_id, **row}
            for row in assets
        ])

        counts: dict[str, int] = {}
        for item in assets:
            counts[item["asset_type"]] = counts.get(item["asset_type"], 0) + 1
        summary = {
            **counts,
            "chunks": len(chunks),
            "visual": visual_summary,
        }
        memory_rows = self.workspace._select("scibrain_paper_memory", {
            "folder_id": f"eq.{self.folder_id}", "paper_id": f"eq.{document.paper_id}",
            "select": "memory_id", "limit": "1",
        })
        if memory_rows:
            self.workspace._patch("scibrain_paper_memory", {"memory_id": f"eq.{memory_rows[0]['memory_id']}"}, {
                "structure": structure,
                "asset_summary": summary,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            })
        return {"structure": structure, "asset_summary": summary, "chunk_count": len(chunks)}

    def get_structure(self, paper_id: str) -> dict[str, Any]:
        rows = self.workspace._select("scibrain_paper_memory", {
            "folder_id": f"eq.{self.folder_id}", "paper_id": f"eq.{paper_id}",
            "select": "paper_id,page_count,word_count,structure,asset_summary,indexed_at,updated_at", "limit": "1",
        })
        return rows[0] if rows else {"paper_id": paper_id, "structure": {}, "asset_summary": {}}

    def list_assets(self, paper_id: str, asset_type: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
        params = {
            "folder_id": f"eq.{self.folder_id}", "paper_id": f"eq.{paper_id}",
            "select": "asset_id,page,asset_type,label,caption,text,metadata,created_at",
            "order": "page.asc,created_at.asc", "limit": str(max(1, min(limit, 500))),
        }
        if asset_type:
            params["asset_type"] = f"eq.{asset_type}"
        return self.workspace._select("scibrain_paper_assets", params)

    def search_chunks(self, paper_id: str, query: str, limit: int = 12) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            response = httpx.post(
                f"{self.workspace.url}/rest/v1/rpc/scibrain_search_paper_chunks",
                headers=self.workspace.headers,
                json={
                    "p_folder_id": self.folder_id,
                    "p_paper_id": paper_id,
                    "p_query": query,
                    "p_limit": max(1, min(limit, 30)),
                },
                timeout=self.workspace.timeout,
            )
            response.raise_for_status()
            rows = response.json()
        except httpx.HTTPError:
            # Symbols and field-specific notation can be awkward for websearch_to_tsquery.
            # Retrieval must remain available through the deterministic lexical fallback.
            rows = []
        if rows:
            return rows

        # Fallback for equations, symbols, and very short queries that FTS may tokenize poorly.
        all_rows = self.workspace._select("scibrain_paper_chunks", {
            "folder_id": f"eq.{self.folder_id}", "paper_id": f"eq.{paper_id}",
            "select": "chunk_id,chunk_index,page_start,page_end,section_label,kind,text",
            "order": "chunk_index.asc", "limit": "300",
        })
        terms = {t.lower() for t in _TOKEN_RE.findall(query) if t.lower() not in _STOPWORDS}
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in all_rows:
            low = str(row.get("text") or "").lower()
            score = sum(low.count(term) for term in terms)
            scored.append((score, row))
        scored.sort(key=lambda x: (-x[0], int(x[1].get("chunk_index") or 0)))
        chosen = [row for score, row in scored if score > 0][:limit]
        if not chosen:
            chosen = [row for _, row in scored[:limit]]
        for row in chosen:
            row["rank"] = 0.0
        return chosen

    def cache_visual_analysis(self, paper_id: str, page: int, question: str, answer: str, page_png: bytes) -> dict[str, Any]:
        key = _hash(page_png + question.strip().lower().encode("utf-8", errors="ignore"))
        existing = self.workspace._select("scibrain_paper_assets", {
            "folder_id": f"eq.{self.folder_id}", "paper_id": f"eq.{paper_id}",
            "asset_type": "eq.visual_analysis", "content_hash": f"eq.{key}", "select": "*", "limit": "1",
        })
        payload = {
            "owner_id": self.user.user_id, "folder_id": self.folder_id, "paper_id": paper_id,
            "page": page, "asset_type": "visual_analysis", "label": f"Visual analysis p.{page}",
            "caption": question, "text": answer, "content_hash": key,
            "metadata": {"question": question, "page_render_hash": _hash(page_png), "source": "multimodal_model"},
        }
        return existing[0] if existing else self.workspace._insert("scibrain_paper_assets", payload)

    def find_cached_visual_analysis(self, paper_id: str, page: int, question: str, page_png: bytes) -> dict[str, Any] | None:
        key = _hash(page_png + question.strip().lower().encode("utf-8", errors="ignore"))
        rows = self.workspace._select("scibrain_paper_assets", {
            "folder_id": f"eq.{self.folder_id}", "paper_id": f"eq.{paper_id}",
            "asset_type": "eq.visual_analysis", "content_hash": f"eq.{key}", "select": "*", "limit": "1",
        })
        return rows[0] if rows else None


def resolve_pdf_bytes(user: AuthenticatedUser, folder_id: str, paper_id: str) -> tuple[str, bytes]:
    snapshot = UserSnapshotStore(user, folder_id=folder_id)
    private_pdf = snapshot.fetch_paper_pdf(paper_id)
    if private_pdf:
        return private_pdf

    workspace = UserWorkspaceStore(user)
    rows = workspace._select("scibrain_folder_papers", {
        "folder_id": f"eq.{folder_id}", "canonical_id": f"eq.{paper_id}",
        "select": "record,pdf_url,access_url,source_url", "limit": "1",
    })
    if not rows:
        raise KeyError("paper_not_found")
    row = rows[0]
    for candidate in (row.get("pdf_url"), row.get("access_url"), row.get("source_url")):
        url = str(candidate or "").strip()
        if url and (url.lower().endswith(".pdf") or "arxiv.org/pdf/" in url.lower()):
            return url, fetch_pdf(url)
    record = row.get("record") or {}
    paper = Paper.model_validate(record)
    url = resolve_open_access_pdf(paper, unpaywall_email=os.getenv("UNPAYWALL_EMAIL"))
    if not url:
        raise ValueError("paper PDF is not available for visual analysis")
    return url, fetch_pdf(url)
