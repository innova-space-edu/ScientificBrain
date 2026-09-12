from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_runtime import ConfiguredScientificAgent
from .artifacts import ArtifactRecord, LocalArtifactStore
from .memory import ScientificMemory
from .models import AuditEvent, GateResult, ResearchStage
from .persistence import SnapshotStore
from .project_store import ProjectDefinitionStore
from .protocol_engine import ResearchProtocolEngine, StageDecision
from .providers import RoutedProvider
from .registry import load_agent_registry
from .stage_validation import StageGateFactory


def _task_provider(provider: object, task: str) -> object:
    selector = getattr(provider, "for_task", None)
    return selector(task) if callable(selector) else provider


def _independent_provider(provider: object, task: str) -> object:
    routed = _task_provider(provider, task)
    providers = getattr(routed, "providers", None)
    if isinstance(providers, list) and len(providers) > 1:
        return RoutedProvider(providers=providers[1:] + providers[:1], task=task)
    return routed


@dataclass
class StageRunResult:
    session_id: str
    stage: str
    agent_results: list[dict[str, Any]]
    gate_results: list[GateResult]
    decision: StageDecision
    next_stage: str | None


@dataclass
class ScientificOrchestrator:
    memory: ScientificMemory
    provider: object
    snapshot_store: SnapshotStore | None = None

    def _agents_for_stage(self, stage: str) -> list[dict[str, Any]]:
        registry = load_agent_registry()
        return [agent for agent in registry["agents"] if agent["stage"] == stage]

    def add_external_artifact(
        self,
        session_id: str,
        stage: str,
        artifact_type: str,
        payload: Any,
        *,
        evidence_ids: list[str] | None = None,
        accepted: bool = True,
        producer: str = "human_or_instrument",
    ) -> ArtifactRecord:
        store = LocalArtifactStore(self.memory)
        revision = store.next_revision(session_id, artifact_type)
        record = ArtifactRecord(
            artifact_id=f"{session_id}:{artifact_type}:r{revision}",
            session_id=session_id,
            artifact_type=artifact_type,
            producer_agent=producer,
            stage=stage,
            payload=payload,
            evidence_ids=evidence_ids or [],
            revision=revision,
            accepted=accepted,
        )
        store.save(record)
        return record

    def run_stage(
        self,
        session_id: str,
        stage: str | None = None,
        *,
        extra_context: dict[str, Any] | None = None,
    ) -> StageRunResult:
        state = self.memory.load_state(session_id)
        if state is None:
            raise KeyError(f"Unknown research session: {session_id}")
        if not state.project_id:
            raise ValueError("Session is not attached to a strict ResearchProjectDefinition")

        project = ProjectDefinitionStore(self.memory).load(state.project_id)
        if project is None:
            raise KeyError(f"Missing project definition: {state.project_id}")

        protocol = ResearchProtocolEngine()
        current_stage = stage or state.protocol_stage
        if current_stage not in protocol.stage_ids():
            raise KeyError(f"Unknown protocol stage: {current_stage}")

        artifact_store = LocalArtifactStore(self.memory)
        context = {
            "project_definition": project.model_dump(mode="json"),
            "research_state": state.model_dump(mode="json"),
            "artifacts": artifact_store.context(session_id),
        }
        if extra_context:
            context["external_context"] = extra_context

        executions = []
        hard_agent_failure = False
        for spec in self._agents_for_stage(current_stage):
            primary = _task_provider(self.provider, spec["task"])
            independent = _independent_provider(self.provider, spec["task"])
            agent = ConfiguredScientificAgent(spec["id"], primary, independent)
            execution = agent.run(context)
            agent.persist(session_id, execution, artifact_store)
            executions.append(execution.model_dump(mode="json"))
            if spec.get("can_block") and not execution.review_passed:
                hard_agent_failure = True

            # Every downstream agent sees accepted outputs from earlier agents in the same stage.
            context["artifacts"] = artifact_store.context(session_id)

        gate_factory = StageGateFactory(self.memory, artifact_store, state, project)
        gate_results = gate_factory.for_stage(current_stage)
        if hard_agent_failure:
            gate_results.append(GateResult(
                name="agent_independent_review",
                passed=False,
                score=0.0,
                blockers=["At least one blocking agent failed independent review"],
            ))
        else:
            gate_results.append(GateResult(
                name="agent_independent_review",
                passed=True,
                score=1.0,
            ))

        # Protocol gates are evaluated independently from the generic agent-review gate.
        for gate in gate_results:
            self.memory.record_gate(gate, session_id=session_id)
        state.gate_results.extend(gate_results)

        artifacts = artifact_store.context(session_id)
        decision = protocol.validate_stage(current_stage, artifacts, gate_results)
        next_stage = protocol.next_stage(current_stage) if decision.passed else None

        if decision.passed:
            state.blocked_stage = None
            if next_stage is None:
                state.protocol_stage = "review"
                state.stage = ResearchStage.COMPLETE
                state.audit_log.append(AuditEvent(event="protocol_complete", detail=current_stage))
            else:
                state.protocol_stage = next_stage
                state.stage = ResearchStage(next_stage)
                state.audit_log.append(AuditEvent(
                    event=f"protocol_stage_passed:{current_stage}",
                    detail=f"next={next_stage}",
                ))
        else:
            state.blocked_stage = current_stage
            state.stage = ResearchStage.BLOCKED
            state.audit_log.append(AuditEvent(
                event=f"protocol_stage_blocked:{current_stage}",
                detail=(
                    f"missing_artifacts={decision.missing_artifacts}; "
                    f"failed_gates={decision.failed_gates}"
                ),
            ))

        self.memory.save_state(state)
        if self.snapshot_store:
            self.snapshot_store.save_state(state, project_id=project.project_id)

        return StageRunResult(
            session_id=session_id,
            stage=current_stage,
            agent_results=executions,
            gate_results=gate_results,
            decision=decision,
            next_stage=next_stage,
        )
