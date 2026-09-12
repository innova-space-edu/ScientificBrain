from __future__ import annotations

from dataclasses import dataclass

from .artifacts import ArtifactRecord, LocalArtifactStore
from .memory import ScientificMemory
from .models import AuditEvent, ResearchStage
from .persistence import SnapshotStore
from .project_store import ProjectDefinitionStore
from .research_contracts import ResearchProjectDefinition, definition_gate
from .workflow import ScientificWorkflow


@dataclass
class DefinedProjectService:
    memory: ScientificMemory
    provider: object
    snapshot_store: SnapshotStore | None = None

    def create_session(
        self,
        project: ResearchProjectDefinition,
        *,
        paper_ids: list[str] | None = None,
        search_query: str | None = None,
        limit: int = 20,
    ):
        gate = definition_gate(project)
        if not gate.passed:
            raise ValueError("Project definition did not pass the research-definition gate")

        ProjectDefinitionStore(self.memory).save(project)
        if self.snapshot_store:
            self.snapshot_store.save_project(project)

        workflow = ScientificWorkflow(self.memory, self.provider)
        state = workflow.start_session(
            project.question.statement,
            paper_ids=paper_ids,
            search_query=search_query,
            limit=limit,
        )
        state.project_id = project.project_id
        state.protocol_stage = "definition"
        state.stage = ResearchStage.DEFINITION
        state.gate_results.append(gate)
        state.audit_log.append(
            AuditEvent(event="project_definition_attached", detail=project.project_id)
        )

        artifact_store = LocalArtifactStore(self.memory)
        project_artifact = ArtifactRecord(
            artifact_id=f"{state.session_id}:project_definition:r1",
            session_id=state.session_id,
            artifact_type="project_definition",
            producer_agent="human_definition",
            stage="definition",
            payload=project.model_dump(mode="json"),
            revision=1,
            accepted=True,
        )
        artifact_store.save(project_artifact)
        if self.snapshot_store:
            self.snapshot_store.save_artifact(project_artifact)

        self.memory.record_gate(gate, session_id=state.session_id)
        self.memory.save_state(state)
        if self.snapshot_store:
            self.snapshot_store.save_state(state, project_id=project.project_id)
        return state
