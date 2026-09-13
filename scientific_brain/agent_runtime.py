from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from .artifacts import ArtifactRecord, LocalArtifactStore
from .reflective import ReflectiveAgentRunner
from .registry import agent_for_id


class AgentPayload(BaseModel):
    outputs: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)


class AgentExecution(BaseModel):
    role_id: str
    stage: str
    task: str
    context_hash: str
    payload: AgentPayload
    self_critique: str
    independent_review: str
    review_passed: bool


@dataclass
class ConfiguredScientificAgent:
    role_id: str
    provider: object
    independent_provider: object | None = None

    def _spec(self) -> dict[str, Any]:
        return agent_for_id(self.role_id)

    def run(self, context: dict[str, Any]) -> AgentExecution:
        spec = self._spec()
        context_json = json.dumps(context, ensure_ascii=False, default=str, sort_keys=True)
        context_hash = hashlib.sha256(context_json.encode("utf-8")).hexdigest()
        output_contract = {
            "outputs": {name: "<content>" for name in spec["outputs"]},
            "evidence_ids": [],
            "unresolved_issues": [],
            "assumptions": [],
            "blocking_issues": [],
        }
        system = (
            f"You are the ScientificBrain agent '{spec['id']}'.\n"
            f"PRIMARY RESPONSIBILITY: {spec['purpose']}\n"
            f"REQUIRED CHECKS: {', '.join(spec['required_checks'])}\n"
            "Use only the supplied structured research context. Preserve uncertainty and provenance. "
            "Do not silently fill missing information. Distinguish measured, derived, inferred, hypothetical "
            "and speculative content. Return ONLY valid JSON matching the requested output contract."
        )
        user = (
            f"STAGE: {spec['stage']}\n"
            f"EXPECTED INPUTS: {json.dumps(spec['inputs'])}\n"
            f"OUTPUT CONTRACT: {json.dumps(output_contract, ensure_ascii=False)}\n\n"
            f"RESEARCH CONTEXT:\n{context_json}"
        )
        runner = ReflectiveAgentRunner(self.provider, self.independent_provider)
        result = runner.run(self.role_id, system, user)
        try:
            payload = AgentPayload.model_validate_json(_extract_json(result.revised))
        except Exception as exc:
            payload = AgentPayload(
                outputs={"raw_output": result.revised},
                unresolved_issues=[f"Structured-output parse failed: {type(exc).__name__}"],
                blocking_issues=["Agent output did not satisfy the JSON contract"],
            )
        return AgentExecution(
            role_id=self.role_id,
            stage=spec["stage"],
            task=spec["task"],
            context_hash=context_hash,
            payload=payload,
            self_critique=result.self_critique,
            independent_review=result.independent_review,
            review_passed=result.review_passed and not payload.blocking_issues,
        )

    def persist(self, session_id: str, execution: AgentExecution, store: LocalArtifactStore) -> list[ArtifactRecord]:
        records: list[ArtifactRecord] = []
        for artifact_type, payload in execution.payload.outputs.items():
            revision = store.next_revision(session_id, artifact_type)
            record = ArtifactRecord(
                artifact_id=f"{session_id}:{artifact_type}:r{revision}",
                session_id=session_id,
                artifact_type=artifact_type,
                producer_agent=execution.role_id,
                stage=execution.stage,
                payload=payload,
                evidence_ids=execution.payload.evidence_ids,
                revision=revision,
                accepted=execution.review_passed,
            )
            store.save(record)
            records.append(record)
        return records


def _extract_json(text: str) -> str:
    raw = text.strip()
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{") and cleaned.endswith("}"):
                return cleaned
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found")
    return raw[start:end + 1]
