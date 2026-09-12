from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import GateResult
from .registry import load_research_protocol


@dataclass
class StageDecision:
    stage: str
    passed: bool
    missing_artifacts: list[str]
    failed_gates: list[str]
    completion_rule: str


class ResearchProtocolEngine:
    def __init__(self, protocol: dict[str, Any] | None = None) -> None:
        self.protocol = protocol or load_research_protocol()
        self.stages = {stage["id"]: stage for stage in self.protocol["stages"]}

    def stage_ids(self) -> list[str]:
        return [stage["id"] for stage in self.protocol["stages"]]

    def validate_stage(
        self,
        stage_id: str,
        artifacts: dict[str, Any],
        gate_results: list[GateResult],
    ) -> StageDecision:
        if stage_id not in self.stages:
            raise KeyError(f"Unknown protocol stage: {stage_id}")
        spec = self.stages[stage_id]
        missing = [
            name for name in spec.get("required_artifacts", [])
            if name not in artifacts or artifacts[name] in (None, "", [], {})
        ]
        by_name = {gate.name: gate for gate in gate_results}
        failed = []
        for gate_name in spec.get("gates", []):
            gate = by_name.get(gate_name)
            if gate is None or not gate.passed:
                failed.append(gate_name)
        return StageDecision(
            stage=stage_id,
            passed=not missing and not failed,
            missing_artifacts=missing,
            failed_gates=failed,
            completion_rule=spec["completion"],
        )

    def next_stage(self, current_stage: str) -> str | None:
        ordered = self.stage_ids()
        if current_stage not in ordered:
            raise KeyError(f"Unknown protocol stage: {current_stage}")
        index = ordered.index(current_stage)
        return ordered[index + 1] if index + 1 < len(ordered) else None

    def route_revision(self, category: str) -> str:
        routing = self.protocol.get("revision_routing", {})
        return routing.get(category, "definition")
