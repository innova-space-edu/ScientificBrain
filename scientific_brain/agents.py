from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import Paper, PaperKind


class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


PAPER_SYSTEM = """You are ScientificBrain Paper Agent, a plasma-physics research extractor.
Never invent missing values. Separate what the paper states from your inference. Every extracted
claim must retain a source pointer (section/page/equation/figure when available). Capture physical
regime, governing equations, closure/orderings, assumptions, parameters, diagnostics, initial and
boundary conditions, numerics, uncertainty, limitations, code/data availability and conclusions.
Use SI units where a conversion is unambiguous but preserve the reported value too."""

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


@dataclass
class PaperAgent:
    provider: LLMProvider

    def analyze(self, paper: Paper, text: str) -> str:
        return self.provider.complete(PAPER_SYSTEM, f"METADATA:\n{paper.model_dump_json(indent=2)}\n\nPAPER TEXT:\n{text}")


@dataclass
class CriticAgent:
    provider: LLMProvider

    def critique(self, paper: Paper, extracted_analysis: str) -> str:
        checks = "\n".join(f"- {x}" for x in critique_checklist(paper.kind))
        prompt = f"PAPER:\n{paper.model_dump_json(indent=2)}\n\nEXTRACTED ANALYSIS:\n{extracted_analysis}\n\nCHECKS:\n{checks}"
        return self.provider.complete(CRITIC_SYSTEM, prompt)


@dataclass
class SynthesizerAgent:
    provider: LLMProvider

    def synthesize(self, question: str, evidence_bundle: str) -> str:
        return self.provider.complete(SYNTHESIS_SYSTEM, f"QUESTION: {question}\n\nEVIDENCE:\n{evidence_bundle}")


@dataclass
class FrontierAgent:
    provider: LLMProvider

    def propose(self, question: str, synthesis: str) -> str:
        return self.provider.complete(FRONTIER_SYSTEM, f"QUESTION: {question}\n\nSYNTHESIS:\n{synthesis}")
