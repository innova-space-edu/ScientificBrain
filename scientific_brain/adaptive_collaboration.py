from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .collaboration import AGENT_ROLES, CollaborativeResearchService, _parse_json_response, _short


DEEP_SECTION_KEYS = (
    "abstract",
    "state_of_art",
    "research_question",
    "objectives",
    "hypotheses",
    "development",
    "analysis",
    "critical_analysis",
    "novelty",
    "future_work",
    "conclusion",
)


def _stable_source_id(paper: dict[str, Any]) -> str:
    identity = (
        paper.get("canonical_id")
        or paper.get("doi")
        or paper.get("arxiv_id")
        or paper.get("item_id")
        or paper.get("title")
        or "unknown-source"
    )
    digest = hashlib.sha1(str(identity).encode("utf-8")).hexdigest()[:8].upper()
    return f"P{digest}"


def _year(value: Any) -> str:
    text = str(value or "")
    return text[:4] if len(text) >= 4 else text


def _authors(value: Any) -> str:
    if not value:
        return "Autor(es) no informados"
    if isinstance(value, str):
        return value
    items: list[str] = []
    for item in value:
        if isinstance(item, dict):
            items.append(str(item.get("name") or item.get("display_name") or "").strip())
        else:
            items.append(str(item).strip())
    items = [x for x in items if x]
    return ", ".join(items) if items else "Autor(es) no informados"


def _reference_text(paper: dict[str, Any], number: int) -> str:
    authors = _authors(paper.get("authors"))
    title = str(paper.get("title") or "Sin título").strip()
    journal = str(paper.get("journal") or "").strip()
    year = _year(paper.get("publication_date"))
    doi = str(paper.get("doi") or "").strip()
    arxiv_id = str(paper.get("arxiv_id") or "").strip()
    parts = [f"[{number}] {authors}. \"{title}.\""]
    if journal:
        parts.append(journal + ".")
    if year:
        parts.append(year + ".")
    if doi:
        parts.append(f"doi:{doi}.")
    elif arxiv_id:
        parts.append(f"arXiv:{arxiv_id}.")
    return " ".join(parts)


class AdaptiveCollaborativeResearchService(CollaborativeResearchService):
    """Deep, corpus-aware collaborative research with stable scientific citations."""

    context_char_limit: int = 120000

    def _messages(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.workspace._select(
            "scibrain_discussion_messages",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "message_id,document_id,message_role,agent_id,section_key,content,evidence_refs,created_at",
                "order": "created_at.desc",
                "limit": str(max(1, min(limit, 300))),
            },
        )
        rows.reverse()
        return rows

    def _paper_rows(self) -> list[dict[str, Any]]:
        return self.workspace._select(
            "scibrain_folder_papers",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": (
                    "item_id,canonical_id,title,authors,publication_date,journal,doi,arxiv_id,"
                    "source_type,source_url,pdf_url,access_status,access_kind,access_label,"
                    "system_can_read,access_url,access_license,oa_status,review_depth,"
                    "record,analysis,critique,specialist_reviews,created_at,updated_at"
                ),
                "order": "created_at.asc",
            },
        )

    def _recent_searches(self, limit: int = 12) -> list[dict[str, Any]]:
        return self.workspace._select(
            "scibrain_research_searches",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "search_id,query,sources,result_count,results,created_at",
                "order": "created_at.desc",
                "limit": str(max(1, min(limit, 30))),
            },
        )

    def _citation_registry(self, papers: list[dict[str, Any]]) -> dict[str, int]:
        existing = self._document_row() or {}
        previous = ((existing.get("evidence_manifest") or {}).get("sources") or [])
        registry: dict[str, int] = {}
        used: set[int] = set()
        for source in previous:
            canonical = str(source.get("canonical_id") or "")
            try:
                number = int(source.get("citation_number"))
            except (TypeError, ValueError):
                continue
            if canonical and number > 0 and number not in used:
                registry[canonical] = number
                used.add(number)
        next_number = max(used, default=0) + 1
        for paper in papers:
            canonical = str(paper.get("canonical_id") or _stable_source_id(paper))
            if canonical not in registry:
                while next_number in used:
                    next_number += 1
                registry[canonical] = next_number
                used.add(next_number)
                next_number += 1
        return registry

    def _manifest_and_context(self) -> tuple[list[dict[str, Any]], str]:
        papers = self._paper_rows()
        if not papers:
            return [], ""
        registry = self._citation_registry(papers)
        manifest: list[dict[str, Any]] = []
        blocks: list[str] = []
        remaining = max(20000, int(self.context_char_limit))
        reviewed = sum(p.get("review_depth") == "full_text_reviewed" for p in papers)
        blocks.append(json.dumps({
            "corpus_summary": {
                "total_papers": len(papers),
                "full_text_reviewed": reviewed,
                "metadata_or_abstract_only": len(papers) - reviewed,
                "rule": "Use papers as evidence for the research topic; do not write a report about the corpus itself.",
            }
        }, ensure_ascii=False))

        for index, paper in enumerate(papers):
            canonical = str(paper.get("canonical_id") or _stable_source_id(paper))
            number = registry[canonical]
            source_id = _stable_source_id(paper)
            item = {
                "source_id": source_id,
                "citation_number": number,
                "citation_label": f"[{number}]",
                "reference": _reference_text(paper, number),
                "canonical_id": paper.get("canonical_id"),
                "title": paper.get("title"),
                "authors": paper.get("authors") or [],
                "publication_date": paper.get("publication_date"),
                "journal": paper.get("journal"),
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

            papers_left = len(papers) - index
            fair_budget = min(16000, max(800, remaining // max(1, papers_left)))
            record = paper.get("record") or {}
            analysis = paper.get("analysis") or {}
            critique = paper.get("critique") or {}
            reviews = paper.get("specialist_reviews") or []
            if paper.get("review_depth") == "full_text_reviewed" and analysis:
                payload = {
                    "citation": f"[{number}]",
                    "title": paper.get("title"),
                    "authors": paper.get("authors") or [],
                    "year": _year(paper.get("publication_date")),
                    "journal": paper.get("journal"),
                    "doi": paper.get("doi"),
                    "review_depth": "full_text_reviewed",
                    "summary": analysis.get("summary"),
                    "claims": analysis.get("claims") or [],
                    "evidence": analysis.get("evidence") or [],
                    "assumptions": analysis.get("assumptions") or [],
                    "equations": analysis.get("equations") or [],
                    "physical_model": analysis.get("physical_model") or [],
                    "experimental_parameters": analysis.get("experimental_parameters") or {},
                    "diagnostics": analysis.get("diagnostics") or [],
                    "simulation_setup": analysis.get("simulation_setup") or {},
                    "initial_conditions": analysis.get("initial_conditions") or [],
                    "boundary_conditions": analysis.get("boundary_conditions") or [],
                    "uncertainty": analysis.get("uncertainty") or [],
                    "limitations": analysis.get("limitations") or [],
                    "reproducibility": analysis.get("reproducibility") or [],
                    "critique": critique,
                    "specialist_reviews": reviews,
                }
            else:
                payload = {
                    "citation": f"[{number}]",
                    "title": paper.get("title"),
                    "authors": paper.get("authors") or [],
                    "year": _year(paper.get("publication_date")),
                    "journal": paper.get("journal"),
                    "doi": paper.get("doi"),
                    "review_depth": paper.get("review_depth"),
                    "abstract": record.get("abstract") or "",
                    "warning": "This source has not been full-text reviewed; do not attribute unsupported details to it.",
                }
            block = json.dumps(payload, ensure_ascii=False, default=str)
            if len(block) > fair_budget:
                block = block[:fair_budget] + "…"
            blocks.append(block)
            remaining = max(0, remaining - len(block))

        return manifest, "\n".join(blocks)

    def _search_context(self) -> tuple[list[dict[str, Any]], str]:
        rows = self._recent_searches()
        compact: list[dict[str, Any]] = []
        for row in rows:
            results = []
            for result in (row.get("results") or [])[:12]:
                results.append({
                    "title": result.get("title"),
                    "publication_date": result.get("publication_date"),
                    "doi": result.get("doi"),
                    "source": result.get("source"),
                    "abstract": _short(result.get("abstract") or "", 1200),
                    "system_can_read": result.get("system_can_read"),
                })
            compact.append({
                "query": row.get("query"),
                "result_count": row.get("result_count"),
                "created_at": row.get("created_at"),
                "results": results,
            })
        return compact, json.dumps(compact, ensure_ascii=False, default=str)

    def get_workspace(self) -> dict[str, Any]:
        document = self._document_row()
        papers = self._paper_rows()
        searches = self._recent_searches(limit=8)
        return {
            "folder_id": self.folder_id,
            "document": document,
            "messages": self._messages(limit=300),
            "recent_searches": [
                {"query": x.get("query"), "result_count": x.get("result_count"), "created_at": x.get("created_at")}
                for x in searches
            ],
            "corpus": {
                "total": len(papers),
                "full_text_reviewed": sum(p.get("review_depth") == "full_text_reviewed" for p in papers),
                "readable_now": sum(bool(p.get("system_can_read")) for p in papers),
                "metadata_or_abstract_only": sum(p.get("review_depth") != "full_text_reviewed" for p in papers),
            },
            "agent_roles": [
                {"id": key, "label": value[0], "purpose": value[1]}
                for key, value in AGENT_ROLES.items()
            ],
            "section_keys": list(DEEP_SECTION_KEYS),
        }

    def save_brief(self, brief: dict[str, Any]) -> dict[str, Any]:
        topic = str(brief.get("topic") or "").strip()
        questions = brief.get("questions") or []
        if isinstance(questions, str):
            questions = [line.strip(" -•\t") for line in questions.splitlines() if line.strip()]
        normalized = {
            "topic": topic,
            "problem_statement": str(brief.get("problem_statement") or "").strip(),
            "questions": [str(x).strip() for x in questions if str(x).strip()][:10],
            "mechanisms_or_comparisons": str(brief.get("mechanisms_or_comparisons") or "").strip(),
            "scope_constraints": str(brief.get("scope_constraints") or "").strip(),
            "expected_novelty": str(brief.get("expected_novelty") or "").strip(),
            "desired_output": str(brief.get("desired_output") or "").strip(),
        }
        if not normalized["topic"]:
            raise ValueError("research topic is required")
        document = self._document_row()
        payload = {
            "owner_id": self.user.user_id,
            "folder_id": self.folder_id,
            "topic": normalized["topic"],
            "research_brief": normalized,
            "research_mode": "guided_deep",
            "status": "brief_defined",
            "revision": int((document or {}).get("revision") or 0) + 1,
        }
        if document:
            saved = self.workspace._patch(
                "scibrain_research_documents",
                {"document_id": f"eq.{document['document_id']}"},
                payload,
            )
        else:
            payload.update({"sections": {}, "evidence_manifest": {}, "generated_from_paper_ids": []})
            saved = self.workspace._insert("scibrain_research_documents", payload)
        return {"document": saved}

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
        system = """You are ScientificBrain Research Gap Analyst.
Evaluate each user research question against the supplied full-text-reviewed corpus and recent literature-search metadata.
Classify each question as resolved, partially_resolved, open, or contested.
Do not call something novel merely because it is absent from this small corpus. Distinguish corpus gap from literature gap.
Use numbered corpus citations [1], [2], ... only when the cited source supports the statement.
Search results not yet added to the corpus are leads, not validated evidence.
For every question state: what is known, what remains missing, what evidence would resolve it, and the plausible novelty opportunity.
Return JSON only."""
        user = f"""LANGUAGE: {language}
RESEARCH BRIEF:\n{json.dumps(brief, ensure_ascii=False, default=str)}
\nVALIDATED CORPUS:\n{corpus_context}
\nRECENT EXTERNAL SEARCHES:\n{search_context[:50000]}
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
    "refs": [1,2]
  }}],
  "recommended_focus": ["..."],
  "search_gaps": ["..."],
  "risks_to_novelty": ["..."]
}}"""
        assessment = _parse_json_response(self.provider.complete(system, user))  # type: ignore[attr-defined]
        snapshot = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "queries": [{"query": x.get("query"), "result_count": x.get("result_count")} for x in searches],
        }
        updated = self.workspace._patch(
            "scibrain_research_documents",
            {"document_id": f"eq.{document['document_id']}"},
            {
                "novelty_assessment": assessment,
                "external_search_snapshot": snapshot,
                "status": "questions_assessed",
                "revision": int(document.get("revision") or 1) + 1,
            },
        )
        return {"document": updated, "assessment": assessment, "corpus_sources": len(manifest)}

    def generate_draft(self, topic: str, language: str = "es", preserve_user_edits: bool = True) -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic is required")
        manifest, context = self._manifest_and_context()
        if not manifest:
            raise ValueError("At least one paper is required before generating a research draft")
        existing = self._document_row() or {}
        brief = existing.get("research_brief") or {"topic": topic}
        novelty = existing.get("novelty_assessment") or {}
        _, search_context = self._search_context()

        bibliography = "\n".join(source["reference"] for source in sorted(manifest, key=lambda x: x["citation_number"]))
        system = """You are ScientificBrain's senior scientific synthesis engine.
Write a deep research document ABOUT THE USER'S SCIENTIFIC TOPIC. The papers are evidence, not the subject of the document.

Mandatory rules:
1. Never write generic corpus-report language such as 'we found N papers' in the abstract, development, or conclusion.
2. Every scientific statement derived from a source must use standard numbered citations such as [1] or [2,3].
3. Use only the numbered references supplied. Never invent a reference or renumber it.
4. Full-text-reviewed sources may support detailed claims; metadata/abstract-only sources may support only what is explicitly available.
5. Separate established knowledge, inference, open question, hypothesis, and proposed future work.
6. The objectives must follow from the user's questions and identified gap; they must be specific and scientifically testable.
7. Development must explain mechanisms, models, equations/variables, experimental or computational conditions and causal links when available.
8. Analysis must compare evidence, regimes, methods, uncertainty, disagreements and alternative explanations, not merely summarize papers.
9. Critical analysis must actively try to refute the current interpretation and identify methodological weaknesses.
10. Novelty must distinguish what is already known, partially solved, unresolved and genuinely plausible as a new contribution.
11. Future work must specify decisive experiments/simulations/measurements and what outcome would support or reject alternatives.
12. The abstract is a scientific synopsis of the problem, current knowledge, gap, proposed focus and significance; it is not a review-status disclaimer.
13. Do not fabricate original experimental results. If no new experiment has been performed, describe proposed work as proposed.
14. Write with research-level depth and precision in the requested language.
15. Return JSON only."""
        user = f"""LANGUAGE: {language}
USER RESEARCH TOPIC:\n{topic}
\nUSER RESEARCH BRIEF:\n{json.dumps(brief, ensure_ascii=False, default=str)}
\nQUESTION / NOVELTY ASSESSMENT:\n{json.dumps(novelty, ensure_ascii=False, default=str)}
\nVALIDATED CORPUS WITH SAVED ANALYSES:\n{context}
\nRECENT EXTERNAL SEARCH LEADS (not validated until added to corpus):\n{search_context[:40000]}
\nBIBLIOGRAPHY NUMBERING TO USE EXACTLY:\n{bibliography}
\nReturn:
{{
  "sections": {{
    "abstract": {{"text": "180-300 word scientific abstract", "refs": [1]}},
    "state_of_art": {{"text": "deep state of art and what is established", "refs": [1,2]}},
    "research_question": {{"text": "central question plus subquestions linked to the user's interests", "refs": [1]}},
    "objectives": {{"text": "general and specific objectives, each justified by a gap", "refs": [1]}},
    "hypotheses": {{"text": "competing falsifiable hypotheses or propositions and predictions", "refs": [1]}},
    "development": {{"text": "mechanistic/theoretical/methodological development with variables, regimes and causal chain", "refs": [1,2]}},
    "analysis": {{"text": "cross-paper evidence analysis, quantitative comparisons where supported, uncertainty and disagreements", "refs": [1,2]}},
    "critical_analysis": {{"text": "adversarial critique, alternative explanations, methodological weaknesses and decisive checks", "refs": [1]}},
    "novelty": {{"text": "what is known vs partially solved vs open, and defensible novelty opportunity", "refs": [1,2]}},
    "future_work": {{"text": "specific experiments/simulations/measurements, observables and rejection criteria", "refs": [1]}},
    "conclusion": {{"text": "evidence-bound synthesis answering the research focus without overstating", "refs": [1]}}
  }},
  "knowledge_gaps": ["..."],
  "contested_points": ["..."],
  "limitations": ["..."],
  "decisive_next_steps": ["..."]
}}"""
        parsed = _parse_json_response(self.provider.complete(system, user))  # type: ignore[attr-defined]
        raw_sections = parsed.get("sections") or {}
        old_sections = existing.get("sections") or {}
        sections: dict[str, dict[str, Any]] = {}
        valid_numbers = {int(x["citation_number"]) for x in manifest}
        for key in DEEP_SECTION_KEYS:
            old = old_sections.get(key) or {}
            if preserve_user_edits and isinstance(old, dict) and old.get("user_edited"):
                sections[key] = old
                continue
            value = raw_sections.get(key) or {}
            if isinstance(value, str):
                value = {"text": value, "refs": []}
            refs: list[int] = []
            for ref in value.get("refs") or []:
                try:
                    number = int(str(ref).strip("[] "))
                except (TypeError, ValueError):
                    continue
                if number in valid_numbers and number not in refs:
                    refs.append(number)
            sections[key] = {
                "text": str(value.get("text") or "").strip(),
                "refs": refs,
                "user_edited": False,
                "discussion_rewritten": False,
            }

        evidence_manifest = {
            "sources": manifest,
            "knowledge_gaps": parsed.get("knowledge_gaps") or [],
            "contested_points": parsed.get("contested_points") or [],
            "limitations": parsed.get("limitations") or [],
            "decisive_next_steps": parsed.get("decisive_next_steps") or [],
        }
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "owner_id": self.user.user_id,
            "folder_id": self.folder_id,
            "topic": topic,
            "sections": sections,
            "evidence_manifest": evidence_manifest,
            "generated_from_paper_ids": [str(x.get("canonical_id")) for x in manifest if x.get("canonical_id")],
            "revision": int(existing.get("revision") or 0) + 1,
            "status": "deep_draft",
            "last_generated_at": now,
            "research_mode": "guided_deep",
        }
        if existing:
            document = self.workspace._patch(
                "scibrain_research_documents",
                {"document_id": f"eq.{existing['document_id']}"},
                payload,
            )
        else:
            payload["research_brief"] = {"topic": topic}
            document = self.workspace._insert("scibrain_research_documents", payload)
        return {"document": document, "corpus_sources": len(manifest)}

    def save_section(self, section_key: str, content: str) -> dict[str, Any]:
        if section_key not in DEEP_SECTION_KEYS:
            raise ValueError(f"Unknown section: {section_key}")
        document = self._document_row()
        if not document:
            raise KeyError("research_document_not_found")
        sections = dict(document.get("sections") or {})
        current = sections.get(section_key) or {}
        sections[section_key] = {
            "text": content,
            "refs": list(current.get("refs") or []) if isinstance(current, dict) else [],
            "user_edited": True,
            "discussion_rewritten": bool(current.get("discussion_rewritten")) if isinstance(current, dict) else False,
        }
        updated = self.workspace._patch(
            "scibrain_research_documents",
            {"document_id": f"eq.{document['document_id']}"},
            {"sections": sections, "revision": int(document.get("revision") or 1) + 1, "status": "revised"},
        )
        return {"document": updated}

    def discuss(
        self,
        message: str,
        agent_id: str = "critical_reviewer",
        *,
        section_key: str | None = None,
        language: str = "es",
    ) -> dict[str, Any]:
        message = message.strip()
        if not message:
            raise ValueError("message is required")
        if agent_id not in AGENT_ROLES:
            raise ValueError("unknown agent_id")
        if section_key and section_key not in DEEP_SECTION_KEYS:
            raise ValueError("unknown section")
        document = self._document_row()
        if not document:
            raise KeyError("research_document_not_found")
        manifest, context = self._manifest_and_context()
        _, search_context = self._search_context()
        self._insert_message(role="user", content=message, section_key=section_key)
        label, purpose = AGENT_ROLES[agent_id]
        sections = document.get("sections") or {}
        focus = sections.get(section_key) if section_key else sections
        previous = [m for m in self._messages(limit=120) if not section_key or m.get("section_key") == section_key]
        conversation = "\n".join(
            f"{m.get('message_role')}:{m.get('agent_id') or 'user'}: {_short(m.get('content'), 2000)}"
            for m in previous[-30:]
        )
        bibliography = "\n".join(source["reference"] for source in sorted(manifest, key=lambda x: x["citation_number"]))
        system = f"""You are {label}, a specialist in a scientific co-authoring session.
Role: {purpose}
Debate the selected section rigorously. Use the user's research brief, the saved full-text analyses, and recent search leads.
Use numbered citations [1], [2], ... only for validated corpus sources. Search leads are not evidence until added/analyzed.
Challenge weak assumptions, quantify where the evidence supports it, propose alternative explanations and identify decisive tests.
Do not merely summarize. Do not invent facts. Reply in language code {language}. Return JSON only."""
        user = f"""RESEARCH BRIEF:\n{json.dumps(document.get('research_brief') or {}, ensure_ascii=False)}
NOVELTY ASSESSMENT:\n{json.dumps(document.get('novelty_assessment') or {}, ensure_ascii=False)}
SECTION: {section_key or 'general'}\n{json.dumps(focus, ensure_ascii=False, default=str)}
VALIDATED CORPUS:\n{context}
RECENT SEARCH LEADS:\n{search_context[:25000]}
BIBLIOGRAPHY:\n{bibliography}
RECENT SECTION DISCUSSION:\n{conversation}
USER MESSAGE:\n{message}
\nReturn {{"response":"...","objections":["..."],"recommended_changes":["..."],"evidence_refs":[1],"confidence":0.0}}"""
        answer = _parse_json_response(self.provider.complete(system, user))  # type: ignore[attr-defined]
        response_text = str(answer.get("response") or "").strip()
        objections = [str(x) for x in answer.get("objections") or []]
        changes = [str(x) for x in answer.get("recommended_changes") or []]
        if objections:
            response_text += "\n\nObjeciones / refutaciones posibles:\n- " + "\n- ".join(objections)
        if changes:
            response_text += "\n\nCambios sugeridos:\n- " + "\n- ".join(changes)
        refs: list[str] = []
        for ref in answer.get("evidence_refs") or []:
            try:
                refs.append(str(int(str(ref).strip("[] "))))
            except (TypeError, ValueError):
                continue
        agent_message = self._insert_message(
            role="agent",
            content=response_text,
            agent_id=agent_id,
            section_key=section_key,
            refs=refs,
        )
        return {"message": agent_message, "confidence": answer.get("confidence"), "evidence_manifest": manifest}

    def rewrite_section(self, section_key: str, language: str = "es") -> dict[str, Any]:
        if section_key not in DEEP_SECTION_KEYS:
            raise ValueError("unknown section")
        document = self._document_row()
        if not document:
            raise KeyError("research_document_not_found")
        messages = [m for m in self._messages(limit=300) if m.get("section_key") == section_key]
        if not messages:
            raise ValueError("No discussion exists for this section")
        manifest, context = self._manifest_and_context()
        _, search_context = self._search_context()
        current = (document.get("sections") or {}).get(section_key) or {}
        conversation = "\n".join(
            f"{m.get('message_role')}:{m.get('agent_id') or 'user'}: {m.get('content')}" for m in messages
        )
        bibliography = "\n".join(source["reference"] for source in sorted(manifest, key=lambda x: x["citation_number"]))
        system = """You are ScientificBrain Section Rewriter.
Rewrite one scientific section after a completed user-agent debate.
Integrate the current text, every material point from the section discussion, the research brief, validated corpus evidence, novelty assessment and relevant search leads.
Resolve addressed objections where possible; preserve unresolved uncertainty explicitly.
Write substantially, not cosmetically. Use numbered citations [1], [2], ... exactly as supplied. Do not invent references or results.
Return JSON only: {"text":"...","refs":[1,2],"resolved_points":["..."],"remaining_open_points":["..."]}."""
        user = f"""LANGUAGE: {language}
SECTION: {section_key}
CURRENT TEXT:\n{json.dumps(current, ensure_ascii=False, default=str)}
RESEARCH BRIEF:\n{json.dumps(document.get('research_brief') or {}, ensure_ascii=False, default=str)}
NOVELTY ASSESSMENT:\n{json.dumps(document.get('novelty_assessment') or {}, ensure_ascii=False, default=str)}
SECTION DISCUSSION:\n{conversation[:40000]}
VALIDATED CORPUS:\n{context}
SEARCH LEADS:\n{search_context[:20000]}
BIBLIOGRAPHY:\n{bibliography}"""
        answer = _parse_json_response(self.provider.complete(system, user))  # type: ignore[attr-defined]
        refs: list[int] = []
        valid_numbers = {int(x["citation_number"]) for x in manifest}
        for ref in answer.get("refs") or []:
            try:
                number = int(str(ref).strip("[] "))
            except (TypeError, ValueError):
                continue
            if number in valid_numbers and number not in refs:
                refs.append(number)
        sections = dict(document.get("sections") or {})
        sections[section_key] = {
            "text": str(answer.get("text") or "").strip(),
            "refs": refs,
            "user_edited": False,
            "discussion_rewritten": True,
            "resolved_points": answer.get("resolved_points") or [],
            "remaining_open_points": answer.get("remaining_open_points") or [],
        }
        updated = self.workspace._patch(
            "scibrain_research_documents",
            {"document_id": f"eq.{document['document_id']}"},
            {"sections": sections, "revision": int(document.get("revision") or 1) + 1, "status": "revised_from_discussion"},
        )
        return {"document": updated, "section": sections[section_key]}

    def review_section(self, section_key: str, agent_id: str = "critical_reviewer", language: str = "es") -> dict[str, Any]:
        return self.discuss(
            "Realiza una revisión profunda de esta sección. Identifica afirmaciones débiles, evidencia insuficiente, contradicciones, supuestos ocultos, alternativas plausibles y pruebas decisivas antes de aceptarla.",
            agent_id=agent_id,
            section_key=section_key,
            language=language,
        )
