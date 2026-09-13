from scientific_brain.memory import ScientificMemory
from scientific_brain.project_store import ProjectDefinitionStore
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
)


def _project():
    return ResearchProjectDefinition(
        project_id="project:test",
        title="Strictly defined plasma experiment",
        discipline="plasma physics",
        methodologies=["experimental"],
        question=ResearchQuestionSpec(
            statement="Does controlled spacing alter the measured discharge response?",
            scientific_gap="The causal pathway between geometry and response is unresolved.",
            rationale="Controlled variation can discriminate between competing mechanisms.",
        ),
        objectives=[ObjectiveSpec(
            objective_id="o1",
            statement="Measure the geometry-response relationship with bounded uncertainty.",
            hypothesis_ids=["h1"],
            observables=["x", "y"],
            expected_output="response map",
            success_criterion="uncertainty-bounded estimate",
        )],
        variables=[
            VariableSpec(
                variable_id="x", symbol="x", name="spacing", role=VariableRole.INDEPENDENT,
                operational_definition="controlled spacing",
                measurement_or_computation="direct dimensional measurement",
                uncertainty_definition="instrument calibration and repeatability",
            ),
            VariableSpec(
                variable_id="y", symbol="y", name="response", role=VariableRole.DEPENDENT,
                operational_definition="calibrated response",
                measurement_or_computation="diagnostic d1",
                uncertainty_definition="calibration and propagation",
            ),
        ],
        hypotheses=[HypothesisSpec(
            hypothesis_id="h1",
            statement="Changing spacing changes the measured discharge response.",
            mechanism="Geometry changes the discharge evolution and therefore the response.",
            falsifiable_prediction="A reproducible response change appears as spacing is varied.",
            variable_ids=["x", "y"],
            observables=["x", "y"],
            rejection_criterion="Reject if response is invariant within propagated uncertainty.",
        )],
        diagnostics=[DiagnosticSpec(
            diagnostic_id="d1", name="diagnostic", measures=["y"],
            physical_principle="calibrated transduction",
            calibration="traceable calibration",
        )],
        experiments=[ExperimentDesignSpec(
            experiment_id="e1", purpose="test h1", hypothesis_ids=["h1"],
            independent_variables=["x"], dependent_variables=["y"], diagnostic_ids=["d1"],
            repetitions=3, procedure=["set x", "measure y"], acceptance_criteria=["valid calibration"],
        )],
        scope=ScopeSpec(in_scope=["characterization"], out_of_scope=["spacecraft integration"]),
        required_outputs=["research report"],
    )


def test_project_definition_roundtrip(tmp_path):
    memory = ScientificMemory(tmp_path / "brain.db")
    store = ProjectDefinitionStore(memory)
    project = _project()
    store.save(project)
    loaded = store.load(project.project_id)
    assert loaded is not None
    assert loaded.project_id == project.project_id
    assert loaded.hypotheses[0].rejection_criterion
    memory.close()
