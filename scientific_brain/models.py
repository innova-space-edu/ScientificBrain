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
