from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .auth import AuthenticatedUser
from .workspaces import UserWorkspaceStore


@dataclass
class UsageRecorder:
    """Best-effort user-scoped operational telemetry.

    Observability must never make scientific work fail. Callers therefore record events after the
    scientific operation and may safely ignore failures from this recorder.
    """

    user: AuthenticatedUser
    folder_id: str | None = None

    def __post_init__(self) -> None:
        self.workspace = UserWorkspaceStore(self.user)

    def record(
        self,
        event_type: str,
        *,
        paper_id: str | None = None,
        document_id: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.workspace._insert(
                "scibrain_usage_events",
                {
                    "owner_id": self.user.user_id,
                    "folder_id": self.folder_id,
                    "event_type": str(event_type)[:120],
                    "paper_id": paper_id,
                    "document_id": document_id,
                    "duration_ms": duration_ms,
                    "metadata": metadata or {},
                },
            )
        except Exception:
            return
