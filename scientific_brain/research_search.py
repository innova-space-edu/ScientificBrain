from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .discovery import ArxivClient
from .fulltext import arxiv_pdf_url, unpaywall_pdf_url
from .taxonomy import load_taxonomy

ACCESS_RANK = {
    "open_access": 6,
    "public_full_text": 5,
    "oa_landing_page": 4,
    "public_page": 3,
    "restricted_or_unknown": 2,
    "metadata_only": 1,
    "unavailable": 0,
}


def _clean_doi(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value).strip(), flags=re.I)
    return text.rstrip("/") or None


def _host(url: str | None) -> str:
    try:
        return urlparse(str(url or "")).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _looks_like_pdf(url: str | None) -> bool:
    value = str(url or "").lower().split("?", 1)[0]
    return value.endswith(".pdf") or "/pdf/" in value or value.startswith("https://arxiv.org/pdf/")


def _title_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _key(row: dict[str, Any]) -> str:
    if row.get("doi"):
        return "doi:" + str(row["doi"]).lower()
    if row.get("arxiv_id"):
        return "arxiv:" + str(row["arxiv_id"]).lower()
    title = _title_key(row.get("title"))
    if len(title) >= 12:
        return "title:" + title
    return "url:" + str(row.get("url") or row.get("title") or "").lower().rstrip("/")


def _merge_results(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    out = dict(left)
    for key, value in right.items():
        if value not in (None, "", [], {}) and out.get(key) in (None, "", [], {}):
            out[key] = value
    if ACCESS_RANK.get(str(right.get("access_status")), 0) > ACCESS_RANK.get(str(out.get("access_status")), 0):
        for key in ("access_status", "pdf_url", "url", "license", "host_type", "oa_status", "is_open_access", "is_public_full_text", "manual_lookup_required", "manual_lookup_message"):
            if key in right:
                out[key] = right.get(key)
    elif right.get("pdf_url") and not out.get("pdf_url"):
        out["pdf_url"] = right["pdf_url"]
        out["manual_lookup_required"] = False
    out["cited_by_count"] = max(int(left.get("cited_by_count") or 0), int(right.get("cited_by_count") or 0))
    return out


def _manual_message(row: dict[str, Any]) -> str | None:
    if row.get("pdf_url"):
        return None
    status = row.get("access_status")
    if status == "oa_landing_page":
        return "Open-access landing page found; direct PDF was not resolved automatically."
    if status == "public_page":
        return "Public page found; direct full text was not verified automatically."
    if row.get("doi"):
        return f"Direct full text was not verified. Check authorized access using DOI {row['doi']}."
    return "Direct full text was not verified. Open the source or upload an authorized PDF."


class ResearchSearchService:
    """Discover literature and classify access without equating public pages with OA."""

    def __init__(self, taxonomy_path: str = "config/plasma_taxonomy.yaml") -> None:
        self.taxonomy = load_taxonomy(taxonomy_path)
        self.email = os.getenv("UNPAYWALL_EMAIL") or os.getenv("OPENALEX_MAILTO")

    def search(self, query: str, *, from_year: int = 1900, max_results: int = 50, include_web: bool = True, resolve_open_access: bool = True) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("Research search query is required")
        per_source = max(5, min(50, max_results))
        rows: list[dict[str, Any]] = []
        used: list[str] = []
        errors: list[dict[str, str]] = []
        sources = [
            ("openalex", lambda: self._openalex(query, from_year, per_source)),
            ("arxiv", lambda: self._arxiv(query, per_source)),
            ("semantic_scholar", lambda: self._semantic_scholar(query, from_year, per_source)),
            ("crossref", lambda: self._crossref(query, from_year, per_source)),
        ]
        if include_web:
            sources += [("tavily", lambda: self._tavily(query, per_source)), ("brave", lambda: self._brave(query, per_source))]
        for name, fn in sources:
            try:
                found = fn()
                if found:
                    rows.extend(found)
                    used.append(name)
            except Exception as exc:
                errors.append({"source": name, "error": f"{type(exc).__name__}: {exc}"})

        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in rows:
            if not row.get("title"):
                continue
            key = _key(row)
            if key not in merged:
                merged[key] = row
                order.append(key)
            else:
                merged[key] = _merge_results(merged[key], row)
        results = [merged[k] for k in order]
        if resolve_open_access:
            for row in results:
                self._resolve_access(row)
        results.sort(key=lambda r: (0 if r.get("result_type") == "paper" else 1, -ACCESS_RANK.get(str(r.get("access_status")), 0), -int(r.get("cited_by_count") or 0)))
        results = results[:max_results]
        counts: dict[str, int] = {}
        for row in results:
            status = str(row.get("access_status") or "metadata_only")
            counts[status] = counts.get(status, 0) + 1
        return {"query": query, "sources": used, "results": results, "errors": errors, "access_counts": counts, "general_web_enabled": bool(os.getenv("TAVILY_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY"))}

    def _openalex(self, query: str, from_year: int, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"search": query, "filter": f"from_publication_date:{from_year}-01-01", "per-page": min(limit, 100)}
        if self.email:
            params["mailto"] = self.email
        data = httpx.get("https://api.openalex.org/works", params=params, timeout=30).raise_for_status().json()
        out = []
        for work in data.get("results", []):
            title = work.get("title") or ""
            if not title:
                continue
            doi = _clean_doi(work.get("doi"))
            oa = work.get("open_access") or {}
            locations = [work.get("best_oa_location") or {}, *(work.get("locations") or [])]
            best = next((x for x in locations if x.get("pdf_url")), next((x for x in locations if x.get("landing_page_url")), {}))
            pdf = best.get("pdf_url")
            landing = best.get("landing_page_url") or (work.get("primary_location") or {}).get("landing_page_url")
            is_oa = bool(oa.get("is_oa"))
            ids = work.get("ids") or {}
            arxiv_id = str(ids.get("arxiv") or "").rsplit("/", 1)[-1] or None
            status = "open_access" if is_oa and pdf else "oa_landing_page" if is_oa else "metadata_only"
            abstract_index = work.get("abstract_inverted_index") or {}
            words = sorted((pos, word) for word, positions in abstract_index.items() for pos in positions)
            out.append({
                "title": title, "result_type": "paper", "source": "openalex", "url": landing or (f"https://doi.org/{doi}" if doi else work.get("id")),
                "doi": doi, "arxiv_id": arxiv_id, "authors": [a.get("author", {}).get("display_name", "") for a in work.get("authorships", []) if a.get("author")],
                "publication_date": work.get("publication_date"), "journal": ((work.get("primary_location") or {}).get("source") or {}).get("display_name"),
                "abstract": " ".join(word for _, word in words), "pdf_url": pdf, "access_status": status, "is_open_access": is_oa,
                "is_public_full_text": bool(pdf), "oa_status": oa.get("oa_status"), "license": best.get("license"), "host_type": best.get("source", {}).get("type") if isinstance(best.get("source"), dict) else None,
                "manual_lookup_required": not bool(pdf), "cited_by_count": int(work.get("cited_by_count") or 0),
                "canonical_id": f"doi:{doi.lower()}" if doi else f"arxiv:{arxiv_id}" if arxiv_id else f"openalex:{str(work.get('id') or '').rsplit('/',1)[-1]}",
            })
        return out

    def _arxiv(self, query: str, limit: int) -> list[dict[str, Any]]:
        out = []
        for paper in ArxivClient(self.taxonomy).search(query, max_results=limit):
            pdf = arxiv_pdf_url(paper.arxiv_id) if paper.arxiv_id else None
            out.append({"title": paper.title, "result_type": "paper", "source": "arxiv", "url": str(paper.url) if paper.url else None, "doi": _clean_doi(paper.doi), "arxiv_id": paper.arxiv_id, "authors": paper.authors, "publication_date": paper.publication_date.isoformat() if paper.publication_date else None, "journal": paper.journal, "abstract": paper.abstract, "pdf_url": pdf, "access_status": "open_access" if pdf else "metadata_only", "is_open_access": bool(pdf), "is_public_full_text": bool(pdf), "oa_status": "green", "host_type": "repository", "manual_lookup_required": not bool(pdf), "canonical_id": paper.canonical_id})
        return out

    def _semantic_scholar(self, query: str, from_year: int, limit: int) -> list[dict[str, Any]]:
        fields = "title,authors,year,abstract,venue,url,citationCount,externalIds,openAccessPdf"
        data = httpx.get("https://api.semanticscholar.org/graph/v1/paper/search", params={"query": query, "limit": min(limit, 50), "fields": fields}, headers={"User-Agent": "ScientificBrain/0.9"}, timeout=30).raise_for_status().json()
        out = []
        for item in data.get("data", []):
            year = int(item.get("year") or 0)
            if year and year < from_year:
                continue
            ids = item.get("externalIds") or {}
            doi, arxiv_id = _clean_doi(ids.get("DOI")), ids.get("ArXiv")
            pdf = (item.get("openAccessPdf") or {}).get("url")
            out.append({"title": item.get("title") or "", "result_type": "paper", "source": "semantic_scholar", "url": item.get("url"), "doi": doi, "arxiv_id": arxiv_id, "authors": [a.get("name", "") for a in item.get("authors") or [] if a.get("name")], "publication_date": str(year) if year else None, "journal": item.get("venue"), "abstract": item.get("abstract") or "", "pdf_url": pdf, "access_status": "open_access" if pdf else "metadata_only", "is_open_access": bool(pdf), "is_public_full_text": bool(pdf), "host_type": "repository" if pdf else None, "manual_lookup_required": not bool(pdf), "cited_by_count": int(item.get("citationCount") or 0), "canonical_id": f"doi:{doi.lower()}" if doi else f"arxiv:{arxiv_id}" if arxiv_id else f"s2:{item.get('paperId')}"})
        return out

    def _crossref(self, query: str, from_year: int, limit: int) -> list[dict[str, Any]]:
        params = {"query.bibliographic": query, "rows": min(limit, 100), "filter": f"from-pub-date:{from_year}-01-01"}
        items = httpx.get("https://api.crossref.org/works", params=params, headers={"User-Agent": "ScientificBrain/0.9"}, timeout=30).raise_for_status().json().get("message", {}).get("items", [])
        out = []
        for item in items:
            titles = item.get("title") or []
            if not titles:
                continue
            doi = _clean_doi(item.get("DOI"))
            authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in item.get("author") or []]
            out.append({"title": titles[0], "result_type": "paper", "source": "crossref", "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else None), "doi": doi, "authors": [x for x in authors if x], "journal": (item.get("container-title") or [None])[0], "abstract": item.get("abstract") or "", "cited_by_count": int(item.get("is-referenced-by-count") or 0), "access_status": "metadata_only", "canonical_id": f"doi:{doi.lower()}" if doi else None})
        return out

    def _web_rows(self, items: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
        out = []
        for item in items:
            url = item.get("url")
            host = _host(url)
            pdf = _looks_like_pdf(url)
            status = "public_full_text" if pdf else "public_page" if "researchgate.net" in host else "metadata_only"
            out.append({"title": item.get("title") or url or "Web result", "result_type": "web", "source": source, "url": url, "abstract": item.get("content") or item.get("description"), "pdf_url": url if pdf else None, "access_status": status, "is_open_access": False, "is_public_full_text": pdf, "host_type": host or None, "manual_lookup_required": not pdf})
        return out

    def _tavily(self, query: str, limit: int) -> list[dict[str, Any]]:
        key = os.getenv("TAVILY_API_KEY", "").strip()
        if not key:
            return []
        data = httpx.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "search_depth": "advanced", "max_results": min(limit, 20)}, timeout=30).raise_for_status().json()
        return self._web_rows(data.get("results", []), "tavily")

    def _brave(self, query: str, limit: int) -> list[dict[str, Any]]:
        key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        if not key:
            return []
        data = httpx.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": min(limit, 20)}, headers={"Accept": "application/json", "X-Subscription-Token": key}, timeout=30).raise_for_status().json()
        return self._web_rows((data.get("web") or {}).get("results", []), "brave")

    def _resolve_access(self, row: dict[str, Any]) -> None:
        if row.get("pdf_url"):
            if row.get("access_status") not in {"open_access", "public_full_text"}:
                row["access_status"] = "open_access" if row.get("is_open_access") else "public_full_text"
            row["is_public_full_text"] = True
            row["manual_lookup_required"] = False
            row["manual_lookup_message"] = None
            return
        if row.get("arxiv_id"):
            row.update({"pdf_url": arxiv_pdf_url(str(row["arxiv_id"])), "access_status": "open_access", "is_open_access": True, "is_public_full_text": True, "oa_status": row.get("oa_status") or "green", "host_type": row.get("host_type") or "repository", "manual_lookup_required": False, "manual_lookup_message": None})
            return
        doi = _clean_doi(row.get("doi"))
        if doi and self.email:
            try:
                pdf = unpaywall_pdf_url(doi, self.email, timeout=12.0)
                if pdf:
                    row.update({"pdf_url": pdf, "access_status": "open_access", "is_open_access": True, "is_public_full_text": True, "manual_lookup_required": False, "manual_lookup_message": None})
                    return
            except Exception:
                pass
        if _looks_like_pdf(row.get("url")):
            row.update({"pdf_url": row["url"], "access_status": "public_full_text", "is_public_full_text": True, "manual_lookup_required": False, "manual_lookup_message": None})
            return
        host = _host(row.get("url"))
        row["access_status"] = "public_page" if "researchgate.net" in host else "oa_landing_page" if row.get("is_open_access") else "restricted_or_unknown" if (doi or row.get("url")) else "unavailable"
        row["manual_lookup_required"] = True
        row["manual_lookup_message"] = _manual_message(row)
