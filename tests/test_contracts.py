import pytest

from scientific_brain.research_contracts import (
    DiagnosticSpec,
    ExperimentDesignSpec,
    HypothesisSpec,
    ObjectiveSpec,
    ResearchProjectDefinition,
    ResearchQuestionSpec,
    ScopeSpec,
    VariableRole,
    VariableSpec,
    definition_gate,
)


def _project():
    return ResearchProjectDefinition(
        project_id="p1",
        title="Defined experimental plasma project",
        discipline="plasma physics",
        methodologies=["experimental"],
        question=ResearchQuestionSpec(
            statement="How does electrode spacing alter the measured plasma impulse?",
            scientific_gap="The mechanism connecting geometry and measured impulse is unresolved.",
            rationale="A discriminating experiment can separate timing and plume explanations.",
            domain_of_validity=["pulsed plasma discharge"],
        ),
        objectives=[ObjectiveSpec(
            objective_id="o1",
            statement="Quantify the relationship between spacing and impulse.",
            hypothesis_ids=["h1"],
            observables=["spacing", "impulse"],
            expected_output="response curve",
            success_criterion="uncertainty-bounded relationship",
        )],
        variables=[
            VariableSpec(
                variable_id="spacing",
                symbol="dz",
                name="electrode spacing",
                role=VariableRole.INDEPENDENT,
                unit="mm",
                operational_definition="controlled axial separation",
                measurement_or_computation="caliper measurement",
                uncertainty_definition="calibration plus repeatability",
            ),
            VariableSpec(
                variable_id="impulse",
                symbol="Ibit",
                name="impulse bit",
                role=VariableRole.DEPENDENT,
                unit="N s",
                operational_definition="integrated calibrated thrust response",
                measurement_or_computation="thrust stand",
                uncertainty_definition="calibration and repeatability propagation",
            ),
        ],
        hypotheses=[HypothesisSpec(
            hypothesis_id="h1",
            statement="Changing electrode spacing changes impulse through discharge timing.",
            mechanism="Geometry changes breakdown and current-sheath timing relative to peak current.",
            falsifiable_prediction="Impulse changes systematically with timing offset as spacing varies.",
            variable_ids=["spacing", "impulse"],
            observables=["timing offset", "impulse"],
            rejection_criterion="Reject if timing offset varies without a corresponding impulse change within uncertainty.",
        )],
        diagnostics=[DiagnosticSpec(
            diagnostic_id="d1",
            name="thrust stand",
            measures=["impulse"],
            physical_principle="calibrated mechanical response",
            calibration="known impulse calibration",
            uncertainty_sources=["noise", "drift"],
        )],
        experiments=[ExperimentDesignSpec(
            experiment_id="e1",
            purpose="Discriminate timing-mediated impulse hypothesis",
            hypothesis_ids=["h1"],
            independent_variables=["spacing"],
            dependent_variables=["impulse"],
            diagnostic_ids=["d1"],
            repetitions=5,
            procedure=["set spacing", "fire pulse", "record response"],
            acceptance_criteria=["calibration valid", "signal above quantification limit"],
        )],
        scope=ScopeSpec(
            in_scope=["thruster characterization"],
            out_of_scope=["spacecraft integration"],
        ),
        required_outputs=["evidence-linked report"],
    )


def test_complete_project_passes_definition_gate():
    result = definition_gate(_project())
    assert result.passed
    assert result.score == 1.0


def test_unknown_variable_reference_is_rejected():
    payload = _project().model_dump()
    payload["hypotheses"][0]["variable_ids"].append("missing")
    with pytest.raises(ValueError):
        ResearchProjectDefinition.model_validate(payload)
