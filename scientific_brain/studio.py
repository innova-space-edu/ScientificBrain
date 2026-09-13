from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

import httpx

from .auth import AuthenticatedUser, supabase_public_config
from .graph_store import ScientificGraphStore
from .providers import provider_from_env
from .user_snapshot import UserSnapshotStore
from .workspaces import UserWorkspaceStore


SECTION_KEYS = [
    "resumen",
    "estado_del_arte",
    "brecha",
    "pregunta_investigacion",
    "objetivo_general",
    "objetivos_especificos",
    "hipotesis",
    "desarrollo",
    "analisis_discusion",
    "conclusiones",
    "limitaciones",
    "proximos_pasos",
]

REVIEWER_ROLES = {
    "theory": "revisor de teoría",
    "experiment": "revisor experimental",
    "methodology": "revisor metodológico",
    "adversarial": "revisor adversarial/escéptico",
    "reproducibility": "revisor de reproducibilidad",
    "writer": "editor científico",
}


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI response did not contain a JSON object")
    payload = json.loads(text[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object")
    return payload


def _clean_sections(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key in SECTION_KEYS:
        item = value.get(key)
        if isinstance(item, str):
            out[key] = {"content": item, "source_refs": [], "status": "draft"}
        elif isinstance(item, dict):
            out[key] = {
                "content": str(item.get("content") or ""),
                "source_refs": [str(x) for x in (item.get("source_refs") or []) if str(x).strip()],
                "status": str(item.get("status") or "draft"),
            }
    return out


@dataclass
class ResearchStudioStore:
    user: AuthenticatedUser
    timeout: float = 30.0

    def __post_init__(self) -> None:
        config = supabase_public_config()
        self.url = config["url"].rstrip("/")
        self.key = config["publishable_key"]

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.user.access_token}",
            "Content-Type": "application/json",
        }

    def _endpoint(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = httpx.get(self._endpoint(table), headers=self.headers, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _insert(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            self._endpoint(table),
            headers={**self.headers, "Prefer": "return=representation"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else payload

    def _patch(self, table: str, params: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.patch(
            self._endpoint(table),
            headers={**self.headers, "Prefer": "return=representation"},
            params=params,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else payload

    def get_study(self, study_id: str) -> dict[str, Any] | None:
        rows = self._select("scibrain_studies", {"study_id": f"eq.{study_id}", "select": "*", "limit": "1"})
        return rows[0] if rows else None

    def latest_study(self, folder_id: str) -> dict[str, Any] | None:
        rows = self._select("scibrain_studies", {"folder_id": f"eq.{folder_id}", "select": "*", "order": "updated_at.desc", "limit": "1"})
        return rows[0] if rows else None

    def create_study(self, folder_id: str, topic: str, question: str = "", language: str = "es") -> dict[str, Any]:
        return self._insert("scibrain_studies", {"study_id": str(uuid.uuid4()), "owner_id": self.user.user_id, "folder_id": folder_id, "topic": topic, "title": topic, "research_question": question, "language": language, "sections": {}, "source_snapshot": {}, "status": "draft", "revision": 1})

    def update_study(self, study_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        study = self.get_study(study_id)
        if not study:
            raise KeyError("study_not_found")
        updates: dict[str, Any] = {}
        for key in ("topic", "title", "research_question", "language", "status", "source_snapshot"):
            if key in payload:
                updates[key] = payload[key]
        if "sections" in payload:
            current = _clean_sections(study.get("sections") or {})
            current.update(_clean_sections(payload.get("sections") or {}))
            updates["sections"] = current
        updates["revision"] = int(study.get("revision") or 0) + 1
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self._patch("scibrain_studies", {"study_id": f"eq.{study_id}"}, updates)

    def add_review(self, study_id: str, folder_id: str, section_key: str, agent_role: str, review: dict[str, Any]) -> dict[str, Any]:
        return self._insert("scibrain_study_reviews", {"review_id": str(uuid.uuid4()), "owner_id": self.user.user_id, "folder_id": folder_id, "study_id": study_id, "section_key": section_key, "agent_role": agent_role, "review": review})

    def list_reviews(self, study_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return self._select("scibrain_study_reviews", {"study_id": f"eq.{study_id}", "select": "*", "order": "created_at.desc", "limit": str(max(1, min(limit, 500)))})

    def add_message(self, study_id: str, folder_id: str, speaker: str, content: str, *, agent_role: str | None = None, source_refs: list[str] | None = None) -> dict[str, Any]:
        return self._insert("scibrain_discussion_messages", {"message_id": str(uuid.uuid4()), "owner_id": self.user.user_id, "folder_id": folder_id, "study_id": study_id, "speaker": speaker, "agent_role": agent_role, "content": content, "source_refs": source_refs or []})

    def list_messages(self, study_id: str, limit: int = 200) -> list[dict[str, Any]]:
        return self._select("scibrain_discussion_messages", {"study_id": f"eq.{study_id}", "select": "*", "order": "created_at.asc", "limit": str(max(1, min(limit, 500)))})


@dataclass
class ResearchStudioService:
    user: AuthenticatedUser

    def __post_init__(self) -> None:
        self.store = ResearchStudioStore(self.user)
        self.workspace = UserWorkspaceStore(self.user)

    def _ensure_folder(self, folder_id: str) -> dict[str, Any]:
        folder = self.workspace.get_folder(folder_id)
        if not folder:
            raise KeyError("folder_not_found")
        return folder

    def _corpus_context(self, folder_id: str, max_chars: int = 52000) -> tuple[str, dict[str, Any]]:
        self._ensure_folder(folder_id)
        papers = sorted(self.workspace.list_papers(folder_id), key=lambda p: (0 if p.get("review_depth") == "full_text_reviewed" else 1, str(p.get("publication_date") or "")))
        snapshot = UserSnapshotStore(self.user, folder_id=folder_id)
        ids = [str(p.get("canonical_id")) for p in papers if p.get("canonical_id")]
        bundle_map = {str((b.get("record") or {}).get("canonical_id")): b for b in snapshot.load_paper_bundles(ids)}
        lines: list[str] = []
        size = 0
        full_count = 0
        for index, paper in enumerate(papers, start=1):
            pid = str(paper.get("canonical_id") or "")
            bundle = bundle_map.get(pid) or {}
            record, analysis = bundle.get("record") or {}, bundle.get("analysis") or {}
            depth = str(paper.get("review_depth") or "metadata_verified")
            if depth == "full_text_reviewed":
                full_count += 1
            claims = " | ".join(f"{c.get('claim_id')}: {c.get('text')}" for c in (analysis.get("claims") or [])[:12] if isinstance(c, dict) and c.get("text"))
            evidence = " | ".join(f"{e.get('evidence_id')}: {e.get('text')} (p.{e.get('page') or '?'})" for e in (analysis.get("evidence") or [])[:10] if isinstance(e, dict) and e.get("text"))
            block = f"\nSOURCE {index}\nid={pid}\ntitle={paper.get('title')}\ndoi={paper.get('doi') or ''}\nyear={str(paper.get('publication_date') or '')[:4]}\nreview_depth={depth}\naccess={paper.get('access_status') or ''}\nabstract={str(record.get('abstract') or '')[:1800]}\nfull_text_summary={str(analysis.get('summary') or '')[:1800]}\nclaims={claims[:3500]}\nevidence={evidence[:3500]}\n"
            if size + len(block) > max_chars:
                break
            lines.append(block)
            size += len(block)
        graph_summary: dict[str, Any] = {}
        try:
            graph_summary = ScientificGraphStore(self.user, folder_id).summary()
        except Exception:
            pass
        return "".join(lines), {"paper_ids": ids, "paper_count": len(papers), "full_text_reviewed": full_count, "graph_summary": graph_summary}

    def suggest(self, folder_id: str, topic: str, language: str = "es") -> dict[str, Any]:
        context, snapshot = self._corpus_context(folder_id, max_chars=38000)
        provider = provider_from_env("cloud", task="research")
        system = """You are ScientificBrain Research Designer. Use ONLY the supplied corpus. Distinguish full-text-reviewed evidence from abstract/metadata-only material. Do not invent results. Propose research directions that can be challenged by a scientist. Return JSON only with: title_suggestions (array), research_questions (array of objects with question, rationale, source_refs), objective_suggestions (array), gaps (array), search_queries (array). source_refs must contain only source IDs supplied in the corpus. If evidence is insufficient, say so."""
        result = _extract_json(provider.complete(system, f"Language: {language}\nResearch topic: {topic}\n\nCORPUS:\n{context}\n\nGenerate 3-5 focused research-question alternatives and evidence-grounded gaps."))
        result["source_snapshot"] = snapshot
        return result

    def generate_draft(self, study_id: str, language: str = "es") -> dict[str, Any]:
        study = self.store.get_study(study_id)
        if not study:
            raise KeyError("study_not_found")
        context, snapshot = self._corpus_context(str(study["folder_id"]))
        provider = provider_from_env("cloud", task="research")
        system = """You are the ScientificBrain collaborative scientific writer. Use ONLY the supplied corpus. Never fabricate experiments, measurements, equations, citations or conclusions. Full-text-reviewed sources may support detailed claims; abstract/metadata-only sources must be treated as preliminary context. Every section must preserve uncertainty and conflicting evidence. Return JSON only. Each section is an object with content (string), source_refs (array of source IDs), status (draft). Required section keys: resumen, estado_del_arte, brecha, pregunta_investigacion, objetivo_general, objetivos_especificos, hipotesis, desarrollo, analisis_discusion, conclusiones, limitaciones, proximos_pasos. The conclusiones section must be a literature-grounded conclusion, not fabricated new experimental results. If the corpus cannot support a section, explicitly state the evidence gap."""
        prompt = f"Language: {language}\nTopic: {study.get('topic') or ''}\nCurrent research question: {study.get('research_question') or ''}\n\nCORPUS:\n{context}\n\nReturn JSON with title, research_question and sections."
        result = _extract_json(provider.complete(system, prompt))
        return self.store.update_study(study_id, {"title": str(result.get("title") or study.get("title") or study.get("topic") or ""), "research_question": str(result.get("research_question") or study.get("research_question") or ""), "language": language, "sections": _clean_sections(result.get("sections") or {}), "source_snapshot": snapshot})

    def review_section(self, study_id: str, section_key: str, agent_role: str, language: str = "es") -> dict[str, Any]:
        study = self.store.get_study(study_id)
        if not study:
            raise KeyError("study_not_found")
        if section_key not in SECTION_KEYS:
            raise ValueError("unknown section")
        role = REVIEWER_ROLES.get(agent_role, REVIEWER_ROLES["adversarial"])
        content = str(((study.get("sections") or {}).get(section_key) or {}).get("content") or "")
        context, _ = self._corpus_context(str(study["folder_id"]), max_chars=36000)
        provider = provider_from_env("cloud", task="research")
        system = f"""You are {role} in ScientificBrain. Critique rather than merely agree. Audit the supplied section against the corpus. Separate unsupported statements, regime mismatch, methodological weaknesses, missing counter-evidence and claims that are adequately supported. Return JSON only with verdict, strengths, concerns, required_changes, questions_for_author, source_refs. source_refs must contain only source IDs present in the corpus."""
        review = _extract_json(provider.complete(system, f"Language: {language}\nSection: {section_key}\nText:\n{content}\n\nCORPUS:\n{context}"))
        return self.store.add_review(study_id, str(study["folder_id"]), section_key, agent_role, review)

    def chat(self, study_id: str, message: str, agent_role: str, language: str = "es") -> dict[str, Any]:
        study = self.store.get_study(study_id)
        if not study:
            raise KeyError("study_not_found")
        message = message.strip()
        if not message:
            raise ValueError("message is required")
        folder_id = str(study["folder_id"])
        role = REVIEWER_ROLES.get(agent_role, REVIEWER_ROLES["adversarial"])
        self.store.add_message(study_id, folder_id, "user", message)
        history = self.store.list_messages(study_id, limit=40)
        context, _ = self._corpus_context(folder_id, max_chars=30000)
        sections = _clean_sections(study.get("sections") or {})
        draft = "\n\n".join(f"{key.upper()}:\n{item.get('content','')[:2500]}" for key, item in sections.items() if item.get("content"))
        history_text = "\n".join(f"{row.get('speaker')}[{row.get('agent_role') or ''}]: {row.get('content')}" for row in history[-20:])
        provider = provider_from_env("cloud", task="research")
        system = f"""You are {role} participating in a collaborative scientific discussion. Be critical, constructive and evidence-grounded. You may disagree with the user or other agents. Use only the supplied corpus for factual scientific claims. Cite supporting sources inline as [source:SOURCE_ID]. Clearly label hypotheses or inference. Never pretend metadata-only material was read in full. Respond in the requested language."""
        response = provider.complete(system, f"Language: {language}\nCurrent study title: {study.get('title') or ''}\nResearch question: {study.get('research_question') or ''}\n\nCURRENT DRAFT:\n{draft}\n\nRECENT DISCUSSION:\n{history_text}\n\nCORPUS:\n{context}\n\nReply to the latest user message.").strip()
        source_refs = list(dict.fromkeys(re.findall(r"\[source:([^\]]+)\]", response)))
        agent_row = self.store.add_message(study_id, folder_id, "agent", response, agent_role=agent_role, source_refs=source_refs)
        return {"message": agent_row, "source_refs": source_refs}
