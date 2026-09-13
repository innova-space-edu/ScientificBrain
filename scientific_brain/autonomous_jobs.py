from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import jobs as _jobs
from .agents import MathematicalAgent, StatisticalAgent
from .jobs import ScientificJobProcessor, _specialist_agents as _base_specialist_agents
from .models import PaperKind
from .workspaces import UserWorkspaceStore


def _research_provider(provider: object) -> object:
    selector = getattr(provider, "for_task", None)
    return selector("research") if callable(selector) else provider


def _v012_specialist_agents(provider: object, kind: PaperKind) -> list[object]:
    """Extend the stable v0.11 reviewer registry without rewriting the job engine.

    Mathematics is audited for theory/simulation/hybrid work and also for experimental work
    because dimensional consistency and derived quantities frequently matter there. Statistical
    review is added only where empirical variability is normally meaningful.
    """
    base = list(_base_specialist_agents(provider, kind))
    routed = _research_provider(provider)
    extras: list[object] = []
    if kind in {PaperKind.THEORETICAL, PaperKind.SIMULATION, PaperKind.EXPERIMENTAL, PaperKind.HYBRID}:
        extras.append(MathematicalAgent(routed))
    if kind in {PaperKind.EXPERIMENTAL, PaperKind.HYBRID}:
        extras.append(StatisticalAgent(routed))
    if not extras:
        return base
    # Keep adversarial and reproducibility reviewers last so they can remain the final independent
    # challenge layers while preserving the phase/checkpoint behavior of the existing job engine.
    split = max(0, len(base) - 2)
    return base[:split] + extras + base[split:]


# ScientificJobProcessor resolves this registry from scientific_brain.jobs at runtime.
# The assignment is intentionally isolated here so legacy/local workflows that import jobs.py
# directly retain their original behavior, while the production autonomous processor gets v0.12.
_jobs._specialist_agents = _v012_specialist_agents


_PERMANENT_MARKERS = (
    "pdf contains no extractable text",
    "no open-access pdf could be resolved",
    "paper not found",
    "folder_not_found",
    "unsupported job type",
    "requires payload.paper_id",
    "unknown review phase",
    "job is not attached",
)


def _retryable(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    return not any(marker in message for marker in _PERMANENT_MARKERS)


class AutonomousScientificJobProcessor(ScientificJobProcessor):
    """ScientificJobProcessor with bounded phase retry recovery and stale-evidence signaling."""

    max_phase_retries = 3

    def _mark_research_stale(self, paper_id: str) -> None:
        user = getattr(self.snapshot_store, "user", None)
        folder_id = getattr(self.snapshot_store, "folder_id", None)
        if user is None or not folder_id:
            return
        try:
            workspace = UserWorkspaceStore(user)
            rows = workspace._select(
                "scibrain_research_documents",
                {
                    "folder_id": f"eq.{folder_id}",
                    "select": "document_id,status,stale_reason",
                    "limit": "1",
                },
            )
            if not rows:
                return
            document = rows[0]
            workspace._patch(
                "scibrain_research_documents",
                {"document_id": f"eq.{document['document_id']}"},
                {
                    "status": "stale_evidence",
                    "stale_reason": f"paper_full_text_reviewed:{paper_id}",
                },
            )
        except Exception:
            # Paper review must never fail because a collaborative draft could not be marked stale.
            return

    def _review_paper(self, job: dict[str, Any]) -> dict[str, Any]:
        result = super()._review_paper(job)
        if str(result.get("phase") or "") == "completed":
            paper_id = str(
                result.get("paper_id") or (job.get("payload") or {}).get("paper_id") or ""
            )
            if paper_id:
                self._mark_research_stale(paper_id)
        return result

    def run(self, job_id: str) -> dict[str, Any]:
        try:
            result = super().run(job_id)
        except Exception as exc:
            current = self.snapshot_store.get_job(job_id)
            if not current:
                raise
            progress = dict(current.get("progress") or {})
            phase = str(progress.get("phase") or "unknown")
            previous_phase = str(progress.get("retry_phase") or "")
            retries = int(progress.get("phase_retry_count") or 0) if previous_phase == phase else 0
            history = list(progress.get("error_history") or [])
            history.append(
                {
                    "phase": phase,
                    "attempt": retries + 1,
                    "error": f"{type(exc).__name__}: {exc}",
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            )
            if _retryable(exc) and retries < self.max_phase_retries:
                progress.update(
                    {
                        "retryable": True,
                        "retry_phase": phase,
                        "phase_retry_count": retries + 1,
                        "error_history": history[-12:],
                    }
                )
                self.snapshot_store.update_job(
                    job_id,
                    status="pending",
                    progress=progress,
                    last_error=(
                        f"Transient failure in {phase}; automatic retry "
                        f"{retries + 1}/{self.max_phase_retries}: {type(exc).__name__}: {exc}"
                    ),
                )
                return self.snapshot_store.get_job(job_id) or current
            progress.update(
                {
                    "retryable": False,
                    "retry_phase": phase,
                    "phase_retry_count": retries,
                    "error_history": history[-12:],
                }
            )
            self.snapshot_store.update_job(job_id, status="failed", progress=progress)
            raise

        progress = dict(result.get("progress") or {})
        changed = False
        for key in ("retryable", "retry_phase", "phase_retry_count", "reason", "soft_deadline_seconds"):
            if key in progress:
                progress.pop(key, None)
                changed = True
        if changed:
            self.snapshot_store.update_job(job_id, progress=progress)
            result = self.snapshot_store.get_job(job_id) or result
        return result
