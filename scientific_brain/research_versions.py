from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

from .auth import AuthenticatedUser
from .workspaces import UserWorkspaceStore


SECTION_LABELS = {
    "abstract": "Abstract",
    "state_of_art": "Estado del arte",
    "research_question": "Pregunta de investigación",
    "objectives": "Objetivos",
    "hypotheses": "Hipótesis y predicciones",
    "development": "Desarrollo científico",
    "analysis": "Análisis de evidencia",
    "critical_analysis": "Análisis crítico",
    "novelty": "Novedad y brecha",
    "future_work": "Trabajo futuro",
    "conclusion": "Conclusión",
}


def _text(section: Any) -> str:
    if isinstance(section, dict):
        return str(section.get("text") or "")
    return str(section or "")


def _slug(text: str) -> str:
    out = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip()).strip("._")
    return out[:90] or "scientificbrain_research"


def _bibtex_key(source: dict[str, Any], number: int) -> str:
    authors = source.get("authors") or []
    surname = "source"
    if isinstance(authors, list) and authors:
        first = authors[0]
        name = first.get("name") if isinstance(first, dict) else str(first)
        parts = str(name or "").split()
        if parts:
            surname = re.sub(r"[^A-Za-z0-9]", "", parts[-1]) or "source"
    year = str(source.get("publication_date") or "")[:4] or "nd"
    return f"{surname}{year}_{number}"


@dataclass
class ResearchVersionStore:
    user: AuthenticatedUser
    folder_id: str

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)

    def document(self) -> dict[str, Any] | None:
        rows = self.workspace._select("scibrain_research_documents", {
            "folder_id": f"eq.{self.folder_id}", "select": "*", "limit": "1",
        })
        return rows[0] if rows else None


    def corpus_fingerprint(self) -> str:
        rows = self.workspace._select("scibrain_folder_papers", {
            "folder_id": f"eq.{self.folder_id}",
            "select": "canonical_id,review_depth,updated_at",
            "order": "canonical_id.asc",
        })
        payload = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()

    def mark_fresh(self, document: dict[str, Any] | None = None) -> dict[str, Any] | None:
        document = document or self.document()
        if not document or not document.get("document_id"):
            return document
        return self.workspace._patch("scibrain_research_documents", {
            "document_id": f"eq.{document['document_id']}"
        }, {
            "corpus_fingerprint": self.corpus_fingerprint(),
            "stale_reason": None,
            "last_evidence_refresh_at": datetime.now(timezone.utc).isoformat(),
        })

    def snapshot(self, document: dict[str, Any] | None, reason: str = "update") -> dict[str, Any] | None:
        if not document or not document.get("document_id"):
            return None
        revision = int(document.get("revision") or 1)
        existing = self.workspace._select("scibrain_research_versions", {
            "document_id": f"eq.{document['document_id']}", "revision": f"eq.{revision}",
            "select": "version_id,revision,reason,created_at", "limit": "1",
        })
        if existing:
            return existing[0]
        return self.workspace._insert("scibrain_research_versions", {
            "owner_id": self.user.user_id,
            "folder_id": self.folder_id,
            "document_id": document["document_id"],
            "revision": revision,
            "reason": reason,
            "topic": document.get("topic") or "",
            "research_brief": document.get("research_brief") or {},
            "sections": document.get("sections") or {},
            "evidence_manifest": document.get("evidence_manifest") or {},
            "novelty_assessment": document.get("novelty_assessment") or {},
        })

    def list_versions(self, limit: int = 80) -> list[dict[str, Any]]:
        document = self.document()
        if not document:
            return []
        return self.workspace._select("scibrain_research_versions", {
            "document_id": f"eq.{document['document_id']}",
            "select": "version_id,revision,reason,topic,created_at",
            "order": "revision.desc", "limit": str(max(1, min(limit, 200))),
        })

    def restore(self, version_id: str) -> dict[str, Any]:
        current = self.document()
        if not current:
            raise KeyError("research_document_not_found")
        rows = self.workspace._select("scibrain_research_versions", {
            "version_id": f"eq.{version_id}", "document_id": f"eq.{current['document_id']}",
            "select": "*", "limit": "1",
        })
        if not rows:
            raise KeyError("research_version_not_found")
        version = rows[0]
        updated = self.workspace._patch("scibrain_research_documents", {
            "document_id": f"eq.{current['document_id']}"
        }, {
            "topic": version.get("topic") or current.get("topic") or "",
            "research_brief": version.get("research_brief") or {},
            "sections": version.get("sections") or {},
            "evidence_manifest": version.get("evidence_manifest") or {},
            "novelty_assessment": version.get("novelty_assessment") or {},
            "revision": int(current.get("revision") or 1) + 1,
            "status": "restored",
        })
        self.snapshot(updated, reason=f"restore_from_revision_{version.get('revision')}")
        return updated

    def export(self, fmt: str = "markdown") -> dict[str, Any]:
        document = self.document()
        if not document:
            raise KeyError("research_document_not_found")
        fmt = fmt.strip().lower()
        title = str(document.get("topic") or "ScientificBrain Research").strip()
        sections = document.get("sections") or {}
        sources = ((document.get("evidence_manifest") or {}).get("sources") or [])
        sources = sorted(sources, key=lambda s: int(s.get("citation_number") or 999999))
        base = _slug(title)

        if fmt in {"json", "scibrain"}:
            return {
                "format": "json", "mime": "application/json", "filename": f"{base}.json",
                "content": json.dumps(document, ensure_ascii=False, indent=2, default=str),
            }
        if fmt in {"bib", "bibtex"}:
            entries: list[str] = []
            for i, source in enumerate(sources, 1):
                number = int(source.get("citation_number") or i)
                key = _bibtex_key(source, number)
                authors = source.get("authors") or []
                if isinstance(authors, list):
                    author_text = " and ".join(
                        str(a.get("name") or a.get("display_name") or "") if isinstance(a, dict) else str(a)
                        for a in authors
                    )
                else:
                    author_text = str(authors)
                year = str(source.get("publication_date") or "")[:4]
                fields = {
                    "title": source.get("title"), "author": author_text, "journal": source.get("journal"),
                    "year": year, "doi": source.get("doi"), "url": source.get("source_url"),
                }
                lines = [f"@article{{{key},"]
                for field, value in fields.items():
                    if value:
                        clean = str(value).replace("{", "\\{").replace("}", "\\}")
                        lines.append(f"  {field} = {{{clean}}},")
                lines.append("}")
                entries.append("\n".join(lines))
            return {"format": "bibtex", "mime": "text/plain", "filename": f"{base}.bib", "content": "\n\n".join(entries)}
        if fmt in {"tex", "latex"}:
            body = ["\\documentclass[11pt]{article}", "\\usepackage[utf8]{inputenc}", "\\usepackage{hyperref}", "\\begin{document}", f"\\section*{{{title}}}"]
            for key, label in SECTION_LABELS.items():
                text = _text(sections.get(key)).strip()
                if text:
                    escaped = text.replace("%", "\\%").replace("&", "\\&").replace("#", "\\#")
                    body.extend([f"\\section*{{{label}}}", escaped])
            if sources:
                body.append("\\section*{Referencias}")
                body.append("\\begin{enumerate}")
                for source in sources:
                    ref = str(source.get("reference") or source.get("title") or "Fuente")
                    ref = re.sub(r"^\[\d+\]\s*", "", ref).replace("%", "\\%").replace("&", "\\&")
                    body.append(f"\\item {ref}")
                body.append("\\end{enumerate}")
            body.append("\\end{document}")
            return {"format": "latex", "mime": "text/x-tex", "filename": f"{base}.tex", "content": "\n\n".join(body)}

        lines = [f"# {title}", ""]
        brief = document.get("research_brief") or {}
        if brief:
            lines.extend(["## Research Brief", "", json.dumps(brief, ensure_ascii=False, indent=2, default=str), ""])
        for key, label in SECTION_LABELS.items():
            text = _text(sections.get(key)).strip()
            if text:
                lines.extend([f"## {label}", "", text, ""])
        if sources:
            lines.extend(["## Referencias", ""])
            for source in sources:
                lines.append(str(source.get("reference") or f"[{source.get('citation_number')}] {source.get('title')}"))
        return {"format": "markdown", "mime": "text/markdown", "filename": f"{base}.md", "content": "\n".join(lines)}
