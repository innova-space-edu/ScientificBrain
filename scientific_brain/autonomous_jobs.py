from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import jobs as _jobs
from .agents import MathematicalAgent, StatisticalAgent
from .jobs import ScientificJobProcessor, _specialist_agents as _base_specialist_agents
from .models import PaperKind
from .ocr_service import ScannedPaperOCR
from .visual_sweep import AutomaticVisualSweep, vision_configured
from .workspaces import UserWorkspaceStore


def _research_provider(provider: object) -> object:
    selector = getattr(provider, "for_task", None)
    return selector("research") if callable(selector) else provider


def _v012_specialist_agents(provider: object, kind: PaperKind) -> list[object]:
    base = list(_base_specialist_agents(provider, kind))
    routed = _research_provider(provider)
    extras: list[object] = []
    if kind in {PaperKind.THEORETICAL, PaperKind.SIMULATION, PaperKind.EXPERIMENTAL, PaperKind.HYBRID}:
        extras.append(MathematicalAgent(routed))
    if kind in {PaperKind.EXPERIMENTAL, PaperKind.HYBRID}:
        extras.append(StatisticalAgent(routed))
    if not extras:
        return base
    split = max(0, len(base) - 2)
    return base[:split] + extras + base[split:]


_jobs._specialist_agents = _v012_specialist_agents


_PERMANENT_MARKERS = (
    "no open-access pdf could be resolved",
    "paper not found",
    "folder_not_found",
    "unsupported job type",
    "requires payload.paper_id",
    "unknown review phase",
    "job is not attached",
    "multimodal ocr provider not configured",
)


def _retryable(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    return not any(marker in message for marker in _PERMANENT_MARKERS)


class AutonomousScientificJobProcessor(ScientificJobProcessor):
    """Resumable production processor with OCR, visual review and bounded recovery.

    Text extraction remains the first path. Image-only PDFs transparently switch the same review
    job into a page-batched OCR phase; after OCR the normal scientific review resumes. Once the
    textual/specialist review passes, a bounded set of high-value visual pages is analyzed before the
    job is marked completed. Optional OCR/visual layers never duplicate the text review.
    """

    max_phase_retries = 3

    def _context(self) -> tuple[Any | None, str | None]:
        return getattr(self.snapshot_store, "user", None), getattr(self.snapshot_store, "folder_id", None)

    def _mark_research_stale(self, paper_id: str) -> None:
        user, folder_id = self._context()
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
            workspace._patch(
                "scibrain_research_documents",
                {"document_id": f"eq.{rows[0]['document_id']}"},
                {
                    "status": "stale_evidence",
                    "stale_reason": f"paper_full_text_reviewed:{paper_id}",
                },
            )
        except Exception:
            return

    def _advance_ocr(self, job: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        user, folder_id = self._context()
        if user is None or not folder_id:
            raise RuntimeError("OCR requires authenticated folder-scoped persistence")
        paper_id = str(current.get("paper_id") or (job.get("payload") or {}).get("paper_id") or "")
        if not paper_id:
            raise ValueError("review_paper job requires payload.paper_id")
        if not vision_configured():
            raise ValueError("multimodal OCR provider not configured for scanned PDF")
        service = ScannedPaperOCR(user, str(folder_id))
        total = int(current.get("ocr_page_count") or 0)
        if total <= 0:
            total = service.page_count(paper_id)
        next_page = int(current.get("ocr_next_page") or 1)
        if next_page <= total:
            batch = service.process_batch(
                paper_id,
                next_page,
                batch_size=int((job.get("payload") or {}).get("ocr_batch_size") or 2),
                language=str((job.get("payload") or {}).get("language") or "es"),
            )
            current.update(
                {
                    "paper_id": paper_id,
                    "phase": "wait_ocr",
                    "ocr_page_count": total,
                    "ocr_next_page": int(batch.get("next_page") or (total + 1)),
                    "ocr_completed_pages": service.completed_pages(paper_id),
                    "steps_completed": int(current.get("steps_completed") or 0) + 1,
                    "__job_status": "pending",
                }
            )
            return current

        finalized = service.finalize(paper_id)
        # Start the original review again from prepare. It now resolves the persistent OCR memory.
        reset_job = dict(job)
        reset_job["progress"] = {}
        resumed = super()._review_paper(reset_job)
        resumed["ocr"] = {
            "used": True,
            "page_count": finalized.get("page_count"),
            "word_count": finalized.get("word_count"),
        }
        resumed["steps_completed"] = int(resumed.get("steps_completed") or 0) + int(current.get("steps_completed") or 0) + 1
        return resumed

    def _advance_visual_sweep(self, job: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        user, folder_id = self._context()
        paper_id = str(current.get("paper_id") or (job.get("payload") or {}).get("paper_id") or "")
        review_result = dict(current.get("review_result") or {})
        pages = [int(x) for x in (current.get("visual_pages") or []) if int(x) > 0]
        index = int(current.get("visual_index") or 0)
        if user is None or not folder_id or not paper_id or not pages or index >= len(pages):
            final = review_result or {"paper_id": paper_id, "phase": "completed"}
            final["phase"] = "completed"
            final["visual_sweep"] = {
                "planned_pages": pages,
                "analyzed_pages": current.get("visual_analyzed_pages") or [],
            }
            if paper_id:
                self._mark_research_stale(paper_id)
            return final

        sweep = AutomaticVisualSweep(user, str(folder_id))
        try:
            result = sweep.analyze_batch(
                paper_id,
                pages,
                index,
                batch_size=int((job.get("payload") or {}).get("visual_batch_size") or 1),
                language=str((job.get("payload") or {}).get("language") or "es"),
            )
        except Exception as exc:
            # Automatic visual enrichment is valuable but must not invalidate a completed textual
            # scientific review. Keep a bounded diagnostic and finish the paper review.
            final = review_result or {"paper_id": paper_id, "phase": "completed"}
            final["phase"] = "completed"
            final["visual_sweep"] = {
                "planned_pages": pages,
                "analyzed_pages": current.get("visual_analyzed_pages") or [],
                "warning": f"{type(exc).__name__}: {exc}",
            }
            self._mark_research_stale(paper_id)
            return final

        analyzed = list(current.get("visual_analyzed_pages") or [])
        analyzed.extend(result.get("processed") or [])
        analyzed.extend(result.get("cached") or [])
        next_index = int(result.get("next_index") or len(pages))
        if next_index >= len(pages):
            final = review_result or {"paper_id": paper_id, "phase": "completed"}
            final["phase"] = "completed"
            final["visual_sweep"] = {
                "planned_pages": pages,
                "analyzed_pages": sorted(set(int(x) for x in analyzed)),
            }
            self._mark_research_stale(paper_id)
            return final
        current.update(
            {
                "phase": "visual_sweep",
                "visual_index": next_index,
                "visual_analyzed_pages": sorted(set(int(x) for x in analyzed)),
                "steps_completed": int(current.get("steps_completed") or 0) + 1,
                "__job_status": "pending",
            }
        )
        return current

    def _review_paper(self, job: dict[str, Any]) -> dict[str, Any]:
        current = dict(job.get("progress") or {})
        phase = str(current.get("phase") or "prepare")
        if phase == "wait_ocr":
            return self._advance_ocr(job, current)
        if phase == "visual_sweep":
            return self._advance_visual_sweep(job, current)

        try:
            result = super()._review_paper(job)
        except ValueError as exc:
            if "pdf contains no extractable text" not in str(exc).lower():
                raise
            if not vision_configured():
                raise ValueError("multimodal OCR provider not configured for scanned PDF") from exc
            paper_id = str((job.get("payload") or {}).get("paper_id") or "")
            return {
                "__job_status": "pending",
                "paper_id": paper_id,
                "phase": "wait_ocr",
                "ocr_next_page": 1,
                "ocr_page_count": 0,
                "ocr_completed_pages": [],
                "steps_completed": int(current.get("steps_completed") or 0),
                "reason": "image_only_pdf_requires_ocr",
            }

        if str(result.get("phase") or "") != "completed":
            return result

        paper_id = str(result.get("paper_id") or (job.get("payload") or {}).get("paper_id") or "")
        user, folder_id = self._context()
        if user is not None and folder_id and paper_id and vision_configured():
            try:
                pages = AutomaticVisualSweep(user, str(folder_id)).plan(paper_id)
            except Exception:
                pages = []
            if pages:
                return {
                    "__job_status": "pending",
                    "paper_id": paper_id,
                    "phase": "visual_sweep",
                    "visual_pages": pages,
                    "visual_index": 0,
                    "visual_analyzed_pages": [],
                    "review_result": result,
                    "steps_completed": int(result.get("steps_completed") or 0),
                }
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
