from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class PaperKind(StrEnum):
    EXPERIMENTAL = "experimental"
    THEORETICAL = "theoretical"
    SIMULATION = "simulation"
    REVIEW = "review"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class EvidenceStrength(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    INFERRED = "inferred"
    SPECULATIVE = "speculative"


class ReviewDepth(StrEnum):
    METADATA = "metadata_verified"
    ABSTRACT = "abstract_reviewed"
    FULL_TEXT = "full_text_reviewed"


class ResearchStage(StrEnum):
    INGESTION = "ingestion"
    ANALYSIS = "analysis"
    CRITIQUE = "critique"
    EVIDENCE_GATE = "evidence_gate"
    SYNTHESIS = "synthesis"
    ALTERNATIVES = "alternatives"
    ADVERSARIAL = "adversarial"
    REPRODUCIBILITY = "reproducibility"
    WRITING = "writing"
    REVIEW = "review"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class Paper(BaseModel):
    canonical_id: str
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    publication_date: date | None = None
    journal: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    openalex_id: str | None = None
    url: HttpUrl | None = None
    cited_by_count: int = 0
    kind: PaperKind = PaperKind.UNKNOWN
    plasma_topics: list[str] = Field(default_factory=list)
    source: str = "unknown"
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Evidence(BaseModel):
    evidence_id: str
    paper_id: str
    text: str
    section: str | None = None
    page: int | None = None
    equation: str | None = None
    figure: str | None = None
    strength: EvidenceStrength = EvidenceStrength.DIRECT

    @property
    def has_source_pointer(self) -> bool:
        return any((self.section, self.page is not None, self.equation, self.figure))


class Claim(BaseModel):
    claim_id: str
    paper_id: str
    text: str
    claim_type: Literal[
        "result", "method", "assumption", "limitation", "hypothesis", "definition", "other"
    ] = "other"
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class PaperAnalysis(BaseModel):
    paper_id: str
    inferred_kind: PaperKind = PaperKind.UNKNOWN
    review_depth: ReviewDepth = ReviewDepth.FULL_TEXT
    summary: str = ""
    plasma_regime: list[str] = Field(default_factory=list)
    physical_model: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    equations: list[str] = Field(default_factory=list)
    experimental_parameters: dict[str, str] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)
    simulation_setup: dict[str, str] = Field(default_factory=dict)
    initial_conditions: list[str] = Field(default_factory=list)
    boundary_conditions: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    reproducibility: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


class Critique(BaseModel):
    paper_id: str
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    reproducibility_risks: list[str] = Field(default_factory=list)
    proposed_tests: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class SpecialistReview(BaseModel):
    paper_id: str
    role: Literal["theory", "experiment", "simulation", "adversarial", "reproducibility"]
    findings: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    proposed_tests: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AlternativeExplanation(BaseModel):
    explanation_id: str
    statement: str
    mechanism: str = ""
    target_claim_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    discriminating_observables: list[str] = Field(default_factory=list)
    falsification_test: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AlternativeExplanationSet(BaseModel):
    question: str
    explanations: list[AlternativeExplanation] = Field(default_factory=list)


class ResearchHypothesis(BaseModel):
    hypothesis_id: str
    statement: str
    mechanism: str = ""
    falsifiable_prediction: str = ""
    observables: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: Literal["candidate", "supported", "contested", "rejected"] = "candidate"


class GateResult(BaseModel):
    name: str
    passed: bool
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ReviewVerdict(BaseModel):
    passed: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    event: str
    detail: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearchState(BaseModel):
    session_id: str
    question: str
    stage: ResearchStage = ResearchStage.INGESTION
    candidate_paper_ids: list[str] = Field(default_factory=list)
    selected_paper_ids: list[str] = Field(default_factory=list)
    hypotheses: list[ResearchHypothesis] = Field(default_factory=list)
    alternative_explanations: list[AlternativeExplanation] = Field(default_factory=list)
    gate_results: list[GateResult] = Field(default_factory=list)
    synthesis: str = ""
    adversarial_review: str = ""
    reproducibility_review: str = ""
    draft: str = ""
    final_review: str = ""
    review_verdict: ReviewVerdict | None = None
    audit_log: list[AuditEvent] = Field(default_factory=list)

    def transition(self, stage: ResearchStage, detail: str = "") -> None:
        self.stage = stage
        self.audit_log.append(AuditEvent(event=f"stage:{stage.value}", detail=detail))


class CorpusAudit(BaseModel):
    target_papers: int
    total_papers: int
    deep_analysis_count: int
    method_counts: dict[str, int] = Field(default_factory=dict)
    time_counts: dict[str, int] = Field(default_factory=dict)
    domain_counts: dict[str, int] = Field(default_factory=dict)
    requirement_results: dict[str, bool] = Field(default_factory=dict)
    passed: bool = False


class PaperReviewResult(BaseModel):
    paper_id: str
    analysis: PaperAnalysis
    critique: Critique
    specialist_reviews: list[SpecialistReview] = Field(default_factory=list)
    gate_results: list[GateResult] = Field(default_factory=list)
