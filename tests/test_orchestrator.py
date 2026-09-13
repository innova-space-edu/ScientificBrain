from scientific_brain.memory import ScientificMemory
from scientific_brain.orchestrator import ScientificOrchestrator
from scientific_brain.project_service import DefinedProjectService
from scientific_brain.research_contracts import (
    HypothesisSpec,
    ObjectiveSpec,
    ResearchProjectDefinition,
    ResearchQuestionSpec,
    ScopeSpec,
    TheoryModelSpec,
    VariableRole,
    VariableSpec,
)


class FakeProvider:
    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, system, user):
        return self.replies.pop(0)


def _project():
    return ResearchProjectDefinition(
        project_id="p:theory",
        title="Defined plasma theory project",
        discipline="plasma physics",
        methodologies=["theoretical"],
        question=ResearchQuestionSpec(
            statement="Which model term controls the transition between two plasma regimes?",
            scientific_gap="The dominant term in the transition regime remains unresolved.",
            rationale="Explicit asymptotic comparison can identify discriminating observables.",
        ),
        objectives=[ObjectiveSpec(
            objective_id="o1",
            statement="Determine which term controls the transition regime.",
            hypothesis_ids=["h1"],
            observables=["ratio"],
            expected_output="regime criterion",
            success_criterion="dimensionless criterion with stated domain",
        )],
        variables=[VariableSpec(
            variable_id="ratio",
            symbol="R",
            name="term ratio",
            role=VariableRole.DERIVED,
            operational_definition="ratio of competing model terms",
            measurement_or_computation="derive from governing equations",
            uncertainty_definition="propagate parameter uncertainty",
        )],
        hypotheses=[HypothesisSpec(
            hypothesis_id="h1",
            statement="The transition occurs when the competing term ratio approaches unity.",
            mechanism="The second term becomes dynamically comparable to the baseline term.",
            falsifiable_prediction="Regime change coincides with the ratio approaching order unity.",
            variable_ids=["ratio"],
            observables=["ratio"],
            rejection_criterion="Reject if transition occurs while the ratio remains asymptotically small.",
        )],
        theory_models=[TheoryModelSpec(
            model_id="m1",
            purpose="compare competing terms",
            governing_equations=["A + B = 0"],
            domain_of_validity=["specified plasma regime"],
        )],
        scope=ScopeSpec(in_scope=["theoretical comparison"], out_of_scope=["hardware qualification"]),
        required_outputs=["evidence-linked theory report"],
    )


def test_definition_stage_advances_only_after_review(tmp_path):
    memory = ScientificMemory(tmp_path / "brain.db")
    provider = FakeProvider([
        '{"outputs":{"validated_scope":{"ok":true},"work_plan":[],"decision_log":[]},"evidence_ids":[],"unresolved_issues":[],"assumptions":[],"blocking_issues":[]}',
        "No material defects.",
        '{"outputs":{"validated_scope":{"ok":true},"work_plan":[],"decision_log":[]},"evidence_ids":[],"unresolved_issues":[],"assumptions":[],"blocking_issues":[]}',
        "PASS",
    ])
    state = DefinedProjectService(memory, provider).create_session(_project(), paper_ids=[])
    result = ScientificOrchestrator(memory, provider).run_stage(state.session_id, "definition")
    assert result.decision.passed
    assert result.next_stage == "literature"
    loaded = memory.load_state(state.session_id)
    assert loaded.protocol_stage == "literature"
    memory.close()
