from __future__ import annotations

from dataclasses import dataclass, field


SELF_CRITIQUE_SYSTEM = """You are the self-review stage of a scientific agent. Do not produce hidden
reasoning or a new scientific story. Inspect the supplied draft for concrete defects: unsupported
claims, missing variables, regime mismatch, ambiguous definitions, missing uncertainty, missing
alternative explanations, methodological gaps and failure to follow the requested output contract.
Return a concise list of defects and required corrections."""

REVISION_SYSTEM = """You are the revision stage of a scientific agent. Revise the original draft using
only the supplied task context and the explicit defect list. Do not introduce new facts that are not
supported by the task context. Preserve the requested output format exactly, especially JSON when the
original task required JSON."""

INDEPENDENT_REVIEW_SYSTEM = """You are an independent scientific reviewer. Audit the revised output
without assuming that the generating agent is correct. Report only specific remaining defects,
missing evidence, invalid transitions in epistemic status, or unaddressed scientific risks. Do not
reward fluency. If no substantive defect remains, say PASS."""


@dataclass
class ReflectiveResult:
    role_id: str
    draft: str
    self_critique: str
    revised: str
    independent_review: str = ""
    review_passed: bool = False
    iterations: int = 1
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class ReflectiveAgentRunner:
    provider: object
    independent_provider: object | None = None

    def run(self, role_id: str, system: str, user: str) -> ReflectiveResult:
        draft = self.provider.complete(system, user)  # type: ignore[attr-defined]
        critique = self.provider.complete(  # type: ignore[attr-defined]
            SELF_CRITIQUE_SYSTEM,
            f"ROLE: {role_id}\n\nTASK CONTEXT:\n{user}\n\nDRAFT:\n{draft}",
        )
        revised = self.provider.complete(  # type: ignore[attr-defined]
            REVISION_SYSTEM,
            f"ROLE: {role_id}\n\nORIGINAL SYSTEM CONTRACT:\n{system}\n\n"
            f"TASK CONTEXT:\n{user}\n\nORIGINAL DRAFT:\n{draft}\n\nDEFECT LIST:\n{critique}",
        )

        reviewer = self.independent_provider or self.provider
        independent = reviewer.complete(  # type: ignore[attr-defined]
            INDEPENDENT_REVIEW_SYSTEM,
            f"ROLE UNDER REVIEW: {role_id}\n\nTASK CONTEXT:\n{user}\n\nREVISED OUTPUT:\n{revised}",
        )
        passed = independent.strip().upper().startswith("PASS")
        return ReflectiveResult(
            role_id=role_id,
            draft=draft,
            self_critique=critique,
            revised=revised,
            independent_review=independent,
            review_passed=passed,
        )
