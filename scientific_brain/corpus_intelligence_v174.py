from __future__ import annotations

import re
from typing import Any

from .cloud_papers import CloudPaperService
from .corpus_intelligence_v16 import TelemetryCorpusIntelligenceService
from .paper_intelligence import PaperIntelligenceStore
from .user_snapshot import UserSnapshotStore
from .web_runtime import temporary_memory

_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9_\-]{3,}")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "are", "was", "were",
    "una", "unos", "unas", "para", "con", "del", "los", "las", "que", "por", "como", "sobre",
    "what", "which", "where", "when", "cual", "cuáles", "donde", "cuando", "cómo", "qué",
}
_ALIASES = {
    "impulso": {"impulse", "impulses", "momentum"},
    "impulsos": {"impulse", "impulses", "momentum"},
    "propulsor": {"thruster", "propulsion"},
    "propulsores": {"thruster", "thrusters", "propulsion"},
    "propulsión": {"propulsion", "thruster"},
    "propulsion": {"propulsion", "thruster"},
    "mecanismo": {"mechanism"},
    "mecanismos": {"mechanism", "mechanisms"},
    "empuje": {"thrust"},
    "corriente": {"current"},
    "descarga": {"discharge"},
    "geometría": {"geometry"},
    "geometria": {"geometry"},
}


def _query_terms(query: str) -> set[str]:
    terms = {
        token.lower()
        for token in _TOKEN_RE.findall(str(query or ""))
        if token.lower() not in _STOPWORDS
    }
    expanded = set(terms)
    for term in list(terms):
        expanded.update(_ALIASES.get(term, set()))
        if term.startswith("impuls"):
            expanded.update({"impulse", "momentum"})
        if term.startswith("propuls"):
            expanded.update({"propulsion", "thruster"})
        if term.startswith("mecan"):
            expanded.add("mechanism")
    return expanded


class ResilientTelemetryCorpusIntelligenceService(TelemetryCorpusIntelligenceService):
    """Corpus chat with self-healing legacy full-text indexing and evidence fallback."""

    def _has_chunks(self, paper_id: str) -> bool:
        rows = self.workspace._select(
            "scibrain_paper_chunks",
            {
                "folder_id": f"eq.{self.folder_id}",
                "paper_id": f"eq.{paper_id}",
                "select": "chunk_id",
                "limit": "1",
            },
        )
        return bool(rows)

    def _repair_missing_indexes(self, max_papers: int = 2) -> dict[str, Any]:
        checked = 0
        repaired = 0
        errors: list[dict[str, str]] = []
        snapshot = UserSnapshotStore(self.user, folder_id=self.folder_id)

        for paper in self._papers():
            if checked >= max(1, min(int(max_papers), 4)):
                break
            if paper.get("review_depth") != "full_text_reviewed":
                continue
            if not (
                paper.get("system_can_read")
                or paper.get("storage_path")
                or paper.get("pdf_url")
            ):
                continue
            paper_id = str(paper.get("canonical_id") or "").strip()
            if not paper_id:
                continue
            try:
                if self._has_chunks(paper_id):
                    continue
                checked += 1
                with temporary_memory() as memory:
                    _, document = CloudPaperService(memory, object(), snapshot).load_document(
                        paper_id,
                        pdf_url=paper.get("pdf_url") or None,
                    )
                if not self._has_chunks(paper_id):
                    PaperIntelligenceStore(self.user, self.folder_id).index_document(document)
                if self._has_chunks(paper_id):
                    repaired += 1
                else:
                    errors.append({"paper_id": paper_id, "error": "index remained empty"})
            except Exception as exc:
                errors.append(
                    {
                        "paper_id": paper_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        return {
            "papers_checked": checked,
            "papers_repaired": repaired,
            "errors": errors[:4],
        }

    def _analysis_evidence_hits(self, query: str, limit: int) -> list[dict[str, Any]]:
        rows = self.workspace._select(
            "scibrain_folder_papers",
            {
                "folder_id": f"eq.{self.folder_id}",
                "review_depth": "eq.full_text_reviewed",
                "select": "canonical_id,title,analysis",
                "order": "updated_at.desc",
                "limit": "24",
            },
        )
        terms = _query_terms(query)
        hits: list[dict[str, Any]] = []

        for paper in rows:
            paper_id = str(paper.get("canonical_id") or "").strip()
            analysis = paper.get("analysis") or {}
            evidence = analysis.get("evidence") or []
            claims = analysis.get("claims") or []

            linked_claims: dict[str, list[str]] = {}
            for claim in claims:
                if not isinstance(claim, dict):
                    continue
                claim_text = str(claim.get("text") or claim.get("claim") or "").strip()
                if not claim_text:
                    continue
                for evidence_id in claim.get("evidence_ids") or []:
                    linked_claims.setdefault(str(evidence_id), []).append(claim_text)

            for index, item in enumerate(evidence):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                evidence_id = str(item.get("evidence_id") or "")
                section = str(item.get("section") or "")
                ranking_text = " ".join(
                    [text, section, *linked_claims.get(evidence_id, [])]
                ).lower()
                overlap = sum(ranking_text.count(term) for term in terms)
                strength = str(item.get("strength") or "").lower()
                direct_bonus = 1.0 if strength == "direct" else 0.25
                reference_penalty = 2.0 if section.lower().startswith("reference") else 0.0
                rank = overlap * 10.0 + direct_bonus - reference_penalty + 1.0 / (index + 10)

                page = int(item.get("page") or 0)
                hits.append(
                    {
                        "paper_id": paper_id,
                        "title": paper.get("title") or paper_id,
                        "page_start": page,
                        "page_end": page,
                        "section_label": section or None,
                        "kind": "reviewed_evidence",
                        "text": text,
                        "rank": rank,
                        "semantic_score": 0.0,
                        "lexical_score": float(overlap),
                        "evidence_id": evidence_id or None,
                        "retrieval_source": "full_text_review_analysis",
                    }
                )

        hits.sort(key=lambda row: float(row.get("rank") or 0.0), reverse=True)
        non_reference = [
            row
            for row in hits
            if not str(row.get("section_label") or "").lower().startswith("reference")
        ]
        chosen = non_reference if non_reference else hits
        return chosen[: max(1, min(int(limit), 60))]

    def search(
        self,
        query: str,
        limit: int = 24,
        per_paper: int = 4,
        lazy_embed: bool = True,
    ) -> dict[str, Any]:
        result = super().search(
            query,
            limit=limit,
            per_paper=per_paper,
            lazy_embed=lazy_embed,
        )
        if result.get("hits"):
            return result

        repair = self._repair_missing_indexes()
        if repair.get("papers_repaired"):
            result = super().search(
                query,
                limit=limit,
                per_paper=per_paper,
                lazy_embed=True,
            )
            result["index_repair"] = repair
            if result.get("hits"):
                result["retrieval_mode"] = "repaired_full_text_index"
                return result

        fallback = self._analysis_evidence_hits(query, limit)
        if fallback:
            result["hits"] = fallback
            result["hit_count"] = len(fallback)
            result["retrieval_mode"] = "full_text_review_analysis"
            result["index_repair"] = repair
        return result
