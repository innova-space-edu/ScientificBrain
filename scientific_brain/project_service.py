from __future__ import annotations

from dataclasses import dataclass

from .memory import ScientificMemory
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
        state.gate_results.append(gate)
        state.audit_log.append(
            state.audit_log[0].model_copy(
                update={
                    "event": "project_definition_attached",
                    "detail": project.project_id,
                }
            )
        )
        self.memory.record_gate(gate, session_id=state.session_id)
        self.memory.save_state(state)
        if self.snapshot_store:
            self.snapshot_store.save_state(state, project_id=project.project_id)
        return state
