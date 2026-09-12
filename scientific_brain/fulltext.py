from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

import httpx
from pypdf import PdfReader

from .models import Paper


DEFAULT_MAX_PDF_BYTES = 80 * 1024 * 1024


@dataclass
class TextPage:
    page: int
    text: str


@dataclass
class FullTextDocument:
    paper_id: str
    source_url: str
    pages: list[TextPage]

    @property
    def text(self) -> str:
        return "\n\n".join(f"[[PAGE {p.page}]]\n{p.text}" for p in self.pages)

    @property
    def page_count(self) -> int:
        return len(self.pages)


def extract_pdf_bytes(paper_id: str, source_url: str, data: bytes) -> FullTextDocument:
    reader = PdfReader(BytesIO(data))
    pages: list[TextPage] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(TextPage(page=index, text=text.strip()))
    if not any(page.text for page in pages):
        raise ValueError("PDF contains no extractable text; a layout/OCR parser is required")
    return FullTextDocument(paper_id=paper_id, source_url=source_url, pages=pages)


def fetch_pdf(url: str, max_bytes: int = DEFAULT_MAX_PDF_BYTES, timeout: float = 60.0) -> bytes:
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").lower()
        if "pdf" not in content_type and not str(response.url).lower().endswith(".pdf"):
            raise ValueError(f"Resolved resource is not a PDF: {content_type or 'unknown content type'}")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(f"PDF exceeds ingestion limit of {max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)


def arxiv_pdf_url(arxiv_id: str) -> str:
    clean = arxiv_id.strip().removeprefix("arXiv:")
    return f"https://arxiv.org/pdf/{clean}.pdf"


def unpaywall_pdf_url(doi: str, email: str, timeout: float = 30.0) -> str | None:
    clean = doi.strip().removeprefix("https://doi.org/")
    response = httpx.get(
        f"https://api.unpaywall.org/v2/{clean}",
        params={"email": email},
        timeout=timeout,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    candidates: Iterable[dict] = [
        payload.get("best_oa_location") or {},
        *(payload.get("oa_locations") or []),
    ]
    for location in candidates:
        if not location:
            continue
        url = location.get("url_for_pdf")
        if url:
            return url
    return None


def resolve_open_access_pdf(paper: Paper, unpaywall_email: str | None = None) -> str | None:
    if paper.arxiv_id:
        return arxiv_pdf_url(paper.arxiv_id)
    if paper.url and str(paper.url).lower().endswith(".pdf"):
        return str(paper.url)
    email = unpaywall_email or os.getenv("UNPAYWALL_EMAIL")
    if paper.doi and email:
        return unpaywall_pdf_url(paper.doi, email)
    return None


def ingest_open_access_paper(
    paper: Paper,
    *,
    unpaywall_email: str | None = None,
    max_bytes: int = DEFAULT_MAX_PDF_BYTES,
) -> FullTextDocument:
    url = resolve_open_access_pdf(paper, unpaywall_email=unpaywall_email)
    if not url:
        raise ValueError(
            "No open-access PDF could be resolved. Provide the paper text/PDF explicitly or configure UNPAYWALL_EMAIL."
        )
    data = fetch_pdf(url, max_bytes=max_bytes)
    return extract_pdf_bytes(paper.canonical_id, url, data)
