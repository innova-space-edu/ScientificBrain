from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import GateResult


class EpistemicStatus(StrEnum):
    OBSERVED = "observed"
    MEASURED = "measured"
    DERIVED = "derived"
    INFERRED = "inferred"
    SUPPORTED = "supported"
    HYPOTHESIS = "hypothesis"
    SPECULATIVE = "speculative"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class VariableRole(StrEnum):
    INDEPENDENT = "independent"
    DEPENDENT = "dependent"
    CONTROL = "control"
    CONFOUNDING = "confounding"
    LATENT = "latent"
    DERIVED = "derived"


class ResearchQuestionSpec(BaseModel):
    statement: str = Field(min_length=10)
    scientific_gap: str = Field(min_length=10)
    rationale: str = Field(min_length=10)
    domain_of_validity: list[str] = Field(default_factory=list)


class ObjectiveSpec(BaseModel):
    objective_id: str
    statement: str = Field(min_length=10)
    hypothesis_ids: list[str] = Field(default_factory=list)
    observables: list[str] = Field(default_factory=list)
    expected_output: str = Field(min_length=3)
    success_criterion: str = Field(min_length=3)


class VariableSpec(BaseModel):
    variable_id: str
    symbol: str
    name: str
    role: VariableRole
    unit: str | None = None
    operational_definition: str = Field(min_length=3)
    measurement_or_computation: str = Field(min_length=3)
    uncertainty_definition: str = Field(min_length=3)


class HypothesisSpec(BaseModel):
    hypothesis_id: str
    statement: str = Field(min_length=10)
    mechanism: str = Field(min_length=10)
    falsifiable_prediction: str = Field(min_length=10)
    variable_ids: list[str] = Field(min_length=1)
    observables: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    rejection_criterion: str = Field(min_length=10)
    status: Literal["candidate", "supported", "contested", "rejected"] = "candidate"


class TheoryModelSpec(BaseModel):
    model_id: str
    purpose: str
    governing_equations: list[str] = Field(min_length=1)
    closures: list[str] = Field(default_factory=list)
    approximations: list[str] = Field(default_factory=list)
    ordering_assumptions: list[str] = Field(default_factory=list)
    conserved_quantities: list[str] = Field(default_factory=list)
    domain_of_validity: list[str] = Field(default_factory=list)
    limiting_cases: list[str] = Field(default_factory=list)


class DiagnosticSpec(BaseModel):
    diagnostic_id: str
    name: str
    measures: list[str] = Field(min_length=1)
    physical_principle: str = Field(min_length=3)
    calibration: str = Field(min_length=3)
    temporal_resolution: str | None = None
    spatial_resolution: str | None = None
    bandwidth: str | None = None
    uncertainty_sources: list[str] = Field(default_factory=list)
    perturbation_or_bias: list[str] = Field(default_factory=list)
    detection_or_quantification_limit: str | None = None


class ExperimentDesignSpec(BaseModel):
    experiment_id: str
    purpose: str
    hypothesis_ids: list[str] = Field(min_length=1)
    independent_variables: list[str] = Field(default_factory=list)
    dependent_variables: list[str] = Field(min_length=1)
    control_variables: list[str] = Field(default_factory=list)
    diagnostic_ids: list[str] = Field(min_length=1)
    repetitions: int = Field(ge=1)
    procedure: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    failure_modes: list[str] = Field(default_factory=list)
    safety_or_hardware_constraints: list[str] = Field(default_factory=list)


class SimulationDesignSpec(BaseModel):
    simulation_id: str
    purpose: str
    hypothesis_ids: list[str] = Field(min_length=1)
    model_type: str
    equations_or_model: list[str] = Field(min_length=1)
    solver: str = Field(min_length=2)
    dimensionality: str
    spatial_resolution: str
    time_step_or_integrator: str
    initial_conditions: list[str] = Field(min_length=1)
    boundary_conditions: list[str] = Field(min_length=1)
    convergence_tests: list[str] = Field(min_length=1)
    numerical_error_checks: list[str] = Field(min_length=1)
    validation_reference: list[str] = Field(default_factory=list)
    required_outputs: list[str] = Field(min_length=1)


class UncertaintySpec(BaseModel):
    uncertainty_id: str
    quantity: str
    source: str
    category: Literal["random", "systematic", "model", "numerical", "calibration", "other"]
    estimate: str
    propagation_method: str
    mitigation: str | None = None


class ScopeSpec(BaseModel):
    in_scope: list[str] = Field(min_length=1)
    out_of_scope: list[str] = Field(min_length=1)
    external_dependencies: list[str] = Field(default_factory=list)


class ResearchProjectDefinition(BaseModel):
    project_id: str
    title: str = Field(min_length=5)
    discipline: str = Field(min_length=3)
    methodologies: list[Literal["experimental", "theoretical", "simulation", "data_analysis"]] = Field(min_length=1)
    question: ResearchQuestionSpec
    objectives: list[ObjectiveSpec] = Field(min_length=1)
    variables: list[VariableSpec] = Field(min_length=1)
    hypotheses: list[HypothesisSpec] = Field(min_length=1)
    theory_models: list[TheoryModelSpec] = Field(default_factory=list)
    diagnostics: list[DiagnosticSpec] = Field(default_factory=list)
    experiments: list[ExperimentDesignSpec] = Field(default_factory=list)
    simulations: list[SimulationDesignSpec] = Field(default_factory=list)
    uncertainties: list[UncertaintySpec] = Field(default_factory=list)
    scope: ScopeSpec
    required_outputs: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self):
        variable_ids = {v.variable_id for v in self.variables}
        hypothesis_ids = {h.hypothesis_id for h in self.hypotheses}
        diagnostic_ids = {d.diagnostic_id for d in self.diagnostics}

        if len(variable_ids) != len(self.variables):
            raise ValueError("Duplicate variable_id values are not allowed")
        if len(hypothesis_ids) != len(self.hypotheses):
            raise ValueError("Duplicate hypothesis_id values are not allowed")

        for hypothesis in self.hypotheses:
            unknown = set(hypothesis.variable_ids) - variable_ids
            if unknown:
                raise ValueError(f"{hypothesis.hypothesis_id} references unknown variables: {sorted(unknown)}")

        for objective in self.objectives:
            unknown = set(objective.hypothesis_ids) - hypothesis_ids
            if unknown:
                raise ValueError(f"{objective.objective_id} references unknown hypotheses: {sorted(unknown)}")
            if not objective.observables:
                raise ValueError(f"{objective.objective_id} must define at least one observable")

        for experiment in self.experiments:
            unknown_h = set(experiment.hypothesis_ids) - hypothesis_ids
            unknown_d = set(experiment.diagnostic_ids) - diagnostic_ids
            unknown_v = (
                set(experiment.independent_variables)
                | set(experiment.dependent_variables)
                | set(experiment.control_variables)
            ) - variable_ids
            if unknown_h:
                raise ValueError(f"{experiment.experiment_id} references unknown hypotheses: {sorted(unknown_h)}")
            if unknown_d:
                raise ValueError(f"{experiment.experiment_id} references unknown diagnostics: {sorted(unknown_d)}")
            if unknown_v:
                raise ValueError(f"{experiment.experiment_id} references unknown variables: {sorted(unknown_v)}")

        for simulation in self.simulations:
            unknown = set(simulation.hypothesis_ids) - hypothesis_ids
            if unknown:
                raise ValueError(f"{simulation.simulation_id} references unknown hypotheses: {sorted(unknown)}")

        if "experimental" in self.methodologies and (not self.experiments or not self.diagnostics):
            raise ValueError("Experimental projects must define experiments and diagnostics")
        if "theoretical" in self.methodologies and not self.theory_models:
            raise ValueError("Theoretical projects must define at least one theory model")
        if "simulation" in self.methodologies and not self.simulations:
            raise ValueError("Simulation projects must define at least one simulation design")
        return self


def definition_gate(project: ResearchProjectDefinition) -> GateResult:
    checks = {
        "question_defined": bool(project.question.statement and project.question.scientific_gap),
        "objectives_have_observables": all(o.observables for o in project.objectives),
        "hypotheses_falsifiable": all(h.falsifiable_prediction and h.rejection_criterion for h in project.hypotheses),
        "variables_operationalized": all(v.operational_definition and v.uncertainty_definition for v in project.variables),
        "scope_defined": bool(project.scope.in_scope and project.scope.out_of_scope),
        "experimental_design_defined": "experimental" not in project.methodologies or bool(project.experiments and project.diagnostics),
        "theory_defined": "theoretical" not in project.methodologies or bool(project.theory_models),
        "simulation_defined": "simulation" not in project.methodologies or bool(project.simulations),
        "outputs_defined": bool(project.required_outputs),
    }
    passed_count = sum(checks.values())
    missing = [name for name, ok in checks.items() if not ok]
    return GateResult(
        name="research_definition",
        passed=not missing,
        score=passed_count / len(checks),
        blockers=[f"Missing required definition: {name}" for name in missing],
        details=checks,
    )
