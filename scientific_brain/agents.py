from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .models import (
    AlternativeExplanationSet,
    Critique,
    Paper,
    PaperAnalysis,
    PaperKind,
    ReviewVerdict,
    SpecialistReview,
)


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


PAPER_SYSTEM = """You are ScientificBrain Paper Agent, a plasma-physics research extractor.
Never invent missing values. Separate what the paper states from your inference. Every extracted
claim must retain a source pointer through evidence records (section/page/equation/figure when
available). Capture physical regime, governing equations, closure/orderings, assumptions,
parameters, diagnostics, initial and boundary conditions, numerics, uncertainty, limitations,
code/data availability and conclusions. Use SI units where a conversion is unambiguous but preserve
the reported value too. If the source does not report something, leave the corresponding field empty.
Do not convert your own interpretation into a statement attributed to the paper."""

CRITIC_SYSTEM = """You are ScientificBrain Critic Agent. Evaluate plasma-physics work as a skeptical
peer reviewer. Distinguish fatal validity issues, important limitations and optional improvements.
Do not reject a paper merely because a check is unreported; label evidence status explicitly.
Compare every criticism against the model regime and the claimed conclusion."""

SYNTHESIS_SYSTEM = """You are ScientificBrain Synthesis Agent. Build an evidence-weighted synthesis,
not a majority vote. Separate direct measurements, model-dependent inference and speculation.
Identify agreement, contradictory claims, incompatible regimes, unresolved questions and the exact
evidence that would discriminate between competing explanations."""

FRONTIER_SYSTEM = """You are ScientificBrain Frontier Agent. Propose research directions only after
mapping existing evidence and contradictions. Each proposal needs a falsifiable hypothesis, physical
mechanism, observables, required diagnostics or simulation outputs, confounders, and a result that
would count against the hypothesis. Mark extrapolation and speculation."""

THEORY_SYSTEM = """You are the independent theory reviewer in ScientificBrain. Audit governing
equations, closures, asymptotic orderings, neglected terms, conservation properties, limiting cases,
parameter-regime validity and whether the claimed interpretation actually follows from the model.
Do not repeat the main extractor. Focus on failure modes and discriminating theoretical checks."""

EXPERIMENT_SYSTEM = """You are the independent experimental reviewer in ScientificBrain. Audit
diagnostic calibration, bandwidth, transfer functions, perturbation, spatial/temporal resolution,
systematics, detection limits, sample size, shot-to-shot variability, uncertainty propagation and
whether independent diagnostics support the key physical claims."""

SIMULATION_SYSTEM = """You are the independent numerical reviewer in ScientificBrain. Audit grid or
particle resolution, time step, convergence, stability criteria, numerical heating/diffusion/noise,
domain size, boundary/initial-condition sensitivity, solver dependence, verification and validation."""

ADVERSARIAL_SYSTEM = """You are the adversarial scientific reviewer in ScientificBrain. Try to break
the current interpretation using plausible alternative mechanisms, hidden confounders, regime
mismatch, circular reasoning, overfitting, selection bias, untested assumptions and contradictory
evidence. Every objection must be testable or tied to a specific evidence gap."""

REPRODUCIBILITY_SYSTEM = """You are the reproducibility reviewer in ScientificBrain. Determine what
an independent group would need to reproduce the result: parameters, geometry, materials, diagnostic
settings, calibration, processing, code/version, solver settings, data, uncertainty model and
acceptance criteria. Separate absent information from information known to be inadequate."""

ALTERNATIVES_SYSTEM = """You are ScientificBrain Alternative Explanations Agent. For each important
claim, propose only physically plausible competing explanations. Each explanation must state a
mechanism, the claims it challenges, the evidence for/against it, observables that discriminate it,
and a falsification test. Avoid generic possibilities that cannot be tested."""

WRITER_SYSTEM = """You are ScientificBrain Writer. Convert the accepted synthesis into a concise
scientific answer without adding new facts. Every important factual statement must include one or
more evidence IDs in square brackets, for example [e12]. Preserve uncertainty, regime limits,
contradictions and alternative explanations. Do not cite paper IDs when a more specific evidence ID
is available."""

REVIEWER_SYSTEM = """You are ScientificBrain Reviewer. Audit the draft against the supplied evidence.
Pass only if important factual claims are traceable to evidence IDs and if direct measurement,
model-dependent inference and speculation are distinguished. List unsupported statements and exact
required changes. Return only the structured verdict."""


COMMON_CHECKS = [
    "dimensional consistency and units",
    "parameter regime and ordering validity",
    "energy/particle/momentum conservation where applicable",
    "causal claim versus correlation",
    "uncertainty propagation and sensitivity",
    "reproducibility: data, code, parameters and versioning",
]

EXPERIMENT_CHECKS = [
    "diagnostic calibration and transfer function",
    "systematic errors and diagnostic perturbation of the plasma",
    "shot-to-shot variability and sample size",
    "temporal/spatial resolution versus relevant plasma scales",
    "background subtraction, instrument saturation and detection limits",
    "independent or redundant diagnostics for key claims",
]

THEORY_CHECKS = [
    "closure assumptions and neglected moments",
    "asymptotic ordering and domain of validity",
    "equilibrium/stability assumptions",
    "collisionless/collisional and magnetization limits",
    "gauge, symmetry and conservation consistency where relevant",
    "limiting cases against established theory",
]

SIMULATION_CHECKS = [
    "grid/particle/time-step convergence",
    "CFL or solver stability criteria",
    "boundary and initial-condition sensitivity",
    "numerical heating, diffusion, dispersion and noise",
    "domain size relative to physical scales",
    "solver/model sensitivity and benchmark/verification",
    "validation against experiment or an independent code when available",
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


ModelT = TypeVar("ModelT", bound=BaseModel)


def _json_payload(raw: str) -> str:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    return text[start : end + 1]


def _complete_model(
    provider: LLMProvider,
    system: str,
    user: str,
    model_type: type[ModelT],
) -> ModelT:
    schema = json.dumps(model_type.model_json_schema(), ensure_ascii=False)
    response = provider.complete(
        system + "\nReturn ONLY one valid JSON object matching the supplied JSON Schema.",
        f"{user}\n\nJSON SCHEMA:\n{schema}",
    )
    return model_type.model_validate_json(_json_payload(response))


@dataclass
class PaperAgent:
    provider: LLMProvider

    def analyze(self, paper: Paper, text: str) -> str:
        return self.provider.complete(
            PAPER_SYSTEM,
            f"METADATA:\n{paper.model_dump_json(indent=2)}\n\nPAPER TEXT:\n{text}",
        )

    def analyze_structured(self, paper: Paper, text: str) -> PaperAnalysis:
        result = _complete_model(
            self.provider,
            PAPER_SYSTEM,
            f"METADATA:\n{paper.model_dump_json(indent=2)}\n\nPAPER TEXT:\n{text}",
            PaperAnalysis,
        )
        if result.paper_id != paper.canonical_id:
            result.paper_id = paper.canonical_id
        for evidence in result.evidence:
            evidence.paper_id = paper.canonical_id
        for claim in result.claims:
            claim.paper_id = paper.canonical_id
        return result


@dataclass
class CriticAgent:
    provider: LLMProvider

    def critique(self, paper: Paper, extracted_analysis: str) -> str:
        checks = "\n".join(f"- {x}" for x in critique_checklist(paper.kind))
        prompt = (
            f"PAPER:\n{paper.model_dump_json(indent=2)}\n\n"
            f"EXTRACTED ANALYSIS:\n{extracted_analysis}\n\nCHECKS:\n{checks}"
        )
        return self.provider.complete(CRITIC_SYSTEM, prompt)

    def critique_structured(self, paper: Paper, analysis: PaperAnalysis) -> Critique:
        checks = "\n".join(f"- {x}" for x in critique_checklist(paper.kind))
        result = _complete_model(
            self.provider,
            CRITIC_SYSTEM,
            f"PAPER:\n{paper.model_dump_json(indent=2)}\n\n"
            f"ANALYSIS:\n{analysis.model_dump_json(indent=2)}\n\nCHECKS:\n{checks}",
            Critique,
        )
        result.paper_id = paper.canonical_id
        return result


@dataclass
class _SpecialistAgent:
    provider: LLMProvider
    role: str
    system: str

    def review(self, paper: Paper, analysis: PaperAnalysis) -> SpecialistReview:
        result = _complete_model(
            self.provider,
            self.system,
            f"REQUIRED ROLE: {self.role}\n\n"
            f"PAPER:\n{paper.model_dump_json(indent=2)}\n\n"
            f"ANALYSIS:\n{analysis.model_dump_json(indent=2)}",
            SpecialistReview,
        )
        result.paper_id = paper.canonical_id
        result.role = self.role  # type: ignore[assignment]
        return result


class TheoryAgent(_SpecialistAgent):
    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider, "theory", THEORY_SYSTEM)


class ExperimentAgent(_SpecialistAgent):
    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider, "experiment", EXPERIMENT_SYSTEM)


class SimulationAgent(_SpecialistAgent):
    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider, "simulation", SIMULATION_SYSTEM)


class AdversarialAgent(_SpecialistAgent):
    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider, "adversarial", ADVERSARIAL_SYSTEM)


class ReproducibilityAgent(_SpecialistAgent):
    def __init__(self, provider: LLMProvider) -> None:
        super().__init__(provider, "reproducibility", REPRODUCIBILITY_SYSTEM)


@dataclass
class SynthesizerAgent:
    provider: LLMProvider

    def synthesize(self, question: str, evidence_bundle: str) -> str:
        return self.provider.complete(
            SYNTHESIS_SYSTEM,
            f"QUESTION: {question}\n\nEVIDENCE:\n{evidence_bundle}",
        )


@dataclass
class AlternativeExplanationAgent:
    provider: LLMProvider

    def propose(self, question: str, synthesis: str, evidence_bundle: str) -> AlternativeExplanationSet:
        return _complete_model(
            self.provider,
            ALTERNATIVES_SYSTEM,
            f"QUESTION:\n{question}\n\nSYNTHESIS:\n{synthesis}\n\nEVIDENCE:\n{evidence_bundle}",
            AlternativeExplanationSet,
        )


@dataclass
class FrontierAgent:
    provider: LLMProvider

    def propose(self, question: str, synthesis: str) -> str:
        return self.provider.complete(
            FRONTIER_SYSTEM,
            f"QUESTION: {question}\n\nSYNTHESIS:\n{synthesis}",
        )


@dataclass
class WriterAgent:
    provider: LLMProvider

    def write(
        self,
        question: str,
        synthesis: str,
        alternatives: AlternativeExplanationSet,
        adversarial_review: str,
        reproducibility_review: str,
        evidence_bundle: str,
    ) -> str:
        return self.provider.complete(
            WRITER_SYSTEM,
            f"QUESTION:\n{question}\n\nSYNTHESIS:\n{synthesis}\n\n"
            f"ALTERNATIVE EXPLANATIONS:\n{alternatives.model_dump_json(indent=2)}\n\n"
            f"ADVERSARIAL REVIEW:\n{adversarial_review}\n\n"
            f"REPRODUCIBILITY REVIEW:\n{reproducibility_review}\n\n"
            f"EVIDENCE:\n{evidence_bundle}",
        )


@dataclass
class ReviewerAgent:
    provider: LLMProvider

    def review(self, draft: str, evidence_bundle: str) -> ReviewVerdict:
        return _complete_model(
            self.provider,
            REVIEWER_SYSTEM,
            f"DRAFT:\n{draft}\n\nEVIDENCE:\n{evidence_bundle}",
            ReviewVerdict,
        )
