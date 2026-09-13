from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from .discovery import ArxivClient
from .fulltext import arxiv_pdf_url, unpaywall_pdf_url
from .taxonomy import load_taxonomy


def _clean_doi(value: str | None) -> str | None:
    if not value:
        return None
    value = str(value).strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value or None


def _invert_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    words: list[tuple[int, str]] = []
    for word, indexes in index.items():
        words.extend((int(i), word) for i in indexes)
    return " ".join(word for _, word in sorted(words))


def _key(row: dict[str, Any]) -> str:
    if row.get("doi"):
        return "doi:" + str(row["doi"]).lower()
    if row.get("arxiv_id"):
        return "arxiv:" + str(row["arxiv_id"]).lower()
    if row.get("canonical_id"):
        return str(row["canonical_id"]).lower()
    if row.get("url"):
        return "url:" + str(row["url"]).lower().rstrip("/")
    return "title:" + re.sub(r"\W+", "", str(row.get("title") or "").lower())


def _domain(url: str | None) -> str:
    try:
        return urlparse(str(url or "")).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _is_pdf_url(url: str | None) -> bool:
    value = str(url or "").lower().split("?", 1)[0]
    return value.endswith(".pdf") or "/pdf/" in value or value.endswith("/pdf")


def _manual_message(row: dict[str, Any]) -> str | None:
    if row.get("system_can_read"):
        return None
    kind = row.get("access_kind")
    doi = row.get("doi")
    if kind == "open_access":
        return "Open Access confirmado, pero no se resolvió un PDF directo. Abre la fuente pública y adjunta el PDF para análisis de texto completo."
    if kind == "public_copy":
        return "Hay una copia pública, pero ScientificBrain no asume que su licencia sea Open Access. Abre la fuente y adjunta el PDF si corresponde."
    if kind in {"public_page", "public_repository"}:
        return "La fuente es pública, pero no se resolvió un PDF directo. Puedes abrirla y adjuntar el PDF."
    if doi:
        return f"Open Access no confirmado. Usa el DOI {doi} para comprobar acceso o localizar una copia pública."
    if row.get("url"):
        return "Open Access no confirmado. Abre la fuente para comprobar si existe una copia pública."
    return "No se resolvió acceso al texto completo. Busca por título/autores y adjunta el PDF si corresponde."


def _set_access(
    row: dict[str, Any], *, kind: str, label: str, reason: str,
    pdf_url: str | None = None, public_url: str | None = None,
    system_can_read: bool = False, coarse_status: str = "metadata_only",
    oa_status: str | None = None, license_name: str | None = None,
) -> None:
    if pdf_url:
        row["pdf_url"] = pdf_url
    row["public_url"] = public_url or pdf_url or row.get("url")
    row["access_kind"] = kind
    row["access_label"] = label
    row["access_reason"] = reason
    row["system_can_read"] = bool(system_can_read)
    row["access_status"] = coarse_status
    row["oa_status"] = oa_status
    row["license"] = license_name
    row["manual_lookup_required"] = not bool(system_can_read)
    row["manual_lookup_message"] = _manual_message(row)


def _classify_web_access(row: dict[str, Any]) -> None:
    url = row.get("url")
    domain = _domain(url)
    if "researchgate.net" in domain:
        _set_access(
            row, kind="public_copy", label="Copia pública · ResearchGate",
            reason="ResearchGate puede mostrar una copia pública, pero una copia pública no implica automáticamente una licencia Open Access.",
            public_url=url, system_can_read=False, coarse_status="manual_download",
        )
    elif _is_pdf_url(url):
        _set_access(
            row, kind="public_pdf", label="PDF público · licencia no verificada",
            reason="Se detectó un PDF público directo; su licencia Open Access no fue verificada.",
            pdf_url=url, public_url=url, system_can_read=True, coarse_status="metadata_only",
        )
    else:
        _set_access(
            row, kind="public_page", label="Página pública",
            reason="La página es pública, pero no se confirmó un PDF ni una licencia Open Access.",
            public_url=url, system_can_read=False, coarse_status="metadata_only",
        )


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
    public_url: str | None = None
    access_status: str = "metadata_only"
    access_kind: str = "unknown"
    access_label: str = "Acceso no verificado"
    access_reason: str = ""
    system_can_read: bool = False
    manual_lookup_required: bool = True
    manual_lookup_message: str | None = None
    cited_by_count: int = 0
    oa_status: str | None = None
    license: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class ResearchSearchService:
    """Discovery with explicit access provenance.

    Open Access is used only when arXiv, OpenAlex or Unpaywall confirms it.
    Public pages/copies such as ResearchGate are labeled separately.
    """

    def __init__(self, taxonomy_path: str = "config/plasma_taxonomy.yaml") -> None:
        self.taxonomy = load_taxonomy(taxonomy_path)
        self.email = os.getenv("UNPAYWALL_EMAIL") or os.getenv("OPENALEX_MAILTO")

    def search(self, query: str, *, from_year: int = 1900, max_results: int = 50,
               include_web: bool = True, resolve_open_access: bool = True) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("Research search query is required")
        per_source = max(5, min(50, max_results))
        collected: list[dict[str, Any]] = []
        used_sources: list[str] = []
        errors: list[dict[str, str]] = []
        sources = (
            ("openalex", lambda: self._openalex(query, from_year, per_source)),
            ("arxiv", lambda: self._arxiv(query, per_source)),
            ("crossref", lambda: self._crossref(query, from_year, per_source)),
        )
        for name, fn in sources:
            try:
                collected.extend(fn())
                used_sources.append(name)
            except Exception as exc:
                errors.append({"source": name, "error": f"{type(exc).__name__}: {exc}"})
        if include_web:
            for name, fn in (("tavily", lambda: self._tavily(query, per_source)), ("brave", lambda: self._brave(query, per_source))):
                try:
                    rows = fn()
                    if rows:
                        collected.extend(rows)
                        used_sources.append(name)
                except Exception as exc:
                    errors.append({"source": name, "error": f"{type(exc).__name__}: {exc}"})

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in collected:
            key = _key(row)
            if not row.get("title") or key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        for row in deduped:
            if resolve_open_access:
                self._resolve_access(row)
            elif not row.get("access_kind") or row.get("access_kind") == "unknown":
                if row.get("result_type") == "web":
                    _classify_web_access(row)
                else:
                    _set_access(row, kind="closed_or_unknown", label="Open Access no confirmado",
                                reason="No se ejecutó resolución de Open Access.", public_url=row.get("url"),
                                system_can_read=bool(row.get("pdf_url")), coarse_status="metadata_only")

        rank = {"open_access": 0, "public_repository": 1, "public_pdf": 2, "public_copy": 3,
                "public_page": 4, "closed_or_unknown": 5, "unavailable": 6, "unknown": 7}
        deduped.sort(key=lambda r: (
            0 if r.get("result_type") == "paper" else 1,
            rank.get(str(r.get("access_kind") or "unknown"), 8),
            0 if r.get("system_can_read") else 1,
            -(int(r.get("cited_by_count") or 0)),
            str(r.get("publication_date") or ""),
        ))
        return {
            "query": query,
            "sources": used_sources,
            "results": deduped[:max_results],
            "errors": errors,
            "general_web_enabled": bool(os.getenv("TAVILY_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY")),
            "access_legend": {
                "open_access": "Open Access confirmado",
                "public_copy": "Copia pública; licencia OA no asumida",
                "public_page": "Página pública; PDF/OA no confirmado",
                "closed_or_unknown": "Open Access no confirmado",
            },
        }

    def _openalex(self, query: str, from_year: int, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "search": query,
            "filter": f"from_publication_date:{from_year}-01-01",
            "per-page": min(limit, 200),
        }
        if self.email:
            params["mailto"] = self.email
        response = httpx.get("https://api.openalex.org/works", params=params, timeout=30)
        response.raise_for_status()
        rows: list[dict[str, Any]] = []
        for work in response.json().get("results", []):
            doi = _clean_doi(work.get("doi"))
            oid = str(work.get("id") or "").rsplit("/", 1)[-1] or None
            primary = work.get("primary_location") or {}
            best = work.get("best_oa_location") or {}
            oa = work.get("open_access") or {}
            rows.append({
                "title": work.get("title") or "Untitled",
                "result_type": "paper", "source": "openalex",
                "url": primary.get("landing_page_url") or work.get("doi"),
                "doi": doi, "arxiv_id": None,
                "authors": [(a.get("author") or {}).get("display_name", "") for a in work.get("authorships") or [] if (a.get("author") or {}).get("display_name")],
                "publication_date": work.get("publication_date"),
                "journal": (primary.get("source") or {}).get("display_name"),
                "abstract": _invert_abstract(work.get("abstract_inverted_index")),
                "cited_by_count": int(work.get("cited_by_count") or 0),
                "canonical_id": f"doi:{doi.lower()}" if doi else (f"openalex:{oid}" if oid else None),
                "_openalex_access": {
                    "is_oa": bool(oa.get("is_oa")), "oa_status": oa.get("oa_status"),
                    "pdf_url": best.get("pdf_url"), "landing_page_url": best.get("landing_page_url"),
                    "license": best.get("license"),
                },
            })
        return rows

    def _arxiv(self, query: str, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for paper in ArxivClient(self.taxonomy).search(query, max_results=limit):
            pdf = arxiv_pdf_url(paper.arxiv_id) if paper.arxiv_id else None
            row = {
                "title": paper.title, "result_type": "paper", "source": "arxiv",
                "url": str(paper.url) if paper.url else None, "doi": _clean_doi(paper.doi),
                "arxiv_id": paper.arxiv_id, "authors": paper.authors,
                "publication_date": paper.publication_date.isoformat() if paper.publication_date else None,
                "journal": paper.journal, "abstract": paper.abstract, "pdf_url": pdf,
                "cited_by_count": paper.cited_by_count, "canonical_id": paper.canonical_id,
            }
            _set_access(row, kind="open_access", label="Open Access · arXiv",
                        reason="Preprint público en arXiv con PDF directo.", pdf_url=pdf,
                        public_url=str(paper.url) if paper.url else pdf, system_can_read=bool(pdf),
                        coarse_status="open_access", oa_status="repository")
            rows.append(row)
        return rows

    def _crossref(self, query: str, from_year: int, limit: int) -> list[dict[str, Any]]:
        params = {
            "query.bibliographic": query, "rows": min(limit, 100),
            "filter": f"from-pub-date:{from_year}-01-01",
            "select": "DOI,title,author,published-print,published-online,container-title,URL,abstract,is-referenced-by-count,type",
        }
        headers = {"User-Agent": f"ScientificBrain/0.9 ({self.email or 'research-agent'})"}
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
                "title": titles[0], "result_type": "paper", "source": "crossref",
                "url": item.get("URL") or (f"https://doi.org/{doi}" if doi else None),
                "doi": doi, "authors": authors, "publication_date": pub_date,
                "journal": (item.get("container-title") or [None])[0], "abstract": item.get("abstract"),
                "cited_by_count": int(item.get("is-referenced-by-count") or 0),
                "canonical_id": f"doi:{doi.lower()}" if doi else None,
            })
        return rows

    def _tavily(self, query: str, limit: int) -> list[dict[str, Any]]:
        key = os.getenv("TAVILY_API_KEY", "").strip()
        if not key:
            return []
        response = httpx.post("https://api.tavily.com/search", json={
            "api_key": key, "query": query, "search_depth": "advanced",
            "max_results": min(limit, 20), "include_answer": False,
        }, timeout=30)
        response.raise_for_status()
        rows = [{"title": x.get("title") or x.get("url") or "Web result", "result_type": "web",
                 "source": "tavily", "url": x.get("url"), "abstract": x.get("content"),
                 "cited_by_count": 0, "canonical_id": None} for x in response.json().get("results", [])]
        for row in rows:
            _classify_web_access(row)
        return rows

    def _brave(self, query: str, limit: int) -> list[dict[str, Any]]:
        key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        if not key:
            return []
        response = httpx.get("https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": min(limit, 20), "safesearch": "moderate"},
            headers={"Accept": "application/json", "X-Subscription-Token": key}, timeout=30)
        response.raise_for_status()
        rows = [{"title": x.get("title") or x.get("url") or "Web result", "result_type": "web",
                 "source": "brave", "url": x.get("url"), "abstract": x.get("description"),
                 "cited_by_count": 0, "canonical_id": None} for x in (response.json().get("web") or {}).get("results", [])]
        for row in rows:
            _classify_web_access(row)
        return rows

    def _resolve_access(self, row: dict[str, Any]) -> None:
        if row.get("access_kind") == "open_access" and row.get("system_can_read"):
            return
        oa = row.pop("_openalex_access", None) or {}
        if oa.get("is_oa"):
            pdf = oa.get("pdf_url")
            _set_access(row, kind="open_access", label=f"Open Access · {oa.get('oa_status') or 'OpenAlex'}",
                        reason="Open Access confirmado por OpenAlex.", pdf_url=pdf,
                        public_url=oa.get("landing_page_url") or row.get("url"), system_can_read=bool(pdf),
                        coarse_status="open_access", oa_status=oa.get("oa_status"), license_name=oa.get("license"))
            return
        if row.get("arxiv_id"):
            pdf = arxiv_pdf_url(str(row["arxiv_id"]))
            _set_access(row, kind="open_access", label="Open Access · arXiv", reason="Preprint público en arXiv.",
                        pdf_url=pdf, public_url=row.get("url"), system_can_read=True,
                        coarse_status="open_access", oa_status="repository")
            return
        doi = _clean_doi(row.get("doi"))
        if doi and self.email:
            try:
                pdf = unpaywall_pdf_url(doi, self.email, timeout=12.0)
                if pdf:
                    _set_access(row, kind="open_access", label="Open Access · Unpaywall",
                                reason="PDF Open Access resuelto por Unpaywall.", pdf_url=pdf, public_url=pdf,
                                system_can_read=True, coarse_status="open_access")
                    return
            except Exception:
                pass
        if row.get("result_type") == "web":
            _classify_web_access(row)
            return
        _set_access(row, kind="closed_or_unknown", label="Open Access no confirmado",
                    reason="No se encontró una ubicación Open Access confirmada en las fuentes consultadas.",
                    public_url=row.get("url"), system_can_read=False,
                    coarse_status="manual_download" if (doi or row.get("url")) else "unavailable")