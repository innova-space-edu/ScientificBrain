from __future__ import annotations

from dataclasses import dataclass

from .artifacts import LocalArtifactStore
from .gates import run_paper_gates
from .memory import ScientificMemory
from .models import GateResult, ResearchState
from .research_contracts import ResearchProjectDefinition, definition_gate


def _accepted(store: LocalArtifactStore, session_id: str, artifact_type: str) -> bool:
    artifact = store.latest(session_id, artifact_type)
    return bool(artifact and artifact.accepted)


def _presence_gate(name: str, store: LocalArtifactStore, session_id: str, artifacts: list[str]) -> GateResult:
    missing = [artifact for artifact in artifacts if store.latest(session_id, artifact) is None]
    accepted = [artifact for artifact in artifacts if _accepted(store, session_id, artifact)]
    score = len(accepted) / len(artifacts) if artifacts else 1.0
    return GateResult(
        name=name,
        passed=not missing and len(accepted) == len(artifacts),
        score=score,
        blockers=[f"Missing artifact: {artifact}" for artifact in missing],
        warnings=[
            f"Artifact exists but has not passed independent review: {artifact}"
            for artifact in artifacts if artifact not in missing and artifact not in accepted
        ],
        details={"required_artifacts": len(artifacts), "accepted_artifacts": len(accepted)},
    )


@dataclass
class StageGateFactory:
    memory: ScientificMemory
    artifacts: LocalArtifactStore
    state: ResearchState
    project: ResearchProjectDefinition

    def for_stage(self, stage: str) -> list[GateResult]:
        sid = self.state.session_id
        if stage == "definition":
            return [definition_gate(self.project)]
        if stage == "literature":
            return self._literature_gates()
        if stage == "theory":
            return [_presence_gate("theory_consistency", self.artifacts, sid, ["theory_review", "regime_map", "theoretical_predictions"])]
        if stage == "hypothesis":
            project_ok = all(h.falsifiable_prediction and h.rejection_criterion for h in self.project.hypotheses)
            artifact_gate = _presence_gate("falsifiability", self.artifacts, sid, ["competing_hypotheses", "predictions", "rejection_criteria"])
            if not project_ok:
                artifact_gate.passed = False
                artifact_gate.blockers.append("Project hypotheses lack falsifiable prediction or rejection criterion")
            return [artifact_gate]
        if stage == "design":
            return self._design_gates()
        if stage == "execution":
            return [_presence_gate("execution_traceability", self.artifacts, sid, ["raw_data_or_run_outputs", "run_log"])]
        if stage == "analysis":
            return [
                _presence_gate("analysis_reproducibility", self.artifacts, sid, ["processing_log", "processed_data", "statistical_results"]),
                _presence_gate("uncertainty_propagation", self.artifacts, sid, ["uncertainty_propagation"]),
            ]
        if stage == "interpretation":
            return [_presence_gate("claim_evidence_alignment", self.artifacts, sid, ["interpretation", "alternative_explanations"])]
        if stage == "criticism":
            return [_presence_gate("major_concerns_resolved", self.artifacts, sid, ["adversarial_review"])]
        if stage == "reproducibility":
            return [_presence_gate("reproducibility", self.artifacts, sid, ["reproducibility_report"])]
        if stage == "writing":
            return [_presence_gate("writing_traceability", self.artifacts, sid, ["draft"])]
        if stage == "review":
            return [_presence_gate("final_review", self.artifacts, sid, ["review_verdict"])]
        raise KeyError(f"Unknown stage: {stage}")

    def _literature_gates(self) -> list[GateResult]:
        selected = self.state.selected_paper_ids
        if not selected:
            return [
                GateResult(name="corpus_coverage", passed=False, score=0.0, blockers=["No papers selected"]),
                GateResult(name="provenance", passed=False, score=0.0, blockers=["No reviewed evidence"]),
                GateResult(name="evidence", passed=False, score=0.0, blockers=["No reviewed evidence"]),
            ]

        reviewed = 0
        provenance_pass = 0
        evidence_pass = 0
        for paper_id in selected:
            paper = self.memory.get_paper(paper_id)
            analysis = self.memory.get_analysis(paper_id)
            if paper is None or analysis is None:
                continue
            reviewed += 1
            gates = {gate.name: gate for gate in run_paper_gates(analysis, paper.kind)}
            provenance_pass += int(gates["provenance"].passed)
            evidence_pass += int(gates["evidence"].passed)

        coverage_score = reviewed / len(selected)
        provenance_score = provenance_pass / len(selected)
        evidence_score = evidence_pass / len(selected)
        return [
            GateResult(
                name="corpus_coverage",
                passed=reviewed == len(selected) and _accepted(self.artifacts, self.state.session_id, "literature_map"),
                score=coverage_score,
                blockers=[] if reviewed == len(selected) else [f"{len(selected)-reviewed} selected papers lack structured review"],
            ),
            GateResult(
                name="provenance",
                passed=provenance_pass == len(selected),
                score=provenance_score,
                blockers=[] if provenance_pass == len(selected) else ["One or more selected papers failed provenance gate"],
            ),
            GateResult(
                name="evidence",
                passed=evidence_pass == len(selected),
                score=evidence_score,
                blockers=[] if evidence_pass == len(selected) else ["One or more selected papers failed evidence gate"],
            ),
        ]

    def _design_gates(self) -> list[GateResult]:
        sid = self.state.session_id
        experimental = "experimental" in self.project.methodologies
        simulation = "simulation" in self.project.methodologies

        design_required = []
        if experimental:
            design_required.extend(["experiment_design", "diagnostic_plan", "uncertainty_budget"])
        if simulation:
            design_required.append("simulation_plan")
        if not design_required:
            design_required = ["uncertainty_budget"] if self.project.uncertainties else []

        design = _presence_gate("design_completeness", self.artifacts, sid, design_required)
        metrology = (
            _presence_gate("metrology", self.artifacts, sid, ["diagnostic_plan", "uncertainty_budget"])
            if experimental
            else GateResult(name="metrology", passed=True, score=1.0, details={"not_applicable": True})
        )
        numerical = (
            _presence_gate("numerical_validation", self.artifacts, sid, ["simulation_plan", "convergence_plan", "validation_plan"])
            if simulation
            else GateResult(name="numerical_validation", passed=True, score=1.0, details={"not_applicable": True})
        )
        return [design, metrology, numerical]
