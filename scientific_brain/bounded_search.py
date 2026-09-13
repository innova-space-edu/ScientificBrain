from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any

from .fulltext import arxiv_pdf_url, unpaywall_pdf_url
from .research_search import (
    ResearchSearchService,
    _classify_web_access,
    _clean_doi,
    _key,
    _set_access,
)


class BoundedResearchSearchService(ResearchSearchService):
    """Time-bounded discovery for serverless execution."""

    source_deadline_seconds = 38.0
    max_unpaywall_lookups = 6
    unpaywall_timeout_seconds = 5.0

    def __init__(self, taxonomy_path: str = "config/plasma_taxonomy.yaml") -> None:
        super().__init__(taxonomy_path)
        self._unpaywall_remaining = self.max_unpaywall_lookups

    def search(self, query: str, *, from_year: int = 1900, max_results: int = 30,
               include_web: bool = True, resolve_open_access: bool = True) -> dict[str, Any]:
        query = query.strip()
        if not query:
            raise ValueError("Research search query is required")

        max_results = max(1, min(int(max_results), 40))
        per_source = max(5, min(25, max_results))
        specs: list[tuple[str, Any]] = [
            ("openalex", lambda: self._openalex(query, from_year, per_source)),
            ("arxiv", lambda: self._arxiv(query, per_source)),
            ("crossref", lambda: self._crossref(query, from_year, per_source)),
        ]
        if include_web:
            specs.extend([
                ("tavily", lambda: self._tavily(query, per_source)),
                ("brave", lambda: self._brave(query, per_source)),
            ])

        collected: list[dict[str, Any]] = []
        used_sources: list[str] = []
        errors: list[dict[str, str]] = []
        executor = ThreadPoolExecutor(max_workers=len(specs), thread_name_prefix="scibrain-search")
        futures = {executor.submit(fn): name for name, fn in specs}
        done, pending = wait(futures, timeout=self.source_deadline_seconds)

        for future in done:
            name = futures[future]
            try:
                rows = future.result()
                if rows:
                    collected.extend(rows)
                    used_sources.append(name)
            except Exception as exc:
                errors.append({"source": name, "error": f"{type(exc).__name__}: {exc}"})

        for future in pending:
            errors.append({
                "source": futures[future],
                "error": f"TimeoutError: source exceeded {int(self.source_deadline_seconds)}s discovery budget",
            })
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in collected:
            key = _key(row)
            if not row.get("title") or key in seen:
                continue
            seen.add(key)
            deduped.append(row)

        deduped.sort(key=lambda r: (
            0 if r.get("result_type") == "paper" else 1,
            -(int(r.get("cited_by_count") or 0)),
            str(r.get("publication_date") or ""),
        ))
        candidates = deduped[:max_results]

        self._unpaywall_remaining = self.max_unpaywall_lookups
        for row in candidates:
            if resolve_open_access:
                self._resolve_access(row)
            elif not row.get("access_kind") or row.get("access_kind") == "unknown":
                if row.get("result_type") == "web":
                    _classify_web_access(row)
                else:
                    _set_access(row, kind="closed_or_unknown", label="Open Access no confirmado",
                                reason="No se ejecutó resolución de Open Access.", public_url=row.get("url"),
                                system_can_read=bool(row.get("pdf_url")), coarse_status="metadata_only")

        access_rank = {"open_access": 0, "public_repository": 1, "public_pdf": 2,
                       "public_copy": 3, "public_page": 4, "closed_or_unknown": 5,
                       "unavailable": 6, "unknown": 7}
        candidates.sort(key=lambda r: (
            0 if r.get("result_type") == "paper" else 1,
            access_rank.get(str(r.get("access_kind") or "unknown"), 8),
            0 if r.get("system_can_read") else 1,
            -(int(r.get("cited_by_count") or 0)),
            str(r.get("publication_date") or ""),
        ))
        return {
            "query": query,
            "sources": sorted(set(used_sources)),
            "results": candidates,
            "errors": errors,
            "partial": bool(errors),
            "general_web_enabled": bool(os.getenv("TAVILY_API_KEY") or os.getenv("BRAVE_SEARCH_API_KEY")),
            "access_legend": {
                "open_access": "Open Access confirmado",
                "public_copy": "Copia pública; licencia OA no asumida",
                "public_page": "Página pública; PDF/OA no confirmado",
                "closed_or_unknown": "Open Access no confirmado",
            },
        }

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
        if row.get("result_type") == "web":
            _classify_web_access(row)
            return

        doi = _clean_doi(row.get("doi"))
        if doi and self.email and self._unpaywall_remaining > 0:
            self._unpaywall_remaining -= 1
            try:
                pdf = unpaywall_pdf_url(doi, self.email, timeout=self.unpaywall_timeout_seconds)
                if pdf:
                    _set_access(row, kind="open_access", label="Open Access · Unpaywall",
                                reason="PDF Open Access resuelto por Unpaywall.", pdf_url=pdf,
                                public_url=pdf, system_can_read=True, coarse_status="open_access")
                    return
            except Exception:
                pass

        _set_access(row, kind="closed_or_unknown", label="Open Access no confirmado",
                    reason="Open Access no confirmado dentro del presupuesto de búsqueda; se conserva DOI/enlace para verificación.",
                    public_url=row.get("url"), system_can_read=False,
                    coarse_status="manual_download" if (doi or row.get("url")) else "unavailable")
