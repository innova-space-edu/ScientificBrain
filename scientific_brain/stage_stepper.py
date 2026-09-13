from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_runtime import AgentExecution, ConfiguredScientificAgent
from .artifacts import ArtifactRecord, LocalArtifactStore
from .memory import ScientificMemory
from .models import AuditEvent, GateResult, ResearchStage
from .orchestrator import _independent_provider, _task_provider
from .persistence import SnapshotStore
from .project_store import ProjectDefinitionStore
from .protocol_engine import ResearchProtocolEngine, StageDecision
from .registry import agent_for_id, load_agent_registry
from .stage_validation import StageGateFactory


@dataclass
class StageValidationResult:
    session_id: str
    stage: str
    gates: list[GateResult]
    decision: StageDecision
    next_stage: str | None


@dataclass
class StageStepper:
    memory: ScientificMemory
    provider: object
    snapshot_store: SnapshotStore | None = None

    def run_agent(self, session_id: str, role_id: str, extra_context: dict[str, Any] | None = None) -> AgentExecution:
        state = self.memory.load_state(session_id)
        if state is None:
            raise KeyError(f"Unknown session: {session_id}")
        if not state.project_id:
            raise ValueError("Session has no project definition")

        spec = agent_for_id(role_id)
        if spec["stage"] != state.protocol_stage:
            raise ValueError(
                f"Agent {role_id} belongs to stage {spec['stage']}, but current stage is {state.protocol_stage}"
            )
        project = ProjectDefinitionStore(self.memory).load(state.project_id)
        if project is None:
            raise KeyError(f"Missing project: {state.project_id}")

        artifacts = LocalArtifactStore(self.memory)
        context = {
            "project_definition": project.model_dump(mode="json"),
            "research_state": state.model_dump(mode="json"),
            "artifacts": artifacts.context(session_id),
        }
        if extra_context:
            context["external_context"] = extra_context

        primary = _task_provider(self.provider, spec["task"])
        independent = _independent_provider(self.provider, spec["task"])
        agent = ConfiguredScientificAgent(role_id, primary, independent)
        execution = agent.run(context)
        records = agent.persist(session_id, execution, artifacts)
        if self.snapshot_store:
            for record in records:
                self.snapshot_store.save_artifact(record)

        state.audit_log.append(AuditEvent(
            event=f"agent_executed:{role_id}",
            detail=f"stage={state.protocol_stage}; review_passed={execution.review_passed}",
        ))
        self.memory.save_state(state)
        if self.snapshot_store:
            self.snapshot_store.save_state(state, project_id=state.project_id)
        return execution

    def add_external_artifact(
        self,
        session_id: str,
        artifact_type: str,
        payload: Any,
        *,
        stage: str | None = None,
        evidence_ids: list[str] | None = None,
        accepted: bool = True,
        producer: str = "human_or_instrument",
    ) -> ArtifactRecord:
        state = self.memory.load_state(session_id)
        if state is None:
            raise KeyError(f"Unknown session: {session_id}")
        target_stage = stage or state.protocol_stage
        store = LocalArtifactStore(self.memory)
        revision = store.next_revision(session_id, artifact_type)
        record = ArtifactRecord(
            artifact_id=f"{session_id}:{artifact_type}:r{revision}",
            session_id=session_id,
            artifact_type=artifact_type,
            producer_agent=producer,
            stage=target_stage,
            payload=payload,
            evidence_ids=evidence_ids or [],
            revision=revision,
            accepted=accepted,
        )
        store.save(record)
        if self.snapshot_store:
            self.snapshot_store.save_artifact(record)
        return record

    def validate_stage(self, session_id: str) -> StageValidationResult:
        state = self.memory.load_state(session_id)
        if state is None:
            raise KeyError(f"Unknown session: {session_id}")
        if not state.project_id:
            raise ValueError("Session has no project definition")
        project = ProjectDefinitionStore(self.memory).load(state.project_id)
        if project is None:
            raise KeyError(f"Missing project: {state.project_id}")

        stage = state.protocol_stage
        protocol = ResearchProtocolEngine()
        store = LocalArtifactStore(self.memory)
        gates = StageGateFactory(self.memory, store, state, project).for_stage(stage)

        blocking_agents = [
            agent for agent in load_agent_registry()["agents"]
            if agent["stage"] == stage and agent.get("can_block")
        ]
        failed_agents: list[str] = []
        for agent in blocking_agents:
            for output in agent["outputs"]:
                artifact = store.latest(session_id, output)
                if artifact is None or not artifact.accepted:
                    failed_agents.append(agent["id"])
                    break
        agent_gate = GateResult(
            name="agent_independent_review",
            passed=not failed_agents,
            score=(len(blocking_agents) - len(failed_agents)) / len(blocking_agents) if blocking_agents else 1.0,
            blockers=[f"Blocking agent not accepted: {agent_id}" for agent_id in failed_agents],
        )
        gates.append(agent_gate)
        for gate in gates:
            self.memory.record_gate(gate, session_id=session_id)
        state.gate_results.extend(gates)

        decision = protocol.validate_stage(stage, store.context(session_id), gates)
        if failed_agents:
            decision.passed = False
            if "agent_independent_review" not in decision.failed_gates:
                decision.failed_gates.append("agent_independent_review")

        next_stage = protocol.next_stage(stage) if decision.passed else None
        if decision.passed:
            state.blocked_stage = None
            if next_stage is None:
                state.stage = ResearchStage.COMPLETE
                state.audit_log.append(AuditEvent(event="protocol_complete", detail=stage))
            else:
                state.protocol_stage = next_stage
                state.stage = ResearchStage(next_stage)
                state.audit_log.append(AuditEvent(event=f"protocol_stage_passed:{stage}", detail=f"next={next_stage}"))
        else:
            state.blocked_stage = stage
            state.stage = ResearchStage.BLOCKED
            state.audit_log.append(AuditEvent(
                event=f"protocol_stage_blocked:{stage}",
                detail=f"missing={decision.missing_artifacts}; failed={decision.failed_gates}",
            ))

        self.memory.save_state(state)
        if self.snapshot_store:
            self.snapshot_store.save_state(state, project_id=state.project_id)
        return StageValidationResult(
            session_id=session_id,
            stage=stage,
            gates=gates,
            decision=decision,
            next_stage=next_stage,
        )
