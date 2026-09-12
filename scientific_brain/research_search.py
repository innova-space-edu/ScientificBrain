from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import quote_plus

import httpx

from .discovery import ArxivClient, OpenAlexClient
from .fulltext import arxiv_pdf_url, unpaywall_pdf_url
from .taxonomy import load_taxonomy


def _clean_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value or None


def _key(result: dict[str, Any]) -> str:
    if result.get("doi"):
        return "doi:" + str(result["doi"]).lower()
    if result.get("arxiv_id"):
        return "arxiv:" + str(result["arxiv_id"]).lower()
    if result.get("url"):
        return "url:" + str(result["url"]).lower().rstrip("/")
    return "title:" + re.sub(r"\W+", "", str(result.get("title") or "").lower())


def _manual_message(result: dict[str, Any]) -> str | None:
    if result.get("pdf_url"):
        return None
    doi = result.get("doi")
    url = result.get("url")
    if doi and url:
        return f"Full text not resolved automatically. Search manually using DOI {doi} or open the source link."
    if doi:
        return f"Full text not resolved automatically. Search manually using DOI {doi}."
    if url:
        return "Full text not resolved automatically. Open the source link and upload the PDF manually if available."
    return "Full text not resolved automatically. Search manually by title/authors and upload the PDF if available."


@dataclass
class ResearchSearchResult:
    title: str
    result_type: str
    source: str
    url: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    authors: list[str] = field(default_factory=list)
    publication_date: str | None = None
    journal: str | None = None
    abstract: str | None = None
    pdf_url: str | None = None
    access_status: str = "metadata_only"
    manual_lookup_required: bool = True
    manual_lookup_message: str | None = None
    cited_by_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class ResearchSearchService:
    """Research Agent search layer.

    Scientific discovery works without a commercial web-search key through OpenAlex,
    arXiv and Crossref. Tavily/Brave are optional extensions for general web pages.
    Full text is never claimed as available unless a PDF URL is actually resolved.
    """

    def __init__(self, taxonomy_path: str = "config/plasma_taxonomy.yaml") -> None:
        self.taxonomy = load_taxonomy(taxonomy_path)
        self.email = os.getenv("UNPAYWALL_EMAIL") or os.getenv("OPENALEX_MAILTO")

    def search(
        self,
        query: str,
        *,
        from_year: int = 1900,
        max_results: int = 50,
        include_web: bool = True,
        resolve_open_access: bool = True,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("Research search query is required")
        per_source = max(5, min(50, max_results))
        collected: list[dict[str, Any]] = []
        used_sources: list[str] = []
        errors: list[dict[str, str]] = []

        for source_name, fn in (
            ("openalex", lambda: self._openalex(query, from_year, per_source)),
            ("arxiv", lambda: self._arxiv(query, per_source)),
            ("crossref", lambda: self._crossref(query, from_year, per_source)),
        ):
            try:
                rows = fn()
                collected.extend(rows)
                used_sources.append(source_name)
            except Exception as exc:
                errors.append({"source": source_name, "error": f"{type(exc).__name__}: {exc}"})

        if include_web:
            for source_name, fn in (
                ("tavily", lambda: self._tavily(query, per_source)),
                ("brave", lambda: self._brave(query, per_source)),
            ):
                try:
                    rows = fn()
                    if rows:
                        collected.extend(rows)
                        used_sources.append(source_name)
                except Exception as exc:
                    errors.append({"source": source_name, "error": f"{type(exc).__name__}: {exc}"})

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in collected:
            key = _key(row)
            if not row.get("title") or key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        # Prefer papers over generic web pages and then citation-rich/recent records.
        deduped.sort(
            key=lambda r: (
                0 if r.get("result_type") == "paper" else 1,
                -(int(r.get("cited_by_count") or 0)),
                str(r.get("publication_date") or ""),
            )
        )
        deduped = deduped[:max_results]

        if resolve_open_access:
            for row in deduped:
                self._resolve_access(row)
        else:
            for row in deduped:
                row["manual_lookup_required"] = not bool(row.get("pdf_url"))
                row["manual_lookup_message"] = _manual_message(row)

        return {
            "query": query,
            "sources": used_sources,
            "results": deduped,
            "errors": errors,
            "general_web_enabled": bool(os.getenv("TAVILY_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY")),
        }

    def _openalex(self, query: str, from_year: int, limit: int) -> list[dict[str, Any]]:
        client = OpenAlexClient(self.taxonomy, mailto=self.email)
        rows = []
        for paper in client.search(query, from_year=from_year, per_page=limit):
            rows.append({
                "title": paper.title,
                "result_type": "paper",
                "source": "openalex",
                "url": str(paper.url) if paper.url else (f"https://doi.org/{paper.doi}" if paper.doi else None),
                "doi": _clean_doi(paper.doi),
                "arxiv_id": paper.arxiv_id,
                "authors": paper.authors,
                "publication_date": paper.publication_date.isoformat() if paper.publication_date else None,
                "journal": paper.journal,
                "abstract": paper.abstract,
                "cited_by_count": paper.cited_by_count,
                "canonical_id": paper.canonical_id,
            })
        return rows

    def _arxiv(self, query: str, limit: int) -> list[dict[str, Any]]:
        client = ArxivClient(self.taxonomy)
        rows = []
        for paper in client.search(query, max_results=limit):
            rows.append({
                "title": paper.title,
                "result_type": "paper",
                "source": "arxiv",
                "url": str(paper.url) if paper.url else None,
                "doi": _clean_doi(paper.doi),
                "arxiv_id": paper.arxiv_id,
                "authors": paper.authors,
                "publication_date": paper.publication_date.isoformat() if paper.publication_date else None,
                "journal": paper.journal,
                "abstract": paper.abstract,
                "pdf_url": arxiv_pdf_url(paper.arxiv_id) if paper.arxiv_id else None,
                "access_status": "open_access" if paper.arxiv_id else "metadata_only",
                "manual_lookup_required": not bool(paper.arxiv_id),
                "canonical_id": paper.canonical_id,
            })
        return rows

    def _crossref(self, query: str, from_year: int, limit: int) -> list[dict[str, Any]]:
        params = {
            "query.bibliographic": query,
            "rows": min(limit, 100),
            "filter": f"from-pub-date:{from_year}-01-01",
            "select": "DOI,title,author,published-print,published-online,container-title,URL,abstract,is-referenced-by-count,type",
        }
        headers = {"User-Agent": f"ScientificBrain/0.4 ({self.email or 'research-agent'})"}
        response = httpx.get("https://api.crossref.org/works", params=params, headers=headers, timeout=30)
        response.raise_for_status()
        rows: list[dict[str, Any]] = []
        for item in response.json().get("message", {}).get("items", []):
            titles = item.get("title") or []
            if not titles:
                continue
            parts = (item.get("published-online") or item.get("published-print") or {}).get("date-parts") or []
            pub_date = None
            if parts and parts[0]:
                p = parts[0]
                pub_date = f"{p[0]:04d}" + (f"-{p[1]:02d}" if len(p) > 1 else "") + (f"-{p[2]:02d}" if len(p) > 2 else "")
            authors = []
            for author in item.get("author") or []:
                name = " ".join(x for x in [author.get("given"), author.get("family")] if x)
                if name:
                    authors.append(name)
            doi = _clean_doi(item.get("DOI"))
            rows.append({
                "title": titles[0],
                "result_type": "paper",
                "source": "crossref",
                "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
                "doi": doi,
                "authors": authors,
                "publication_date": pub_date,
                "journal": (item.get("container-title") or [None])[0],
                "abstract": item.get("abstract"),
                "cited_by_count": int(item.get("is-referenced-by-count") or 0),
                "canonical_id": f"doi:{doi.lower()}" if doi else None,
            })
        return rows

    def _tavily(self, query: str, limit: int) -> list[dict[str, Any]]:
        key = os.getenv("TAVILY_API_KEY", "").strip()
        if not key:
            return []
        response = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": query, "search_depth": "advanced", "max_results": min(limit, 20), "include_answer": False},
            timeout=30,
        )
        response.raise_for_status()
        return [{
            "title": item.get("title") or item.get("url") or "Web result",
            "result_type": "web",
            "source": "tavily",
            "url": item.get("url"),
            "abstract": item.get("content"),
            "access_status": "metadata_only",
        } for item in response.json().get("results", [])]

    def _brave(self, query: str, limit: int) -> list[dict[str, Any]]:
        key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        if not key:
            return []
        response = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(limit, 20), "safesearch": "moderate"},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
            timeout=30,
        )
        response.raise_for_status()
        return [{
            "title": item.get("title") or item.get("url") or "Web result",
            "result_type": "web",
            "source": "brave",
            "url": item.get("url"),
            "abstract": item.get("description"),
            "access_status": "metadata_only",
        } for item in (response.json().get("web") or {}).get("results", [])]

    def _resolve_access(self, row: dict[str, Any]) -> None:
        if row.get("pdf_url"):
            row["access_status"] = "open_access"
            row["manual_lookup_required"] = False
            row["manual_lookup_message"] = None
            return
        if row.get("arxiv_id"):
            row["pdf_url"] = arxiv_pdf_url(str(row["arxiv_id"]))
            row["access_status"] = "open_access"
            row["manual_lookup_required"] = False
            row["manual_lookup_message"] = None
            return
        doi = _clean_doi(row.get("doi"))
        if doi and self.email:
            try:
                pdf = unpaywall_pdf_url(doi, self.email, timeout=12.0)
                if pdf:
                    row["pdf_url"] = pdf
                    row["access_status"] = "open_access"
                    row["manual_lookup_required"] = False
                    row["manual_lookup_message"] = None
                    return
            except Exception:
                pass
        row["access_status"] = "manual_download" if (doi or row.get("url")) else "unavailable"
        row["manual_lookup_required"] = True
        row["manual_lookup_message"] = _manual_message(row)
