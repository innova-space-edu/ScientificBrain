from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .artifacts import ArtifactRecord
from .models import ResearchState
from .research_contracts import ResearchProjectDefinition


class SnapshotStore(Protocol):
    def save_project(self, project: ResearchProjectDefinition) -> None: ...
    def save_state(self, state: ResearchState, project_id: str | None = None) -> None: ...
    def save_artifact(self, artifact: ArtifactRecord) -> None: ...
    def load_state(self, session_id: str) -> ResearchState | None: ...
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

    def _endpoint(self, table: str) -> str:
        return f"{self.url.rstrip('/')}/rest/v1/{table}"

    def save_project(self, project: ResearchProjectDefinition) -> None:
        response = httpx.post(
            self._endpoint("scibrain_projects"),
            headers=self.headers,
            json={
                "project_id": project.project_id,
                "title": project.title,
                "discipline": project.discipline,
                "definition": project.model_dump(mode="json"),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

    def save_state(self, state: ResearchState, project_id: str | None = None) -> None:
        response = httpx.post(
            self._endpoint("scibrain_states"),
            headers=self.headers,
            json={
                "session_id": state.session_id,
                "project_id": project_id or state.project_id,
                "question": state.question,
                "stage": state.stage.value,
                "state": state.model_dump(mode="json"),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

    def save_artifact(self, artifact: ArtifactRecord) -> None:
        response = httpx.post(
            self._endpoint("scibrain_artifacts"),
            headers=self.headers,
            json={
                "artifact_id": artifact.artifact_id,
                "session_id": artifact.session_id,
                "artifact_type": artifact.artifact_type,
                "payload": artifact.model_dump(mode="json"),
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

    def load_state(self, session_id: str) -> ResearchState | None:
        response = httpx.get(
            self._endpoint("scibrain_states"),
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
            },
            params={"session_id": f"eq.{session_id}", "select": "state", "limit": "1"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            return None
        return ResearchState.model_validate(rows[0]["state"])

    def status(self) -> dict[str, Any]:
        return {
            "backend": "supabase",
            "configured": bool(self.url and self.service_role_key),
            "url_configured": bool(self.url),
            "service_role_key_configured": bool(self.service_role_key),
        }


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
