from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from .artifacts import ArtifactRecord
from .auth import AuthenticatedUser, supabase_public_config
from .models import Critique, Paper, PaperAnalysis, ResearchState, ReviewDepth, SpecialistReview
from .research_contracts import ResearchProjectDefinition


@dataclass
class UserSnapshotStore:
    """Supabase persistence using the signed-in user's JWT so RLS remains authoritative."""

    user: AuthenticatedUser
    folder_id: str | None = None
    timeout: float = 30.0

    def __post_init__(self) -> None:
        config = supabase_public_config()
        self.url = config["url"].rstrip("/")
        self.key = config["publishable_key"]
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be configured")

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

    def _patch(self, table: str, params: dict[str, str], payload: dict[str, Any]) -> None:
        response = httpx.patch(
            self._endpoint(table),
            headers={**self.headers, "Prefer": "return=minimal"},
            params=params,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

    def save_project(self, project: ResearchProjectDefinition) -> None:
        existing = self._select(
            "scibrain_projects",
            {"project_id": f"eq.{project.project_id}", "select": "project_id", "limit": "1"},
        )
        payload = {
            "owner_id": self.user.user_id,
            "folder_id": self.folder_id,
            "title": project.title,
            "discipline": project.discipline,
            "definition": project.model_dump(mode="json"),
            "status": "defined",
        }
        if existing:
            self._patch("scibrain_projects", {"project_id": f"eq.{project.project_id}"}, payload)
        else:
            self._insert("scibrain_projects", {"project_id": project.project_id, **payload})

    def load_project(self, project_id: str) -> ResearchProjectDefinition | None:
        rows = self._select(
            "scibrain_projects",
            {"project_id": f"eq.{project_id}", "select": "definition", "limit": "1"},
        )
        return ResearchProjectDefinition.model_validate(rows[0]["definition"]) if rows else None

    def list_projects(self, limit: int = 50) -> list[dict[str, Any]]:
        params = {
            "select": "project_id,folder_id,title,discipline,status,created_at,updated_at",
            "order": "updated_at.desc",
            "limit": str(max(1, min(limit, 200))),
        }
        if self.folder_id:
            params["folder_id"] = f"eq.{self.folder_id}"
        return self._select("scibrain_projects", params)

    def save_state(self, state: ResearchState, project_id: str | None = None) -> None:
        state.owner_id = self.user.user_id
        if not state.folder_id:
            state.folder_id = self.folder_id
        existing = self._select(
            "scibrain_states",
            {"session_id": f"eq.{state.session_id}", "select": "session_id", "limit": "1"},
        )
        payload = {
            "owner_id": self.user.user_id,
            "folder_id": state.folder_id,
            "project_id": project_id or state.project_id,
            "question": state.question,
            "stage": state.stage.value,
            "protocol_stage": state.protocol_stage,
            "state": state.model_dump(mode="json"),
        }
        if existing:
            self._patch("scibrain_states", {"session_id": f"eq.{state.session_id}"}, payload)
        else:
            self._insert("scibrain_states", {"session_id": state.session_id, **payload})

    def load_state(self, session_id: str) -> ResearchState | None:
        rows = self._select(
            "scibrain_states",
            {"session_id": f"eq.{session_id}", "select": "state", "limit": "1"},
        )
        return ResearchState.model_validate(rows[0]["state"]) if rows else None

    def save_artifact(self, artifact: ArtifactRecord) -> None:
        existing = self._select(
            "scibrain_artifacts",
            {"artifact_id": f"eq.{artifact.artifact_id}", "select": "artifact_id", "limit": "1"},
        )
        payload = {
            "owner_id": self.user.user_id,
            "session_id": artifact.session_id,
            "artifact_type": artifact.artifact_type,
            "payload": artifact.model_dump(mode="json"),
        }
        if existing:
            self._patch("scibrain_artifacts", {"artifact_id": f"eq.{artifact.artifact_id}"}, payload)
        else:
            self._insert("scibrain_artifacts", {"artifact_id": artifact.artifact_id, **payload})

    def list_artifacts(self, session_id: str) -> list[ArtifactRecord]:
        rows = self._select(
            "scibrain_artifacts",
            {"session_id": f"eq.{session_id}", "select": "payload", "order": "created_at.asc"},
        )
        return [ArtifactRecord.model_validate(row["payload"]) for row in rows]

    def _paper_row(self, paper_id: str) -> dict[str, Any] | None:
        if not self.folder_id:
            return None
        rows = self._select(
            "scibrain_folder_papers",
            {
                "folder_id": f"eq.{self.folder_id}",
                "canonical_id": f"eq.{paper_id}",
                "select": "item_id,record,analysis,critique,specialist_reviews,review_depth",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def save_paper_bundle(
        self,
        paper: Paper,
        analysis: PaperAnalysis | None = None,
        critique: Critique | None = None,
        specialist_reviews: list[SpecialistReview] | None = None,
    ) -> None:
        if not self.folder_id:
            raise RuntimeError("UserSnapshotStore needs folder_id to save a paper bundle")
        existing = self._paper_row(paper.canonical_id)
        payload = {
            "owner_id": self.user.user_id,
            "folder_id": self.folder_id,
            "canonical_id": paper.canonical_id,
            "title": paper.title,
            "authors": paper.authors,
            "publication_date": paper.publication_date.isoformat() if paper.publication_date else None,
            "journal": paper.journal,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "source_type": paper.source if paper.source in {"openalex", "arxiv", "crossref", "web", "manual", "upload"} else "manual",
            "source_url": str(paper.url) if paper.url else None,
            "review_depth": analysis.review_depth.value if analysis else ReviewDepth.METADATA.value,
            "record": paper.model_dump(mode="json"),
            "analysis": analysis.model_dump(mode="json") if analysis else None,
            "critique": critique.model_dump(mode="json") if critique else None,
            "specialist_reviews": [r.model_dump(mode="json") for r in (specialist_reviews or [])],
        }
        if existing:
            self._patch("scibrain_folder_papers", {"item_id": f"eq.{existing['item_id']}"}, payload)
        else:
            self._insert("scibrain_folder_papers", payload)

    def load_paper_bundles(self, paper_ids: list[str]) -> list[dict[str, Any]]:
        if not self.folder_id or not paper_ids:
            return []
        results: list[dict[str, Any]] = []
        for paper_id in paper_ids:
            row = self._paper_row(paper_id)
            if row:
                results.append({
                    "record": row.get("record") or {},
                    "analysis": row.get("analysis"),
                    "critique": row.get("critique"),
                    "specialist_reviews": row.get("specialist_reviews") or [],
                })
        return results

    def create_job(self, session_id: str, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "job_id": f"job:{uuid.uuid4().hex}",
            "owner_id": self.user.user_id,
            "session_id": session_id,
            "job_type": job_type,
            "status": "pending",
            "payload": payload,
            "progress": {},
        }
        return self._insert("scibrain_jobs", row)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        rows = self._select("scibrain_jobs", {"job_id": f"eq.{job_id}", "select": "*", "limit": "1"})
        return rows[0] if rows else None

    def list_jobs(self, session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        params = {"select": "*", "order": "created_at.desc", "limit": str(max(1, min(limit, 500)))}
        if session_id:
            params["session_id"] = f"eq.{session_id}"
        return self._select("scibrain_jobs", params)

    def update_job(self, job_id: str, **updates: Any) -> None:
        allowed = {"status", "progress", "last_error", "payload"}
        payload = {key: value for key, value in updates.items() if key in allowed}
        if payload:
            self._patch("scibrain_jobs", {"job_id": f"eq.{job_id}"}, payload)

    def status(self) -> dict[str, Any]:
        return {
            "backend": "supabase_user_rls",
            "configured": True,
            "authenticated_user": self.user.user_id,
            "folder_id": self.folder_id,
        }
