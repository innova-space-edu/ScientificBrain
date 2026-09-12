from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from .agents import (
    AdversarialAgent,
    AlternativeExplanationAgent,
    CriticAgent,
    ExperimentAgent,
    PaperAgent,
    ReproducibilityAgent,
    ReviewerAgent,
    SimulationAgent,
    SynthesizerAgent,
    TheoryAgent,
    WriterAgent,
)
from .gates import run_paper_gates
from .memory import ScientificMemory
from .models import (
    AuditEvent,
    GateResult,
    PaperKind,
    PaperReviewResult,
    ResearchStage,
    ResearchState,
    ReviewDepth,
)
from .providers import InferenceTask


SYNTHESIS_ADVERSARIAL_SYSTEM = """You are ScientificBrain's cross-paper adversarial reviewer.
Attack the synthesis, not the authors. Identify unsupported generalization, hidden regime mismatch,
citation cascades, dependence between supposedly independent evidence, contradictory measurements,
missing uncertainty, and alternative mechanisms. For every objection, identify the evidence or
experiment that could resolve it. Never invent a paper, result, equation or measurement."""


def _for_task(provider: object, task: InferenceTask | str) -> object:
    selector = getattr(provider, "for_task", None)
    if callable(selector):
        return selector(task.value if isinstance(task, InferenceTask) else task)
    return provider


@dataclass
class ScientificWorkflow:
    memory: ScientificMemory
    provider: object

    def _specialists(self, kind: PaperKind):
        research_provider = _for_task(self.provider, InferenceTask.RESEARCH)
        agents = []
        if kind == PaperKind.EXPERIMENTAL:
            agents.extend([ExperimentAgent(research_provider), TheoryAgent(research_provider)])
        elif kind == PaperKind.THEORETICAL:
            agents.append(TheoryAgent(research_provider))
        elif kind == PaperKind.SIMULATION:
            agents.extend([SimulationAgent(research_provider), TheoryAgent(research_provider)])
        elif kind == PaperKind.HYBRID:
            agents.extend([
                TheoryAgent(research_provider),
                ExperimentAgent(research_provider),
                SimulationAgent(research_provider),
            ])
        agents.extend([
            AdversarialAgent(research_provider),
            ReproducibilityAgent(research_provider),
        ])
        return agents

    def review_paper(
        self,
        paper_id: str,
        text: str,
        *,
        depth: ReviewDepth = ReviewDepth.FULL_TEXT,
        source_path: str | None = None,
    ) -> PaperReviewResult:
        paper = self.memory.get_paper(paper_id)
        if paper is None:
            raise KeyError(f"Unknown paper: {paper_id}")

        structured_provider = _for_task(self.provider, InferenceTask.STRUCTURED)
        research_provider = _for_task(self.provider, InferenceTask.RESEARCH)

        analysis = PaperAgent(structured_provider).analyze_structured(paper, text)
        analysis.review_depth = depth
        if paper.kind == PaperKind.UNKNOWN and analysis.inferred_kind != PaperKind.UNKNOWN:
            self.memory.set_paper_kind(paper_id, analysis.inferred_kind)
            paper.kind = analysis.inferred_kind
        self.memory.save_analysis(analysis)

        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        self.memory.set_review_status(
            paper_id,
            depth,
            source_path=source_path,
            content_sha256=content_hash,
        )

        critique = CriticAgent(research_provider).critique_structured(paper, analysis)
        self.memory.save_critique(critique)

        specialist_reviews = []
        for agent in self._specialists(paper.kind):
            review = agent.review(paper, analysis)
            self.memory.save_specialist_review(review)
            specialist_reviews.append(review)

        gates = run_paper_gates(analysis, paper.kind)
        for result in gates:
            self.memory.record_gate(result, paper_id=paper_id)

        return PaperReviewResult(
            paper_id=paper_id,
            analysis=analysis,
            critique=critique,
            specialist_reviews=specialist_reviews,
            gate_results=gates,
        )

    def start_session(
        self,
        question: str,
        *,
        paper_ids: list[str] | None = None,
        search_query: str | None = None,
        limit: int = 20,
    ) -> ResearchState:
        if paper_ids is None:
            rows = self.memory.search(search_query or question, limit=limit)
            paper_ids = [row["canonical_id"] for row in rows]

        session_id = f"research:{uuid.uuid4().hex}"
        state = ResearchState(
            session_id=session_id,
            question=question,
            candidate_paper_ids=list(paper_ids),
            selected_paper_ids=list(paper_ids),
            audit_log=[AuditEvent(event="session_created", detail=f"{len(paper_ids)} candidate papers")],
        )
        self.memory.save_state(state)
        return state

    def _evidence_bundle(self, paper_ids: list[str]) -> tuple[str, list[str]]:
        chunks: list[str] = []
        accepted: list[str] = []
        for paper_id in paper_ids:
            paper = self.memory.get_paper(paper_id)
            analysis = self.memory.get_analysis(paper_id)
            critique = self.memory.get_critique(paper_id)
            if paper is None or analysis is None:
                continue

            gates = run_paper_gates(analysis, paper.kind)
            hard_fail = any(
                gate.name in {"evidence", "provenance"} and not gate.passed
                for gate in gates
            )
            if hard_fail:
                continue

            accepted.append(paper_id)
            reviews = self.memory.get_specialist_reviews(paper_id)
            chunks.append(
                "\n".join([
                    f"=== {paper_id} ===",
                    f"TITLE: {paper.title}",
                    f"KIND: {paper.kind.value}",
                    f"ANALYSIS: {analysis.model_dump_json()}",
                    f"CRITIQUE: {critique.model_dump_json() if critique else '{}'}",
                    "SPECIALIST REVIEWS:",
                    *[review.model_dump_json() for review in reviews],
                ])
            )
        return "\n\n".join(chunks), accepted

    def synthesize_session(self, session_id: str) -> ResearchState:
        state = self.memory.load_state(session_id)
        if state is None:
            raise KeyError(f"Unknown research session: {session_id}")

        state.transition(ResearchStage.EVIDENCE_GATE, "Filtering papers through evidence/provenance gates")
        bundle, accepted = self._evidence_bundle(state.selected_paper_ids)
        state.selected_paper_ids = accepted

        corpus_gate = GateResult(
            name="session_evidence",
            passed=bool(accepted),
            score=(len(accepted) / len(state.candidate_paper_ids)) if state.candidate_paper_ids else 0.0,
            blockers=[] if accepted else ["No reviewed paper passed the evidence/provenance gates."],
            details={
                "candidate_papers": len(state.candidate_paper_ids),
                "accepted_papers": len(accepted),
            },
        )
        state.gate_results.append(corpus_gate)
        self.memory.record_gate(corpus_gate, session_id=state.session_id)
        if not corpus_gate.passed:
            state.transition(ResearchStage.BLOCKED, corpus_gate.blockers[0])
            self.memory.save_state(state)
            return state

        long_context_provider = _for_task(self.provider, InferenceTask.LONG_CONTEXT)
        research_provider = _for_task(self.provider, InferenceTask.RESEARCH)
        text_provider = _for_task(self.provider, InferenceTask.TEXT)
        structured_provider = _for_task(self.provider, InferenceTask.STRUCTURED)

        state.transition(ResearchStage.SYNTHESIS, f"Synthesizing {len(accepted)} accepted papers")
        state.synthesis = SynthesizerAgent(long_context_provider).synthesize(state.question, bundle)

        state.transition(ResearchStage.ALTERNATIVES, "Generating discriminable alternative explanations")
        alternatives = AlternativeExplanationAgent(research_provider).propose(
            state.question,
            state.synthesis,
            bundle,
        )
        state.alternative_explanations = alternatives.explanations

        state.transition(ResearchStage.ADVERSARIAL, "Cross-paper adversarial audit")
        state.adversarial_review = research_provider.complete(  # type: ignore[attr-defined]
            SYNTHESIS_ADVERSARIAL_SYSTEM,
            f"QUESTION:\n{state.question}\n\nSYNTHESIS:\n{state.synthesis}\n\n"
            f"ALTERNATIVES:\n{alternatives.model_dump_json(indent=2)}\n\nEVIDENCE:\n{bundle}",
        )

        state.transition(ResearchStage.REPRODUCIBILITY, "Auditing reproducibility across accepted evidence")
        reproducibility_summaries = []
        for paper_id in accepted:
            analysis = self.memory.get_analysis(paper_id)
            paper = self.memory.get_paper(paper_id)
            if analysis is None or paper is None:
                continue
            gate = next(
                item for item in run_paper_gates(analysis, paper.kind)
                if item.name == "reproducibility"
            )
            reproducibility_summaries.append(f"{paper_id}: {gate.model_dump_json()}")
        state.reproducibility_review = "\n".join(reproducibility_summaries)

        state.transition(ResearchStage.WRITING, "Drafting evidence-linked scientific answer")
        state.draft = WriterAgent(text_provider).write(
            state.question,
            state.synthesis,
            alternatives,
            state.adversarial_review,
            state.reproducibility_review,
            bundle,
        )

        state.transition(ResearchStage.REVIEW, "Final claim-to-evidence audit")
        verdict = ReviewerAgent(structured_provider).review(state.draft, bundle)
        state.review_verdict = verdict
        state.final_review = verdict.model_dump_json(indent=2)
        if verdict.passed:
            state.transition(ResearchStage.COMPLETE, "Research workflow completed")
        else:
            state.transition(
                ResearchStage.BLOCKED,
                "Final reviewer found unsupported claims or required scientific corrections",
            )
        self.memory.save_state(state)
        return state
