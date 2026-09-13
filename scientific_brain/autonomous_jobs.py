from __future__ import annotations

from typing import Any

from .jobs import ScientificJobProcessor


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
    """ScientificJobProcessor with bounded phase-level retry recovery.

    A transient provider/network/structured-output failure no longer forces the user to
    press Analyze again. The last persisted checkpoint is restored to pending and the next
    invocation resumes the same phase. Structural errors still fail after a bounded budget.
    """

    max_phase_retries = 3

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
            history.append({
                "phase": phase,
                "attempt": retries + 1,
                "error": f"{type(exc).__name__}: {exc}",
            })
            if _retryable(exc) and retries < self.max_phase_retries:
                progress.update({
                    "retryable": True,
                    "retry_phase": phase,
                    "phase_retry_count": retries + 1,
                    "error_history": history[-12:],
                })
                self.snapshot_store.update_job(
                    job_id,
                    status="pending",
                    progress=progress,
                    last_error=f"Transient failure in {phase}; automatic retry {retries + 1}/{self.max_phase_retries}: {type(exc).__name__}: {exc}",
                )
                return self.snapshot_store.get_job(job_id) or current
            progress.update({
                "retryable": False,
                "retry_phase": phase,
                "phase_retry_count": retries,
                "error_history": history[-12:],
            })
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
