from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .artifacts import ArtifactRecord, LocalArtifactStore
from .cloud_papers import CloudPaperService
from .graph_service import ScientificGraphService
from .graph_store import ScientificGraphStore
from .memory import ScientificMemory
from .models import AuditEvent
from .persistence import SnapshotStore, hydrate_memory_from_snapshot
from .workspaces import UserWorkspaceStore


SUPPORTED_JOB_TYPES = {
    "discover_literature",
    "review_paper",
    "enqueue_selected_reviews",
    "build_scientific_graph",
    "detect_contradictions",
    "generate_competing_hypotheses",
}


@dataclass
class ScientificJobProcessor:
    memory: ScientificMemory
    provider: object
    snapshot_store: SnapshotStore

    def run(self, job_id: str) -> dict[str, Any]:
        job = self.snapshot_store.get_job(job_id)
        if not job:
            raise KeyError(f"Unknown job: {job_id}")
        if job["job_type"] not in SUPPORTED_JOB_TYPES:
            raise ValueError(f"Unsupported job type: {job['job_type']}")
        if job.get("status") == "completed":
            return job

        self.snapshot_store.update_job(job_id, status="running", last_error=None)
        try:
            if job["job_type"] == "discover_literature":
                progress = self._discover(job)
            elif job["job_type"] == "review_paper":
                progress = self._review_paper(job)
            elif job["job_type"] == "enqueue_selected_reviews":
                progress = self._enqueue_selected_reviews(job)
            elif job["job_type"] == "build_scientific_graph":
                progress = self._build_graph(job)
            elif job["job_type"] == "detect_contradictions":
                progress = self._detect_contradictions(job)
            else:
                progress = self._generate_hypotheses(job)
            self.snapshot_store.update_job(job_id, status="completed", progress=progress)
        except Exception as exc:
            self.snapshot_store.update_job(
                job_id,
                status="failed",
                last_error=f"{type(exc).__name__}: {exc}",
            )
            raise
        return self.snapshot_store.get_job(job_id) or job

    def _state(self, session_id: str):
        return hydrate_memory_from_snapshot(self.memory, self.snapshot_store, session_id)

    def _discover(self, job: dict[str, Any]) -> dict[str, Any]:
        session_id = job["session_id"]
        state = self._state(session_id)
        payload = job.get("payload") or {}
        query = str(payload.get("query") or state.question)
        from_year = int(payload.get("from_year", 1900))
        max_results = min(max(int(payload.get("max_results", 100)), 1), 200)

        service = CloudPaperService(self.memory, self.provider, self.snapshot_store)
        papers = service.discover(query, from_year=from_year, max_results=max_results)
        paper_ids = [paper.canonical_id for paper in papers]
        state.candidate_paper_ids = list(dict.fromkeys(state.candidate_paper_ids + paper_ids))
        state.audit_log.append(AuditEvent(
            event="literature_discovered",
            detail=f"query={query}; papers={len(paper_ids)}",
        ))
        self.memory.save_state(state)
        self.snapshot_store.save_state(state, project_id=state.project_id)

        store = LocalArtifactStore(self.memory)
        revision = store.next_revision(session_id, "literature_discovery_batch")
        artifact = ArtifactRecord(
            artifact_id=f"{session_id}:literature_discovery_batch:r{revision}",
            session_id=session_id,
            artifact_type="literature_discovery_batch",
            producer_agent="literature_discovery_job",
            stage="literature",
            payload={
                "query": query,
                "from_year": from_year,
                "paper_ids": paper_ids,
                "metadata_only": True,
            },
            revision=revision,
            accepted=True,
        )
        store.save(artifact)
        self.snapshot_store.save_artifact(artifact)
        return {"discovered": len(paper_ids), "paper_ids": paper_ids}

    def _review_paper(self, job: dict[str, Any]) -> dict[str, Any]:
        session_id = job["session_id"]
        state = self._state(session_id)
        payload = job.get("payload") or {}
        paper_id = payload.get("paper_id")
        if not paper_id:
            raise ValueError("review_paper job requires payload.paper_id")

        service = CloudPaperService(self.memory, self.provider, self.snapshot_store)
        result, document = service.review_paper(
            str(paper_id),
            pdf_url=payload.get("pdf_url"),
        )
        if paper_id not in state.selected_paper_ids:
            state.selected_paper_ids.append(str(paper_id))
        state.audit_log.append(AuditEvent(
            event="paper_full_text_reviewed",
            detail=f"paper={paper_id}; pages={document.page_count}",
        ))
        self.memory.save_state(state)
        self.snapshot_store.save_state(state, project_id=state.project_id)
        return {
            "paper_id": paper_id,
            "pages": document.page_count,
            "source_url": document.source_url,
            "gates": [gate.model_dump(mode="json") for gate in result.gate_results],
        }

    def _enqueue_selected_reviews(self, job: dict[str, Any]) -> dict[str, Any]:
        state = self._state(job["session_id"])
        payload = job.get("payload") or {}
        requested = payload.get("paper_ids") or state.selected_paper_ids or state.candidate_paper_ids
        limit = min(max(int(payload.get("limit", 100)), 1), 100)
        paper_ids = list(dict.fromkeys(str(x) for x in requested))[:limit]
        children = [
            self.snapshot_store.create_job(
                state.session_id,
                "review_paper",
                {"paper_id": paper_id},
            )
            for paper_id in paper_ids
        ]
        return {
            "enqueued": len(children),
            "job_ids": [child["job_id"] for child in children],
            "paper_ids": paper_ids,
        }

    def _graph_service(self, job: dict[str, Any]) -> tuple[Any, ScientificGraphService]:
        state = self._state(job["session_id"])
        user = getattr(self.snapshot_store, "user", None)
        folder_id = getattr(self.snapshot_store, "folder_id", None) or state.folder_id
        if user is None or not folder_id:
            raise RuntimeError("Scientific graph jobs require an authenticated user and folder-scoped snapshot store")
        graph_store = ScientificGraphStore(user, folder_id=folder_id)
        workspace = UserWorkspaceStore(user)
        service = ScientificGraphService(
            snapshot_store=self.snapshot_store,
            workspace_store=workspace,
            graph_store=graph_store,
            provider=self.provider,
        )
        return state, service

    def _build_graph(self, job: dict[str, Any]) -> dict[str, Any]:
        state, service = self._graph_service(job)
        payload = job.get("payload") or {}
        result = service.build(full_text_only=bool(payload.get("full_text_only", True)))
        state.audit_log.append(AuditEvent(
            event="scientific_graph_built",
            detail=f"nodes={len(result.nodes)}; edges={len(result.edges)}; papers={result.paper_count}",
        ))
        self.memory.save_state(state)
        self.snapshot_store.save_state(state, project_id=state.project_id)
        return {
            "papers": result.paper_count,
            "claims": result.claim_count,
            "evidence": result.evidence_count,
            "nodes": len(result.nodes),
            "edges": len(result.edges),
        }

    def _detect_contradictions(self, job: dict[str, Any]) -> dict[str, Any]:
        state, service = self._graph_service(job)
        payload = job.get("payload") or {}
        rows = service.detect_contradictions(context=str(payload.get("context") or ""))
        state.audit_log.append(AuditEvent(
            event="contradictions_analyzed",
            detail=f"candidates={len(rows)}",
        ))
        self.memory.save_state(state)
        self.snapshot_store.save_state(state, project_id=state.project_id)
        return {
            "contradictions": len(rows),
            "candidate_ids": [row.contradiction_id for row in rows],
        }

    def _generate_hypotheses(self, job: dict[str, Any]) -> dict[str, Any]:
        state, service = self._graph_service(job)
        payload = job.get("payload") or {}
        question = str(payload.get("question") or state.question)
        competition = service.generate_hypotheses(question)
        state.audit_log.append(AuditEvent(
            event="competing_hypotheses_generated",
            detail=f"competition={competition.competition_id}; hypotheses={len(competition.hypotheses)}",
        ))
        self.memory.save_state(state)
        self.snapshot_store.save_state(state, project_id=state.project_id)
        return {
            "competition_id": competition.competition_id,
            "hypotheses": len(competition.hypotheses),
            "decision_needed": competition.decision_needed,
        }
