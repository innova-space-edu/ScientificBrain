from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .auth import AuthenticatedUser
from .workspaces import UserWorkspaceStore

SECTION_KEYS = (
    "abstract",
    "state_of_art",
    "research_question",
    "objectives",
    "development",
    "analysis",
    "conclusion",
)

AGENT_ROLES = {
    "critical_reviewer": (
        "Revisor crítico",
        "Busca sobreafirmaciones, contradicciones, alternativas plausibles, sesgos y puntos refutables.",
    ),
    "literature_reviewer": (
        "Revisor de literatura",
        "Evalúa cobertura del estado del arte, vacíos, actualidad y si las citas realmente apoyan el texto.",
    ),
    "methods_reviewer": (
        "Revisor metodológico",
        "Evalúa variables, observables, controles, incertidumbre, falsabilidad y diseño experimental/simulación.",
    ),
    "theory_reviewer": (
        "Revisor teórico",
        "Evalúa mecanismos físicos, supuestos, ecuaciones, régimen de validez y explicaciones alternativas.",
    ),
    "evidence_reviewer": (
        "Revisor de evidencia",
        "Comprueba trazabilidad Paper → claim → evidencia y penaliza cualquier afirmación sin respaldo.",
    ),
    "scientific_editor": (
        "Editor científico",
        "Mejora claridad, estructura y precisión sin inventar resultados ni borrar incertidumbres.",
    ),
}


def _parse_json_response(text: str) -> dict[str, Any]:
    raw = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.S | re.I)
    if fenced:
        raw = fenced.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object")
    return payload


def _short(value: Any, limit: int = 6000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


@dataclass
class CollaborativeResearchService:
    user: AuthenticatedUser
    folder_id: str
    provider: object
    context_char_limit: int = 90000

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)
        if not self.workspace.get_folder(self.folder_id):
            raise KeyError("folder_not_found")

    def _document_row(self) -> dict[str, Any] | None:
        rows = self.workspace._select(
            "scibrain_research_documents",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def _messages(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.workspace._select(
            "scibrain_discussion_messages",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": "message_id,document_id,message_role,agent_id,section_key,content,evidence_refs,created_at",
                "order": "created_at.asc",
                "limit": str(max(1, min(limit, 300))),
            },
        )

    def _paper_rows(self) -> list[dict[str, Any]]:
        return self.workspace._select(
            "scibrain_folder_papers",
            {
                "folder_id": f"eq.{self.folder_id}",
                "select": (
                    "item_id,canonical_id,title,authors,publication_date,journal,doi,arxiv_id,"
                    "source_type,source_url,pdf_url,access_status,access_kind,access_label,"
                    "system_can_read,access_url,access_license,oa_status,review_depth,"
                    "record,analysis,critique,specialist_reviews"
                ),
                "order": "created_at.asc",
            },
        )

    def _manifest_and_context(self) -> tuple[list[dict[str, Any]], str]:
        papers = self._paper_rows()
        manifest: list[dict[str, Any]] = []
        blocks: list[str] = []
        remaining = self.context_char_limit

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

            payload = {
                "id": source_id,
                "title": paper.get("title"),
                "authors": paper.get("authors") or [],
                "year": str(paper.get("publication_date") or "")[:4],
                "journal": paper.get("journal"),
                "doi": paper.get("doi"),
                "access": item["access_label"],
                "review_depth": paper.get("review_depth"),
                "abstract": record.get("abstract") or "",
                "full_text_analysis": {
                    "summary": analysis.get("summary"),
                    "claims": analysis.get("claims") or [],
                    "evidence": analysis.get("evidence") or [],
                    "assumptions": analysis.get("assumptions") or [],
                    "limitations": analysis.get("limitations") or [],
                    "uncertainty": analysis.get("uncertainty") or [],
                    "diagnostics": analysis.get("diagnostics") or [],
                    "experimental_parameters": analysis.get("experimental_parameters") or {},
                    "physical_model": analysis.get("physical_model") or [],
                }
                if analysis
                else None,
                "critique": critique if critique else None,
            }
            block = json.dumps(payload, ensure_ascii=False, default=str)
            if len(block) > 9000:
                block = block[:9000] + "…"
            if len(block) > remaining:
                break
            blocks.append(block)
            remaining -= len(block)

        return manifest, "\n".join(blocks)

    def get_workspace(self) -> dict[str, Any]:
        document = self._document_row()
        papers = self._paper_rows()
        return {
            "folder_id": self.folder_id,
            "document": document,
            "messages": self._messages(),
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
        }

    def generate_draft(self, topic: str, language: str = "es") -> dict[str, Any]:
        topic = topic.strip()
        if not topic:
            raise ValueError("topic is required")

        manifest, context = self._manifest_and_context()
        if not manifest:
            raise ValueError("At least one paper is required before generating a research draft")

        system = """You are ScientificBrain's collaborative scientific synthesis engine.
Create an editable research draft grounded ONLY in the supplied corpus.

Non-negotiable rules:
1. Do not invent citations, measurements, equations, results, experimental conditions or conclusions.
2. Distinguish full-text-reviewed evidence from abstract/metadata-only evidence.
3. When sources disagree, expose the disagreement and possible regime/method differences.
4. Every substantive source-derived statement must include one or more source tags such as [P1].
5. A source tag means only that the supplied record supports the statement at the available review depth.
6. The research question and objectives may be proposed by you, but label them as proposed and make them falsifiable where possible.
7. If the corpus is too small, say so explicitly inside the relevant section; do not block progress.
8. The abstract is provisional. Do not describe original experimental results that are not in the corpus.
9. Write in the requested language.
10. Return JSON only, with exactly the requested structure."""

        user = f"""Requested language: {language}
Research topic supplied by the user:
{topic}

Corpus records:
{context}

Return:
{{
  "sections": {{
    "abstract": {{"text": "...", "refs": ["P1"]}},
    "state_of_art": {{"text": "...", "refs": ["P1","P2"]}},
    "research_question": {{"text": "...", "refs": []}},
    "objectives": {{"text": "...", "refs": []}},
    "development": {{"text": "...", "refs": ["P1"]}},
    "analysis": {{"text": "...", "refs": ["P1","P2"]}},
    "conclusion": {{"text": "...", "refs": ["P1"]}}
  }},
  "knowledge_gaps": ["..."],
  "contested_points": ["..."],
  "limitations": ["..."]
}}"""

        response = self.provider.complete(system, user)  # type: ignore[attr-defined]
        parsed = _parse_json_response(response)
        raw_sections = parsed.get("sections") or {}
        sections: dict[str, dict[str, Any]] = {}
        for key in SECTION_KEYS:
            value = raw_sections.get(key) or {}
            if isinstance(value, str):
                value = {"text": value, "refs": []}
            sections[key] = {
                "text": str(value.get("text") or "").strip(),
                "refs": [str(x) for x in (value.get("refs") or []) if str(x).startswith("P")],
                "user_edited": False,
            }

        evidence_manifest = {
            "sources": manifest,
            "knowledge_gaps": parsed.get("knowledge_gaps") or [],
            "contested_points": parsed.get("contested_points") or [],
            "limitations": parsed.get("limitations") or [],
        }
        existing = self._document_row()
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "owner_id": self.user.user_id,
            "folder_id": self.folder_id,
            "topic": topic,
            "sections": sections,
            "evidence_manifest": evidence_manifest,
            "generated_from_paper_ids": [
                str(x.get("canonical_id")) for x in manifest if x.get("canonical_id")
            ],
            "revision": int((existing or {}).get("revision") or 0) + 1,
            "status": "draft",
            "last_generated_at": now,
        }
        if existing:
            document = self.workspace._patch(
                "scibrain_research_documents",
                {"document_id": f"eq.{existing['document_id']}"},
                payload,
            )
        else:
            document = self.workspace._insert("scibrain_research_documents", payload)
        return {"document": document, "corpus_sources": len(manifest)}

    def save_section(self, section_key: str, content: str) -> dict[str, Any]:
        if section_key not in SECTION_KEYS:
            raise ValueError(f"Unknown section: {section_key}")
        document = self._document_row()
        if not document:
            raise KeyError("research_document_not_found")
        sections = document.get("sections") or {}
        current = sections.get(section_key) or {}
        refs = current.get("refs") or [] if isinstance(current, dict) else []
        sections[section_key] = {
            "text": content,
            "refs": refs,
            "user_edited": True,
        }
        updated = self.workspace._patch(
            "scibrain_research_documents",
            {"document_id": f"eq.{document['document_id']}"},
            {
                "sections": sections,
                "revision": int(document.get("revision") or 1) + 1,
                "status": "revised",
            },
        )
        return {"document": updated}

    def save_topic(self, topic: str) -> dict[str, Any]:
        document = self._document_row()
        if not document:
            raise KeyError("research_document_not_found")
        updated = self.workspace._patch(
            "scibrain_research_documents",
            {"document_id": f"eq.{document['document_id']}"},
            {
                "topic": topic.strip(),
                "revision": int(document.get("revision") or 1) + 1,
            },
        )
        return {"document": updated}

    def _insert_message(
        self,
        *,
        role: str,
        content: str,
        agent_id: str | None = None,
        section_key: str | None = None,
        refs: list[str] | None = None,
    ) -> dict[str, Any]:
        document = self._document_row()
        return self.workspace._insert(
            "scibrain_discussion_messages",
            {
                "owner_id": self.user.user_id,
                "folder_id": self.folder_id,
                "document_id": document.get("document_id") if document else None,
                "message_role": role,
                "agent_id": agent_id,
                "section_key": section_key,
                "content": content,
                "evidence_refs": refs or [],
            },
        )

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

        document = self._document_row()
        if not document:
            raise KeyError("research_document_not_found")
        manifest, context = self._manifest_and_context()
        self._insert_message(role="user", content=message, section_key=section_key)

        label, purpose = AGENT_ROLES[agent_id]
        sections = document.get("sections") or {}
        focus = ""
        if section_key:
            section = sections.get(section_key) or {}
            focus = str(section.get("text") if isinstance(section, dict) else section)

        previous = self._messages(limit=20)
        conversation = "\n".join(
            f"{m.get('message_role')}:{m.get('agent_id') or 'user'}: {_short(m.get('content'), 1200)}"
            for m in previous[-10:]
        )

        system = f"""You are {label}, one member of a collaborative scientific review team.
Role: {purpose}

Rules:
- Be adversarial but constructive.
- Use ONLY the supplied corpus and draft.
- Cite source tags [P#] whenever you rely on corpus information.
- State clearly when evidence is only abstract/metadata level.
- Do not invent facts.
- Identify what could refute the draft and what evidence is missing.
- The user is a collaborator and may reject or edit your suggestions.
- Reply in language code {language}.
- Return JSON only."""

        user = f"""Research topic:
{document.get('topic') or ''}

Section under discussion:
{section_key or 'general'}
{focus}

Current draft:
{_short(sections, 18000)}

Corpus:
{context}

Recent discussion:
{conversation}

User message:
{message}

Return:
{{
  "response": "...",
  "objections": ["..."],
  "recommended_changes": ["..."],
  "evidence_refs": ["P1"],
  "confidence": 0.0
}}"""

        answer = _parse_json_response(self.provider.complete(system, user))  # type: ignore[attr-defined]
        response_text = str(answer.get("response") or "").strip()
        objections = [str(x) for x in answer.get("objections") or []]
        changes = [str(x) for x in answer.get("recommended_changes") or []]
        if objections:
            response_text += "\n\nPosibles refutaciones:\n- " + "\n- ".join(objections)
        if changes:
            response_text += "\n\nCambios sugeridos:\n- " + "\n- ".join(changes)
        refs = [str(x) for x in answer.get("evidence_refs") or [] if str(x).startswith("P")]
        agent_message = self._insert_message(
            role="agent",
            content=response_text,
            agent_id=agent_id,
            section_key=section_key,
            refs=refs,
        )
        return {
            "message": agent_message,
            "agent": {"id": agent_id, "label": label, "purpose": purpose},
            "confidence": answer.get("confidence"),
            "evidence_manifest": manifest,
        }

    def review_section(
        self,
        section_key: str,
        agent_id: str = "critical_reviewer",
        language: str = "es",
    ) -> dict[str, Any]:
        if section_key not in SECTION_KEYS:
            raise ValueError("unknown section")
        return self.discuss(
            "Revisa esta sección. Identifica afirmaciones refutables, evidencia insuficiente, "
            "contradicciones, sobreinterpretaciones y cambios concretos antes de aceptarla.",
            agent_id,
            section_key=section_key,
            language=language,
        )