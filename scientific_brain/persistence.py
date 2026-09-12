from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .artifacts import ArtifactRecord, LocalArtifactStore
from .memory import ScientificMemory
from .models import Critique, Paper, PaperAnalysis, ResearchState, ReviewDepth, SpecialistReview
from .project_store import ProjectDefinitionStore
from .research_contracts import ResearchProjectDefinition


class SnapshotStore(Protocol):
    def save_project(self, project: ResearchProjectDefinition) -> None: ...
    def load_project(self, project_id: str) -> ResearchProjectDefinition | None: ...
    def list_projects(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def save_state(self, state: ResearchState, project_id: str | None = None) -> None: ...
    def load_state(self, session_id: str) -> ResearchState | None: ...
    def save_artifact(self, artifact: ArtifactRecord) -> None: ...
    def list_artifacts(self, session_id: str) -> list[ArtifactRecord]: ...
    def save_paper_bundle(
        self,
        paper: Paper,
        analysis: PaperAnalysis | None = None,
        critique: Critique | None = None,
        specialist_reviews: list[SpecialistReview] | None = None,
    ) -> None: ...
    def load_paper_bundles(self, paper_ids: list[str]) -> list[dict[str, Any]]: ...
    def create_job(self, session_id: str, job_type: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_job(self, job_id: str) -> dict[str, Any] | None: ...
    def update_job(self, job_id: str, **updates: Any) -> None: ...
    def status(self) -> dict[str, Any]: ...


@dataclass
class SupabaseSnapshotStore:
    url: str
    service_role_key: str
    timeout: float = 30.0

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    @property
    def read_headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
        }

    def _endpoint(self, table: str) -> str:
        return f"{self.url.rstrip('/')}/rest/v1/{table}"

    def _upsert(self, table: str, payload: dict[str, Any]) -> None:
        response = httpx.post(
            self._endpoint(table),
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

    def _select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = httpx.get(
            self._endpoint(table),
            headers=self.read_headers,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def save_project(self, project: ResearchProjectDefinition) -> None:
        self._upsert("scibrain_projects", {
            "project_id": project.project_id,
            "title": project.title,
            "discipline": project.discipline,
            "definition": project.model_dump(mode="json"),
            "status": "defined",
        })

    def load_project(self, project_id: str) -> ResearchProjectDefinition | None:
        rows = self._select(
            "scibrain_projects",
            {"project_id": f"eq.{project_id}", "select": "definition", "limit": "1"},
        )
        return ResearchProjectDefinition.model_validate(rows[0]["definition"]) if rows else None

    def list_projects(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._select(
            "scibrain_projects",
            {
                "select": "project_id,title,discipline,status,created_at,updated_at",
                "order": "updated_at.desc",
                "limit": str(max(1, min(limit, 200))),
            },
        )

    def save_state(self, state: ResearchState, project_id: str | None = None) -> None:
        self._upsert("scibrain_states", {
            "session_id": state.session_id,
            "project_id": project_id or state.project_id,
            "question": state.question,
            "stage": state.stage.value,
            "protocol_stage": state.protocol_stage,
            "state": state.model_dump(mode="json"),
        })

    def load_state(self, session_id: str) -> ResearchState | None:
        rows = self._select(
            "scibrain_states",
            {"session_id": f"eq.{session_id}", "select": "state", "limit": "1"},
        )
        return ResearchState.model_validate(rows[0]["state"]) if rows else None

    def save_artifact(self, artifact: ArtifactRecord) -> None:
        self._upsert("scibrain_artifacts", {
            "artifact_id": artifact.artifact_id,
            "session_id": artifact.session_id,
            "artifact_type": artifact.artifact_type,
            "payload": artifact.model_dump(mode="json"),
        })

    def list_artifacts(self, session_id: str) -> list[ArtifactRecord]:
        rows = self._select(
            "scibrain_artifacts",
            {
                "session_id": f"eq.{session_id}",
                "select": "payload",
                "order": "created_at.asc",
            },
        )
        return [ArtifactRecord.model_validate(row["payload"]) for row in rows]

    def save_paper_bundle(
        self,
        paper: Paper,
        analysis: PaperAnalysis | None = None,
        critique: Critique | None = None,
        specialist_reviews: list[SpecialistReview] | None = None,
    ) -> None:
        depth = analysis.review_depth.value if analysis else ReviewDepth.METADATA.value
        self._upsert("scibrain_papers", {
            "canonical_id": paper.canonical_id,
            "review_depth": depth,
            "record": paper.model_dump(mode="json"),
            "analysis": analysis.model_dump(mode="json") if analysis else None,
            "critique": critique.model_dump(mode="json") if critique else None,
            "specialist_reviews": [r.model_dump(mode="json") for r in (specialist_reviews or [])],
        })

    def load_paper_bundles(self, paper_ids: list[str]) -> list[dict[str, Any]]:
        if not paper_ids:
            return []
        encoded = ",".join(f'"{paper_id}"' for paper_id in paper_ids)
        rows = self._select(
            "scibrain_papers",
            {
                "canonical_id": f"in.({encoded})",
                "select": "record,analysis,critique,specialist_reviews",
            },
        )
        return rows

    def create_job(self, session_id: str, job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = f"job:{uuid.uuid4().hex}"
        row = {
            "job_id": job_id,
            "session_id": session_id,
            "job_type": job_type,
            "status": "pending",
            "payload": payload,
            "progress": {},
        }
        self._upsert("scibrain_jobs", row)
        return row

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        rows = self._select(
            "scibrain_jobs",
            {"job_id": f"eq.{job_id}", "select": "*", "limit": "1"},
        )
        return rows[0] if rows else None

    def update_job(self, job_id: str, **updates: Any) -> None:
        allowed = {"status", "progress", "last_error", "payload"}
        payload = {key: value for key, value in updates.items() if key in allowed}
        if not payload:
            return
        response = httpx.patch(
            self._endpoint("scibrain_jobs"),
            headers={**self.headers, "Prefer": "return=minimal"},
            params={"job_id": f"eq.{job_id}"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

    def status(self) -> dict[str, Any]:
        return {
            "backend": "supabase",
            "configured": bool(self.url and self.service_role_key),
            "url_configured": bool(self.url),
            "service_role_key_configured": bool(self.service_role_key),
        }


def hydrate_memory_from_snapshot(
    memory: ScientificMemory,
    store: SnapshotStore,
    session_id: str,
) -> ResearchState:
    state = store.load_state(session_id)
    if state is None:
        raise KeyError(f"Unknown cloud session: {session_id}")
    memory.save_state(state)

    if state.project_id:
        project = store.load_project(state.project_id)
        if project:
            ProjectDefinitionStore(memory).save(project)

    artifact_store = LocalArtifactStore(memory)
    for artifact in store.list_artifacts(session_id):
        artifact_store.save(artifact)

    paper_ids = list(dict.fromkeys(state.candidate_paper_ids + state.selected_paper_ids))
    for row in store.load_paper_bundles(paper_ids):
        paper = Paper.model_validate(row["record"])
        memory.upsert_paper(paper)
        if row.get("analysis"):
            memory.save_analysis(PaperAnalysis.model_validate(row["analysis"]))
        if row.get("critique"):
            memory.save_critique(Critique.model_validate(row["critique"]))
        for review_payload in row.get("specialist_reviews") or []:
            memory.save_specialist_review(SpecialistReview.model_validate(review_payload))
    return state


def snapshot_store_from_env() -> SnapshotStore | None:
    backend = os.getenv("SCIBRAIN_STORAGE_BACKEND", "sqlite").strip().lower()
    if backend in {"sqlite", "local", "none"}:
        return None
    if backend == "supabase":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError(
                "SCIBRAIN_STORAGE_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
            )
        return SupabaseSnapshotStore(url=url, service_role_key=key)
    raise ValueError(f"Unknown SCIBRAIN_STORAGE_BACKEND: {backend}")


def persistence_status() -> dict[str, Any]:
    backend = os.getenv("SCIBRAIN_STORAGE_BACKEND", "sqlite").strip().lower()
    if backend == "supabase":
        return {
            "backend": "supabase",
            "persistent": True,
            "supabase_url_configured": bool(os.getenv("SUPABASE_URL")),
            "service_role_key_configured": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        }
    return {
        "backend": backend,
        "persistent": backend not in {"sqlite", "local", "none"},
        "warning": "SQLite on Vercel is ephemeral; use Supabase for durable production state." if backend == "sqlite" else None,
    }
