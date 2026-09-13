from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .adaptive_collaboration import AdaptiveCollaborativeResearchService, DEEP_SECTION_KEYS
from .collaboration import _parse_json_response, _short
from .corpus_intelligence import CorpusIntelligenceService, citation_numbers_in_text


EVIDENCE_REQUIRED_SECTIONS = {
    "abstract",
    "state_of_art",
    "development",
    "analysis",
    "critical_analysis",
    "novelty",
    "conclusion",
}


def targeted_query_from_brief(brief: dict[str, Any], section_key: str | None = None) -> str:
    parts: list[str] = []
    for key in ("topic", "problem_statement", "mechanisms_or_comparisons", "scope_constraints"):
        value = str(brief.get(key) or "").strip()
        if value:
            parts.append(value)
    for question in (brief.get("questions") or [])[:8]:
        text = str(question or "").strip()
        if text:
            parts.append(text)
    if section_key:
        parts.append(f"section focus: {section_key}")
    return " | ".join(parts)[:6500]


def section_citation_gate(
    section_key: str,
    section: dict[str, Any] | str,
    valid_numbers: set[int],
) -> dict[str, Any]:
    if isinstance(section, dict):
        text = str(section.get("text") or "")
        raw_refs = section.get("refs") or []
    else:
        text = str(section or "")
        raw_refs = []
    declared: set[int] = set()
    for ref in raw_refs:
        try:
            declared.add(int(str(ref).strip("[] ")))
        except (TypeError, ValueError):
            continue
    visible = citation_numbers_in_text(text)
    invalid = sorted((declared | visible) - valid_numbers)
    missing_declared = sorted(visible - declared)
    evidence_required = section_key in EVIDENCE_REQUIRED_SECTIONS and bool(text.strip())
    has_citation = bool((declared | visible) & valid_numbers)
    passed = not invalid and not missing_declared and (has_citation or not evidence_required)
    return {
        "passed": passed,
        "evidence_required": evidence_required,
        "declared_refs": sorted(declared),
        "visible_refs": sorted(visible),
        "invalid_refs": invalid,
        "visible_refs_missing_from_section_refs": missing_declared,
        "has_valid_citation": has_citation,
    }


class EvidenceBoundCollaborativeResearchService(AdaptiveCollaborativeResearchService):
    """v0.15 collaboration layer grounded by targeted cross-paper retrieval and evidence gates."""

    def _watch_leads_context(self, limit: int = 8) -> tuple[list[dict[str, Any]], str]:
        rows = self.workspace._select(
            "scibrain_literature_watch_runs",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "watch_id,query,new_count,new_results,sources,errors,created_at",
                "order": "created_at.desc",
                "limit": str(max(1, min(int(limit), 20))),
            },
        )
        compact: list[dict[str, Any]] = []
        for row in rows:
            results = []
            for item in (row.get("new_results") or [])[:10]:
                results.append({
                    "title": item.get("title"),
                    "authors": item.get("authors") or [],
                    "publication_date": item.get("publication_date"),
                    "doi": item.get("doi"),
                    "source": item.get("source"),
                    "abstract": _short(item.get("abstract") or "", 1200),
                    "system_can_read": item.get("system_can_read"),
                })
            if results:
                compact.append({
                    "query": row.get("query"),
                    "created_at": row.get("created_at"),
                    "new_count": row.get("new_count"),
                    "results": results,
                })
        return compact, json.dumps(compact, ensure_ascii=False, default=str)

    def _targeted_evidence(
        self,
        brief: dict[str, Any],
        *,
        section_key: str | None = None,
        limit: int = 36,
    ) -> dict[str, Any]:
        query = targeted_query_from_brief(brief, section_key=section_key)
        if not query:
            return {"query": "", "evidence": [], "context": "", "embedding_stats": {}}
        manifest, _ = self._manifest_and_context()
        number_by_paper = {
            str(source.get("canonical_id")): int(source["citation_number"])
            for source in manifest
            if source.get("canonical_id") and source.get("citation_number")
        }
        try:
            result = CorpusIntelligenceService(self.user, self.folder_id).search(
                query,
                limit=max(8, min(int(limit), 50)),
                per_paper=5,
                lazy_embed=True,
            )
        except Exception as exc:
            return {
                "query": query,
                "evidence": [],
                "context": "",
                "embedding_stats": {},
                "warning": f"{type(exc).__name__}: {exc}",
            }
        evidence: list[dict[str, Any]] = []
        blocks: list[str] = []
        for hit in result.get("hits") or []:
            paper_id = str(hit.get("paper_id") or "")
            number = number_by_paper.get(paper_id)
            if number is None:
                continue
            page_start = int(hit.get("page_start") or 0)
            page_end = int(hit.get("page_end") or page_start)
            row = {
                "citation_number": number,
                "paper_id": paper_id,
                "title": hit.get("title"),
                "page_start": page_start,
                "page_end": page_end,
                "section": hit.get("section_label"),
                "rank": hit.get("rank"),
                "semantic_score": hit.get("semantic_score"),
                "lexical_score": hit.get("lexical_score"),
                "text": _short(hit.get("text") or "", 2400),
            }
            evidence.append(row)
            page = f"p.{page_start}" if page_start == page_end else f"pp.{page_start}-{page_end}"
            blocks.append(
                f"SOURCE [{number}] {page} · {row['section'] or 'unknown section'}\n{row['text']}"
            )
        return {
            "query": query,
            "evidence": evidence,
            "context": "\n\n".join(blocks)[:52000],
            "embedding_stats": result.get("embedding_stats") or {},
            "semantic_enabled": result.get("semantic_enabled"),
        }

    def get_workspace(self) -> dict[str, Any]:
        workspace = super().get_workspace()
        document = workspace.get("document") or {}
        watches, _ = self._watch_leads_context(limit=6)
        try:
            embedding = CorpusIntelligenceService(self.user, self.folder_id).embedding_stats()
        except Exception:
            embedding = {}
        evidence_audit = ((document.get("evidence_manifest") or {}).get("evidence_audit") or {})
        workspace["intelligence"] = {
            "semantic_corpus": embedding,
            "watch_runs_with_new_leads": len(watches),
            "requires_novelty_reassessment": document.get("status") == "stale_external_literature",
            "stale_reason": document.get("stale_reason"),
            "evidence_audit": evidence_audit,
        }
        return workspace

    def assess_brief(self, language: str = "es") -> dict[str, Any]:
        document = self._document_row()
        if not document:
            raise KeyError("research_document_not_found")
        brief = document.get("research_brief") or {}
        questions = brief.get("questions") or []
        if not questions:
            raise ValueError("at least one research question is required")
        manifest, corpus_context = self._manifest_and_context()
        searches, search_context = self._search_context()
        watch_runs, watch_context = self._watch_leads_context()
        targeted = self._targeted_evidence(brief, limit=40)
        valid_numbers = {int(source["citation_number"]) for source in manifest}

        system = """You are ScientificBrain Research Gap Analyst v0.15.
Evaluate each research question using two evidence levels:
A) VALIDATED EVIDENCE: full-text indexed chunks and saved full-text analyses from papers already in the research folder.
B) EXTERNAL LEADS: recent search results and Literature Watch discoveries. These may challenge novelty but are not validated evidence until added and reviewed.
Classify every question as resolved, partially_resolved, open, or contested.
Never infer novelty solely from absence in the current corpus. A new external lead can create a novelty risk even before full-text validation.
Use numbered citations [1], [2], ... only for validated corpus papers. Do not cite external leads as validated references.
For every question identify what is known, what remains missing, decisive evidence, plausible novelty, and whether more literature validation is required.
Return JSON only."""
        user_prompt = f"""LANGUAGE: {language}
RESEARCH BRIEF:\n{json.dumps(brief, ensure_ascii=False, default=str)}
\nTARGETED FULL-TEXT EVIDENCE:\n{targeted.get('context') or 'No targeted chunks retrieved.'}
\nSAVED VALIDATED CORPUS ANALYSES:\n{corpus_context[:65000]}
\nRECENT EXTERNAL SEARCH LEADS:\n{search_context[:26000]}
\nLITERATURE WATCH NEW LEADS:\n{watch_context[:22000]}
\nReturn:
{{
  "overall_assessment": "...",
  "questions": [{{
    "question": "...",
    "status": "resolved|partially_resolved|open|contested",
    "what_is_known": "...",
    "what_is_missing": "...",
    "decisive_evidence_needed": "...",
    "novelty_opportunity": "...",
    "novelty_risk_from_external_leads": "...",
    "requires_literature_validation": true,
    "refs": [1,2]
  }}],
  "recommended_focus": ["..."],
  "search_gaps": ["..."],
  "risks_to_novelty": ["..."],
  "external_leads_to_validate": ["..."]
}}"""
        assessment = _parse_json_response(self.provider.complete(system, user_prompt))  # type: ignore[attr-defined]
        for item in assessment.get("questions") or []:
            if not isinstance(item, dict):
                continue
            refs: list[int] = []
            for ref in item.get("refs") or []:
                try:
                    number = int(str(ref).strip("[] "))
                except (TypeError, ValueError):
                    continue
                if number in valid_numbers and number not in refs:
                    refs.append(number)
            item["refs"] = refs

        snapshot = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "queries": [{"query": row.get("query"), "result_count": row.get("result_count")} for row in searches],
            "literature_watch_runs": len(watch_runs),
            "targeted_full_text_chunks": len(targeted.get("evidence") or []),
            "semantic_enabled": targeted.get("semantic_enabled"),
        }
        updated = self.workspace._patch(
            "scibrain_research_documents",
            {"document_id": f"eq.{document['document_id']}"},
            {
                "novelty_assessment": assessment,
                "external_search_snapshot": snapshot,
                "status": "questions_assessed",
                "stale_reason": None,
                "revision": int(document.get("revision") or 1) + 1,
            },
        )
        return {
            "document": updated,
            "assessment": assessment,
            "corpus_sources": len(manifest),
            "targeted_evidence": targeted.get("evidence") or [],
            "external_watch_leads": sum(int(row.get("new_count") or 0) for row in watch_runs),
        }

    def _deterministic_gates(self, document: dict[str, Any]) -> dict[str, Any]:
        manifest = ((document.get("evidence_manifest") or {}).get("sources") or [])
        valid_numbers = {
            int(source.get("citation_number"))
            for source in manifest
            if source.get("citation_number") is not None
        }
        sections = document.get("sections") or {}
        gates = {
            key: section_citation_gate(key, sections.get(key) or {}, valid_numbers)
            for key in DEEP_SECTION_KEYS
        }
        return {
            "passed": all(gate.get("passed") for gate in gates.values()),
            "valid_reference_numbers": sorted(valid_numbers),
            "sections": gates,
        }

    def verify_document(self, language: str = "es", use_model: bool = True) -> dict[str, Any]:
        document = self._document_row()
        if not document:
            raise KeyError("research_document_not_found")
        deterministic = self._deterministic_gates(document)
        brief = document.get("research_brief") or {"topic": document.get("topic") or ""}
        targeted = self._targeted_evidence(brief, limit=44)
        manifest = ((document.get("evidence_manifest") or {}).get("sources") or [])
        bibliography = "\n".join(
            str(source.get("reference") or "")
            for source in sorted(manifest, key=lambda x: int(x.get("citation_number") or 999999))
        )
        verifier: dict[str, Any] = {}
        verifier_error: str | None = None
        if use_model:
            try:
                system = """You are ScientificBrain Evidence Auditor, an adversarial scientific verifier.
Do not rewrite the document. Check whether material scientific claims in each section are actually supported by the supplied full-text evidence and cited source numbers.
Flag quantitative claims without explicit support, causal claims inferred from correlation, claims that exceed a paper's regime/conditions, citation mismatches, and novelty claims that rely only on absence.
Proposed hypotheses/future experiments may be uncited when clearly identified as proposals, but must not be presented as established results.
External literature leads are not validated evidence and are not supplied here as proof.
Return JSON only."""
                compact_sections = {
                    key: {
                        "text": _short((value or {}).get("text") if isinstance(value, dict) else value, 9000),
                        "refs": (value or {}).get("refs") if isinstance(value, dict) else [],
                        "user_edited": bool((value or {}).get("user_edited")) if isinstance(value, dict) else False,
                    }
                    for key, value in (document.get("sections") or {}).items()
                    if key in DEEP_SECTION_KEYS
                }
                prompt = f"""LANGUAGE: {language}
RESEARCH BRIEF:\n{json.dumps(brief, ensure_ascii=False, default=str)}
DOCUMENT SECTIONS:\n{json.dumps(compact_sections, ensure_ascii=False, default=str)}
TARGETED VALIDATED FULL-TEXT EVIDENCE:\n{targeted.get('context') or 'No targeted evidence retrieved.'}
BIBLIOGRAPHY:\n{bibliography}
\nReturn:
{{
  "overall_pass": true,
  "sections": [{{
    "section_key": "analysis",
    "passed": true,
    "unsupported_claims": ["..."],
    "citation_problems": ["..."],
    "overstatements": ["..."],
    "required_changes": ["..."],
    "confidence": 0.0
  }}],
  "global_required_changes": ["..."]
}}"""
                verifier = _parse_json_response(self.provider.complete(system, prompt))  # type: ignore[attr-defined]
            except Exception as exc:
                verifier_error = f"{type(exc).__name__}: {exc}"

        model_by_section: dict[str, dict[str, Any]] = {}
        for check in verifier.get("sections") or []:
            if isinstance(check, dict) and check.get("section_key") in DEEP_SECTION_KEYS:
                model_by_section[str(check["section_key"])] = check
        sections = dict(document.get("sections") or {})
        combined_sections: dict[str, Any] = {}
        for key in DEEP_SECTION_KEYS:
            det = (deterministic.get("sections") or {}).get(key) or {}
            adversarial = model_by_section.get(key) or {}
            model_pass = bool(adversarial.get("passed", True)) if not verifier_error else None
            combined_pass = bool(det.get("passed")) and (model_pass is not False)
            gate = {
                "passed": combined_pass,
                "deterministic": det,
                "adversarial": adversarial,
                "model_checked": bool(adversarial),
            }
            combined_sections[key] = gate
            current = sections.get(key)
            if isinstance(current, dict):
                current = dict(current)
                current["evidence_gate"] = gate
                sections[key] = current

        model_overall = verifier.get("overall_pass")
        overall_pass = bool(deterministic.get("passed")) and (model_overall is not False) and not verifier_error
        if verifier_error:
            status = "evidence_gate_partial"
        else:
            status = "evidence_verified" if overall_pass else "needs_evidence_review"
        manifest_payload = dict(document.get("evidence_manifest") or {})
        audit = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "passed": overall_pass,
            "status": status,
            "deterministic": deterministic,
            "adversarial": verifier,
            "verifier_error": verifier_error,
            "targeted_retrieval": {
                "query": targeted.get("query"),
                "evidence_count": len(targeted.get("evidence") or []),
                "semantic_enabled": targeted.get("semantic_enabled"),
                "embedding_stats": targeted.get("embedding_stats") or {},
            },
            "sections": combined_sections,
        }
        manifest_payload["evidence_audit"] = audit
        updated = self.workspace._patch(
            "scibrain_research_documents",
            {"document_id": f"eq.{document['document_id']}"},
            {
                "sections": sections,
                "evidence_manifest": manifest_payload,
                "status": status,
                "revision": int(document.get("revision") or 1) + 1,
            },
        )
        return {"document": updated, "evidence_audit": audit}

    def generate_draft(self, topic: str, language: str = "es", preserve_user_edits: bool = True) -> dict[str, Any]:
        current = self._document_row() or {}
        brief = current.get("research_brief") or {}
        if current.get("status") == "stale_external_literature" and brief.get("questions"):
            try:
                self.assess_brief(language=language)
            except Exception:
                pass
        result = super().generate_draft(topic, language=language, preserve_user_edits=preserve_user_edits)
        verified = self.verify_document(language=language, use_model=True)
        result["document"] = verified["document"]
        result["evidence_audit"] = verified["evidence_audit"]
        return result

    def rewrite_section(self, section_key: str, language: str = "es") -> dict[str, Any]:
        result = super().rewrite_section(section_key, language=language)
        verified = self.verify_document(language=language, use_model=True)
        result["document"] = verified["document"]
        result["evidence_audit"] = verified["evidence_audit"]
        return result
