from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adaptive import chunk_text, merge_chunk_analyses, plan_corpus, plan_review, profile_document
from .agents import (
    AdversarialAgent,
    CriticAgent,
    ExperimentAgent,
    PaperAgent,
    ReproducibilityAgent,
    SimulationAgent,
    TheoryAgent,
)
from .artifacts import ArtifactRecord, LocalArtifactStore
from .cloud_papers import CloudPaperService
from .gates import run_paper_gates
from .graph_agents import ContradictionAgent
from .graph_models import ContradictionRecord, GraphNodeType
from .graph_service import ScientificGraphService
from .graph_store import ScientificGraphStore
from .memory import ScientificMemory
from .models import AuditEvent, Critique, PaperAnalysis, PaperKind, SpecialistReview
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


def _for_task(provider: object, task: str) -> object:
    selector = getattr(provider, "for_task", None)
    if callable(selector):
        return selector(task)
    return provider


def _specialist_agents(provider: object, kind: PaperKind) -> list[object]:
    research_provider = _for_task(provider, "research")
    agents: list[object] = []
    if kind == PaperKind.EXPERIMENTAL:
        agents.extend([ExperimentAgent(research_provider), TheoryAgent(research_provider)])
    elif kind == PaperKind.THEORETICAL:
        agents.append(TheoryAgent(research_provider))
    elif kind == PaperKind.SIMULATION:
        agents.extend([SimulationAgent(research_provider), TheoryAgent(research_provider)])
    elif kind == PaperKind.HYBRID:
        agents.extend([
            TheoryAgent(research_provider),
            ExperimentAgent(research_provider),
            SimulationAgent(research_provider),
        ])
    agents.extend([AdversarialAgent(research_provider), ReproducibilityAgent(research_provider)])
    return agents


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

            next_status = str(progress.pop("__job_status", "completed"))
            if next_status not in {"pending", "completed"}:
                raise ValueError(f"Invalid resumable job status: {next_status}")
            self.snapshot_store.update_job(job_id, status=next_status, progress=progress)
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
        session_id = job.get("session_id")
        if not session_id:
            raise ValueError("discover_literature requires a research session")
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
        """Advance exactly one resumable paper-review step."""

        session_id = job.get("session_id")
        payload = job.get("payload") or {}
        paper_id = str(payload.get("paper_id") or "").strip()
        if not paper_id:
            raise ValueError("review_paper job requires payload.paper_id")

        current = dict(job.get("progress") or {})
        phase = str(current.get("phase") or "prepare")
        service = CloudPaperService(self.memory, self.provider, self.snapshot_store)

        if phase == "prepare":
            _, document = service.load_document(paper_id, pdf_url=payload.get("pdf_url"))
            profile = profile_document(page.text for page in document.pages)
            plan = plan_review(profile)
            return {
                "__job_status": "pending",
                "paper_id": paper_id,
                "phase": "extract",
                "review_mode": plan.mode,
                "pages_per_chunk": plan.pages_per_chunk,
                "chunk_ranges": [list(x) for x in plan.chunk_ranges],
                "chunk_index": 0,
                "chunk_analyses": [],
                "page_count": profile.page_count,
                "word_count": profile.word_count,
                "estimated_tokens": profile.estimated_tokens,
                "source_url": document.source_url,
                "rationale": plan.rationale,
                "steps_completed": 0,
            }

        if phase == "extract":
            ranges = current.get("chunk_ranges") or []
            index = int(current.get("chunk_index") or 0)
            if index >= len(ranges):
                current["phase"] = "consolidate"
                current["__job_status"] = "pending"
                return current

            paper, document = service.load_document(paper_id, pdf_url=payload.get("pdf_url"))
            start_page, end_page = [int(x) for x in ranges[index]]
            text = chunk_text(document, start_page, end_page)
            analysis = PaperAgent(_for_task(self.provider, "structured")).analyze_structured(paper, text)
            analyses = list(current.get("chunk_analyses") or [])
            analyses.append(analysis.model_dump(mode="json"))
            current.update({
                "chunk_analyses": analyses,
                "chunk_index": index + 1,
                "current_pages": [start_page, end_page],
                "steps_completed": int(current.get("steps_completed") or 0) + 1,
            })
            current["phase"] = "consolidate" if index + 1 >= len(ranges) else "extract"
            current["__job_status"] = "pending"
            return current

        if phase == "consolidate":
            paper = service.load_cloud_paper(paper_id)
            analyses = [PaperAnalysis.model_validate(x) for x in (current.get("chunk_analyses") or [])]
            merged = merge_chunk_analyses(paper_id, analyses)
            if paper.kind == PaperKind.UNKNOWN and merged.inferred_kind != PaperKind.UNKNOWN:
                paper.kind = merged.inferred_kind
            self.memory.upsert_paper(paper)
            self.memory.save_analysis(merged)
            current.pop("chunk_analyses", None)
            current.update({
                "analysis": merged.model_dump(mode="json"),
                "paper_kind": paper.kind.value,
                "phase": "critique",
                "steps_completed": int(current.get("steps_completed") or 0) + 1,
                "__job_status": "pending",
            })
            return current

        analysis = PaperAnalysis.model_validate(current.get("analysis") or {})
        paper = service.load_cloud_paper(paper_id)
        if paper.kind == PaperKind.UNKNOWN and analysis.inferred_kind != PaperKind.UNKNOWN:
            paper.kind = analysis.inferred_kind

        if phase == "critique":
            critique = CriticAgent(_for_task(self.provider, "research")).critique_structured(paper, analysis)
            agents = _specialist_agents(self.provider, paper.kind)
            current.update({
                "critique": critique.model_dump(mode="json"),
                "specialist_index": 0,
                "specialist_roles": [getattr(agent, "role", type(agent).__name__) for agent in agents],
                "specialist_reviews": [],
                "phase": "specialists",
                "steps_completed": int(current.get("steps_completed") or 0) + 1,
                "__job_status": "pending",
            })
            return current

        critique = Critique.model_validate(current.get("critique") or {"paper_id": paper_id})

        if phase == "specialists":
            agents = _specialist_agents(self.provider, paper.kind)
            index = int(current.get("specialist_index") or 0)
            reviews = [SpecialistReview.model_validate(x) for x in (current.get("specialist_reviews") or [])]
            if index < len(agents):
                review = agents[index].review(paper, analysis)  # type: ignore[attr-defined]
                reviews.append(review)
                current.update({
                    "specialist_reviews": [x.model_dump(mode="json") for x in reviews],
                    "specialist_index": index + 1,
                    "steps_completed": int(current.get("steps_completed") or 0) + 1,
                })
                current["phase"] = "finalize" if index + 1 >= len(agents) else "specialists"
                current["__job_status"] = "pending"
                return current
            current["phase"] = "finalize"
            current["__job_status"] = "pending"
            return current

        if phase != "finalize":
            raise ValueError(f"Unknown review phase: {phase}")

        reviews = [SpecialistReview.model_validate(x) for x in (current.get("specialist_reviews") or [])]
        gates = run_paper_gates(analysis, paper.kind)
        self.snapshot_store.save_paper_bundle(paper, analysis, critique, reviews)

        if session_id:
            state = self._state(session_id)
            if paper_id not in state.selected_paper_ids:
                state.selected_paper_ids.append(paper_id)
            state.audit_log.append(AuditEvent(
                event="paper_full_text_reviewed",
                detail=(
                    f"paper={paper_id}; pages={current.get('page_count', 0)}; "
                    f"mode={current.get('review_mode', 'unknown')}"
                ),
            ))
            self.memory.save_state(state)
            self.snapshot_store.save_state(state, project_id=state.project_id)

        return {
            "paper_id": paper_id,
            "phase": "completed",
            "review_mode": current.get("review_mode"),
            "page_count": current.get("page_count", 0),
            "word_count": current.get("word_count", 0),
            "estimated_tokens": current.get("estimated_tokens", 0),
            "source_url": current.get("source_url"),
            "steps_completed": int(current.get("steps_completed") or 0) + 1,
            "specialist_roles": current.get("specialist_roles") or [],
            "gates": [gate.model_dump(mode="json") for gate in gates],
        }

    def _enqueue_selected_reviews(self, job: dict[str, Any]) -> dict[str, Any]:
        session_id = job.get("session_id")
        payload = job.get("payload") or {}
        if session_id:
            state = self._state(session_id)
            requested = payload.get("paper_ids") or state.selected_paper_ids or state.candidate_paper_ids
            effective_session = state.session_id
        else:
            requested = payload.get("paper_ids") or []
            effective_session = None
            if not requested:
                raise ValueError("folder-scoped enqueue_selected_reviews requires payload.paper_ids")
        limit = min(max(int(payload.get("limit", 100)), 1), 500)
        paper_ids = list(dict.fromkeys(str(x) for x in requested))[:limit]
        corpus = plan_corpus(len(paper_ids))
        children = [
            self.snapshot_store.create_job(
                effective_session,
                "review_paper",
                {"paper_id": paper_id, "corpus_mode": corpus.mode},
                folder_id=getattr(self.snapshot_store, "folder_id", None),
            )
            for paper_id in paper_ids
        ]
        return {
            "enqueued": len(children),
            "job_ids": [child["job_id"] for child in children],
            "paper_ids": paper_ids,
            "corpus_mode": corpus.mode,
            "dispatch_batch_size": corpus.dispatch_batch_size,
            "synthesis_group_size": corpus.synthesis_group_size,
            "evidence_warning": corpus.evidence_warning,
        }

    def _graph_service(self, job: dict[str, Any]) -> tuple[Any | None, ScientificGraphService]:
        session_id = job.get("session_id")
        state = self._state(session_id) if session_id else None
        user = getattr(self.snapshot_store, "user", None)
        folder_id = getattr(self.snapshot_store, "folder_id", None) or (state.folder_id if state else None)
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
        if state is not None:
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
        current = dict(job.get("progress") or {})
        phase = str(current.get("phase") or "prepare")
        context = str(payload.get("context") or "")

        if phase == "prepare":
            nodes = service.graph_store.list_nodes(limit=10000)
            claims = [n for n in nodes if n.node_type == GraphNodeType.CLAIM]
            papers = [n for n in nodes if n.node_type == GraphNodeType.PAPER]
            if len(claims) < 2:
                service.graph_store.replace_contradictions([])
                return {"phase": "completed", "contradictions": 0, "candidate_ids": []}
            batches = service._topic_claim_groups(claims, papers)
            return {
                "__job_status": "pending",
                "phase": "scan",
                "batch_index": 0,
                "batch_node_ids": [[node.node_id for node in batch] for batch in batches],
                "records": [],
                "batch_count": len(batches),
            }

        if phase == "scan":
            batches = current.get("batch_node_ids") or []
            index = int(current.get("batch_index") or 0)
            if index >= len(batches):
                current["phase"] = "finalize"
                current["__job_status"] = "pending"
                return current

            nodes = service.graph_store.list_nodes(limit=10000)
            node_by_id = {n.node_id: n for n in nodes}
            batch = [node_by_id[node_id] for node_id in batches[index] if node_id in node_by_id]
            detected = ContradictionAgent(_for_task(self.provider, "research")).detect(batch, context=context)
            records = list(current.get("records") or [])
            records.extend(item.model_dump(mode="json") for item in detected)
            current.update({
                "records": records,
                "batch_index": index + 1,
                "phase": "finalize" if index + 1 >= len(batches) else "scan",
                "__job_status": "pending",
            })
            return current

        if phase != "finalize":
            raise ValueError(f"Unknown contradiction phase: {phase}")

        by_pair: dict[tuple[str, str], ContradictionRecord] = {}
        for payload_row in current.get("records") or []:
            item = ContradictionRecord.model_validate(payload_row)
            pair = tuple(sorted((item.claim_a_id, item.claim_b_id)))
            previous = by_pair.get(pair)
            if previous is None or item.confidence > previous.confidence:
                by_pair[pair] = item
        rows = sorted(by_pair.values(), key=lambda x: x.confidence, reverse=True)
        service.graph_store.replace_contradictions(rows)

        if state is not None:
            state.audit_log.append(AuditEvent(
                event="contradictions_analyzed",
                detail=f"candidates={len(rows)}",
            ))
            self.memory.save_state(state)
            self.snapshot_store.save_state(state, project_id=state.project_id)
        return {
            "phase": "completed",
            "contradictions": len(rows),
            "candidate_ids": [row.contradiction_id for row in rows],
            "batches_processed": int(current.get("batch_count") or 0),
        }

    def _generate_hypotheses(self, job: dict[str, Any]) -> dict[str, Any]:
        state, service = self._graph_service(job)
        payload = job.get("payload") or {}
        question = str(payload.get("question") or (state.question if state is not None else "")).strip()
        if not question:
            raise ValueError("generate_competing_hypotheses requires payload.question when no session is attached")
        competition = service.generate_hypotheses(question)
        if state is not None:
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
