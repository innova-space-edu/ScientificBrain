from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class GraphNodeType(StrEnum):
    PAPER = "paper"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    MODEL = "model"
    ASSUMPTION = "assumption"
    EQUATION = "equation"
    DIAGNOSTIC = "diagnostic"
    OBSERVABLE = "observable"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    DATASET = "dataset"


class GraphRelation(StrEnum):
    ASSERTED_IN = "asserted_in"
    SUPPORTED_BY = "supported_by"
    CONTRADICTED_BY = "contradicted_by"
    CONTAINS = "contains"
    USES_MODEL = "uses_model"
    USES_ASSUMPTION = "uses_assumption"
    USES_EQUATION = "uses_equation"
    USES_DIAGNOSTIC = "uses_diagnostic"
    MEASURES = "measures"
    DEPENDS_ON = "depends_on"
    EXTENDS = "extends"
    REPLICATES = "replicates"
    SAME_DATASET = "same_dataset"
    SHARED_SOURCE = "shared_source"
    DISCRIMINATES = "discriminates"
    TESTS = "tests"


class EpistemicState(StrEnum):
    OBSERVED = "observed"
    MEASURED = "measured"
    DERIVED = "derived"
    INFERRED = "inferred"
    SUPPORTED = "supported"
    HYPOTHESIS = "hypothesis"
    SPECULATIVE = "speculative"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class EvidenceLineageType(StrEnum):
    SAME_PAPER = "same_paper"
    SAME_DATASET = "same_dataset"
    REANALYSIS = "reanalysis"
    CITES_PRIMARY = "cites_primary"
    SHARED_SOURCE = "shared_source"
    DERIVED_FROM = "derived_from"
    UNKNOWN_DEPENDENCE = "unknown_dependence"


class ScientificGraphNode(BaseModel):
    node_id: str
    node_type: GraphNodeType
    label: str
    paper_id: str | None = None
    claim_id: str | None = None
    evidence_id: str | None = None
    epistemic_state: EpistemicState = EpistemicState.UNRESOLVED
    properties: dict[str, Any] = Field(default_factory=dict)


class ScientificGraphEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation: GraphRelation
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class EvidenceLineage(BaseModel):
    lineage_id: str
    source_evidence_id: str
    target_evidence_id: str
    lineage_type: EvidenceLineageType
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: str = ""
    status: str = "candidate"


class ContradictionRecord(BaseModel):
    contradiction_id: str
    claim_a_id: str
    claim_b_id: str
    contradiction_type: str
    summary: str
    regime_difference: str = ""
    possible_explanation: str = ""
    discriminating_observables: list[str] = Field(default_factory=list)
    required_test: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: str = "candidate"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContradictionBatch(BaseModel):
    contradictions: list[ContradictionRecord] = Field(default_factory=list)


class CompetingHypothesis(BaseModel):
    hypothesis_id: str
    statement: str
    mechanism: str
    explains_claim_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    falsifiable_predictions: list[str] = Field(default_factory=list)
    discriminating_observables: list[str] = Field(default_factory=list)
    discriminating_experiment: str = ""
    regime_of_validity: str = ""
    rejection_criterion: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: str = "candidate"


class HypothesisCompetition(BaseModel):
    competition_id: str
    question: str
    contradiction_ids: list[str] = Field(default_factory=list)
    hypotheses: list[CompetingHypothesis] = Field(default_factory=list)
    decision_needed: str = ""


class GraphBuildResult(BaseModel):
    nodes: list[ScientificGraphNode] = Field(default_factory=list)
    edges: list[ScientificGraphEdge] = Field(default_factory=list)
    paper_count: int = 0
    claim_count: int = 0
    evidence_count: int = 0
