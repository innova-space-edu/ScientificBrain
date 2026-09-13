from __future__ import annotations

from dataclasses import dataclass

from .agents_legacy import *  # noqa: F401,F403
from . import agents_legacy as _legacy
from .models import Critique, Paper, PaperAnalysis, PaperKind, SpecialistReview


PAPER_SYSTEM = """You are ScientificBrain's discipline-agnostic Paper Agent.
Extract the scientific content of the supplied paper without assuming a field in advance. Never
invent missing values. Separate what the paper explicitly reports from your inference. Every
important claim must retain provenance through evidence records with section/page/equation/figure
when available. Capture study system or physical regime, models or governing equations when
applicable, assumptions, methods, parameters, measurements/diagnostics, initial and boundary
conditions for mathematical or numerical work, uncertainty/statistics, limitations, code/data
availability and conclusions. Use the existing PaperAnalysis fields where they apply; put the core
scientific meaning in claims and evidence even when a discipline-specific detail has no dedicated
field. Do not force plasma terminology onto non-plasma research. Return only supported content."""

CRITIC_SYSTEM = """You are ScientificBrain's independent critical reviewer. Evaluate validity at the
level appropriate to the paper's actual discipline and study design. Distinguish fatal validity
issues, important limitations and optional improvements. Do not penalize a paper merely because a
check is irrelevant to its field. Separate absent reporting from demonstrated inadequacy and tie
criticisms to the claims they can affect."""

THEORY_SYSTEM = """You are ScientificBrain's independent theory reviewer. When theory or a formal
model is present, audit assumptions, equations, closures or approximations, parameter-domain
validity, internal consistency, conservation or invariants where relevant, limiting cases and whether
the conclusions actually follow from the model. For fields without governing equations, audit the
conceptual model and inferential assumptions instead. Do not invent requirements irrelevant to the
paper's discipline."""

EXPERIMENT_SYSTEM = """You are ScientificBrain's independent experimental/empirical reviewer. Audit
measurement validity, calibration where relevant, controls/comparators, sampling, resolution,
systematic and random error, detection limits, replication or repeated measurements, uncertainty
and whether the observations support the key claims. Adapt these checks to the actual discipline."""

SIMULATION_SYSTEM = """You are ScientificBrain's independent computational reviewer. Audit model and
solver assumptions, resolution/discretization or sampling, convergence, stability where relevant,
boundary/initial conditions, numerical or algorithmic error, sensitivity, verification,
validation and reproducibility. Adapt the criteria to the computational method actually used."""

ADVERSARIAL_SYSTEM = """You are ScientificBrain's adversarial scientific reviewer. Try to break the
current interpretation using plausible alternative mechanisms, hidden confounders, regime or
population mismatch, circular reasoning, overfitting, selection bias, untested assumptions and
contradictory evidence. Every objection must be testable or tied to a concrete evidence gap."""

REPRODUCIBILITY_SYSTEM = """You are ScientificBrain's reproducibility reviewer. Determine what an
independent group would need to reproduce the reported result: materials/samples or data, parameters,
geometry or protocol where applicable, measurement settings, calibration, preprocessing, code and
versions, solver/statistical settings, uncertainty model and acceptance criteria. Separate missing
reporting from information known to be inadequate."""

COMMON_CHECKS = [
    "units and dimensional consistency where applicable",
    "study population, physical regime or domain of validity",
    "causal claim versus correlation or model-dependent inference",
    "uncertainty, sensitivity and robustness",
    "reproducibility: data, code, parameters, protocol and versioning",
]
EXPERIMENT_CHECKS = [
    "measurement validity and calibration where applicable",
    "controls, comparators, confounders and systematic error",
    "sample size, repetitions and variability",
    "temporal/spatial/instrument resolution where relevant",
    "background, saturation, censoring and detection limits where relevant",
    "independent or redundant support for central claims",
]
THEORY_CHECKS = [
    "model assumptions, approximations and domain of validity",
    "mathematical or conceptual consistency",
    "conservation, invariants or consistency constraints where applicable",
    "limiting cases or comparison with established results",
]
SIMULATION_CHECKS = [
    "resolution or sampling convergence",
    "time-step or solver stability where applicable",
    "boundary and initial-condition sensitivity",
    "numerical, algorithmic or discretization error",
    "domain size or sample coverage",
    "verification, benchmarks and validation",
]


def critique_checklist(kind: PaperKind) -> list[str]:
    checks = list(COMMON_CHECKS)
    if kind in {PaperKind.EXPERIMENTAL, PaperKind.HYBRID}:
        checks += EXPERIMENT_CHECKS
    if kind in {PaperKind.THEORETICAL, PaperKind.HYBRID}:
        checks += THEORY_CHECKS
    if kind in {PaperKind.SIMULATION, PaperKind.HYBRID}:
        checks += SIMULATION_CHECKS
    return checks


@dataclass
class PaperAgent:
    provider: _legacy.LLMProvider

    def analyze(self, paper: Paper, text: str) -> str:
        return self.provider.complete(
            PAPER_SYSTEM,
            f"METADATA:\n{paper.model_dump_json(indent=2)}\n\nPAPER TEXT:\n{text}",
        )

    def analyze_structured(self, paper: Paper, text: str) -> PaperAnalysis:
        result = _legacy._complete_model(
            self.provider,
            PAPER_SYSTEM,
            f"METADATA:\n{paper.model_dump_json(indent=2)}\n\nPAPER TEXT:\n{text}",
            PaperAnalysis,
        )
        result.paper_id = paper.canonical_id
        for evidence in result.evidence:
            evidence.paper_id = paper.canonical_id
        for claim in result.claims:
            claim.paper_id = paper.canonical_id
        return result


@dataclass
class CriticAgent:
    provider: _legacy.LLMProvider

    def critique(self, paper: Paper, extracted_analysis: str) -> str:
        checks = "\n".join(f"- {x}" for x in critique_checklist(paper.kind))
        return self.provider.complete(
            CRITIC_SYSTEM,
            f"PAPER:\n{paper.model_dump_json(indent=2)}\n\nANALYSIS:\n{extracted_analysis}\n\nCHECKS:\n{checks}",
        )

    def critique_structured(self, paper: Paper, analysis: PaperAnalysis) -> Critique:
        checks = "\n".join(f"- {x}" for x in critique_checklist(paper.kind))
        result = _legacy._complete_model(
            self.provider,
            CRITIC_SYSTEM,
            f"PAPER:\n{paper.model_dump_json(indent=2)}\n\nANALYSIS:\n{analysis.model_dump_json(indent=2)}\n\nCHECKS:\n{checks}",
            Critique,
        )
        result.paper_id = paper.canonical_id
        return result


@dataclass
class _GenericSpecialistAgent:
    provider: _legacy.LLMProvider
    role: str
    system: str

    def review(self, paper: Paper, analysis: PaperAnalysis) -> SpecialistReview:
        result = _legacy._complete_model(
            self.provider,
            self.system,
            f"REQUIRED ROLE: {self.role}\n\nPAPER:\n{paper.model_dump_json(indent=2)}\n\nANALYSIS:\n{analysis.model_dump_json(indent=2)}",
            SpecialistReview,
        )
        result.paper_id = paper.canonical_id
        result.role = self.role  # type: ignore[assignment]
        return result


class TheoryAgent(_GenericSpecialistAgent):
    def __init__(self, provider: _legacy.LLMProvider) -> None:
        super().__init__(provider, "theory", THEORY_SYSTEM)


class ExperimentAgent(_GenericSpecialistAgent):
    def __init__(self, provider: _legacy.LLMProvider) -> None:
        super().__init__(provider, "experiment", EXPERIMENT_SYSTEM)


class SimulationAgent(_GenericSpecialistAgent):
    def __init__(self, provider: _legacy.LLMProvider) -> None:
        super().__init__(provider, "simulation", SIMULATION_SYSTEM)


class AdversarialAgent(_GenericSpecialistAgent):
    def __init__(self, provider: _legacy.LLMProvider) -> None:
        super().__init__(provider, "adversarial", ADVERSARIAL_SYSTEM)


class ReproducibilityAgent(_GenericSpecialistAgent):
    def __init__(self, provider: _legacy.LLMProvider) -> None:
        super().__init__(provider, "reproducibility", REPRODUCIBILITY_SYSTEM)
