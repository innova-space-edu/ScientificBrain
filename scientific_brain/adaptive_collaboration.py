from __future__ import annotations

import json
from typing import Any

from .collaboration import CollaborativeResearchService, _short


class AdaptiveCollaborativeResearchService(CollaborativeResearchService):
    """Corpus-aware collaborative synthesis.

    Small folders receive deep per-paper context. Large folders receive a fair,
    bounded representation of every paper instead of silently dropping papers
    after the first 90k characters.
    """

    def _manifest_and_context(self) -> tuple[list[dict[str, Any]], str]:
        papers = self._paper_rows()
        manifest: list[dict[str, Any]] = []
        if not papers:
            return manifest, ""

        remaining = max(10000, int(self.context_char_limit))
        blocks: list[str] = []
        total = len(papers)
        reviewed = sum(p.get("review_depth") == "full_text_reviewed" for p in papers)
        header = json.dumps({
            "corpus_summary": {
                "total_papers": total,
                "full_text_reviewed": reviewed,
                "metadata_or_abstract_only": total - reviewed,
                "context_policy": (
                    "deep_per_source" if total <= 5 else
                    "balanced_all_sources" if total <= 25 else
                    "compressed_all_sources"
                ),
            }
        }, ensure_ascii=False)
        blocks.append(header)
        remaining -= len(header)

        for i, paper in enumerate(papers, 1):
            source_id = f"P{i}"
            record = paper.get("record") or {}
            analysis = paper.get("analysis") or {}
            critique = paper.get("critique") or {}
            item = {
                "source_id": source_id,
                "canonical_id": paper.get("canonical_id"),
                "title": paper.get("title"),
                "doi": paper.get("doi"),
                "arxiv_id": paper.get("arxiv_id"),
                "source_type": paper.get("source_type"),
                "source_url": paper.get("source_url"),
                "access_kind": paper.get("access_kind") or "unknown",
                "access_label": paper.get("access_label") or paper.get("access_status"),
                "review_depth": paper.get("review_depth"),
                "system_can_read": bool(paper.get("system_can_read")),
            }
            manifest.append(item)

            papers_left = total - i + 1
            fair_budget = max(160, remaining // max(1, papers_left))
            fair_budget = min(9000, fair_budget)
            is_full = paper.get("review_depth") == "full_text_reviewed" and bool(analysis)

            if is_full:
                claims = analysis.get("claims") or []
                evidence = analysis.get("evidence") or []
                if fair_budget < 1400:
                    claims = claims[:1]
                    evidence = []
                elif fair_budget < 2800:
                    claims = claims[:2]
                    evidence = evidence[:2]
                elif fair_budget < 5000:
                    claims = claims[:4]
                    evidence = evidence[:4]
                payload = {
                    "id": source_id,
                    "title": paper.get("title"),
                    "year": str(paper.get("publication_date") or "")[:4],
                    "doi": paper.get("doi"),
                    "review_depth": paper.get("review_depth"),
                    "summary": _short(analysis.get("summary"), max(260, fair_budget // 3)),
                    "claims": claims,
                    "evidence": evidence,
                    "limitations": analysis.get("limitations") or [],
                    "uncertainty": analysis.get("uncertainty") or [],
                    "physical_model": analysis.get("physical_model") or [],
                    "critique": critique if fair_budget >= 3500 else None,
                }
            else:
                payload = {
                    "id": source_id,
                    "title": paper.get("title"),
                    "authors": paper.get("authors") or [],
                    "year": str(paper.get("publication_date") or "")[:4],
                    "journal": paper.get("journal"),
                    "doi": paper.get("doi"),
                    "review_depth": paper.get("review_depth"),
                    "abstract": _short(record.get("abstract") or "", max(120, fair_budget - 300)),
                }

            block = json.dumps(payload, ensure_ascii=False, default=str)
            if len(block) > fair_budget:
                block = block[:fair_budget] + "…"
            blocks.append(block)
            remaining = max(0, remaining - len(block))

        return manifest, "\n".join(blocks)
