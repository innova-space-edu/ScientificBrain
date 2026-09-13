from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from .graph_models import (
    EpistemicState,
    GraphBuildResult,
    GraphNodeType,
    GraphRelation,
    ScientificGraphEdge,
    ScientificGraphNode,
)
from .models import Paper, PaperAnalysis


def _slug(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]


def _node_id(kind: str, scope: str, value: str) -> str:
    return f"{kind}:{_slug(scope + '|' + value)}"


def _edge_id(source: str, relation: str, target: str) -> str:
    return f"edge:{_slug(source + '|' + relation + '|' + target)}"


def _claim_state(claim_type: str, evidence_ids: list[str]) -> EpistemicState:
    if claim_type == "hypothesis":
        return EpistemicState.HYPOTHESIS
    if claim_type == "assumption":
        return EpistemicState.INFERRED
    if claim_type == "limitation":
        return EpistemicState.OBSERVED
    if evidence_ids:
        return EpistemicState.SUPPORTED
    return EpistemicState.UNRESOLVED


class ScientificGraphBuilder:
    """Create a deterministic graph from accepted paper analyses.

    The builder never invents cross-paper causal or contradiction relations. Those are
    added later by dedicated agents. This layer only materializes provenance-preserving
    structures directly supported by stored paper analyses.
    """

    def build(self, bundles: Iterable[dict[str, Any]]) -> GraphBuildResult:
        nodes: dict[str, ScientificGraphNode] = {}
        edges: dict[str, ScientificGraphEdge] = {}
        paper_count = claim_count = evidence_count = 0

        for bundle in bundles:
            record = bundle.get("record") or {}
            analysis_raw = bundle.get("analysis")
            if not record or not analysis_raw:
                continue
            paper = Paper.model_validate(record)
            analysis = PaperAnalysis.model_validate(analysis_raw)
            paper_count += 1

            paper_node_id = f"paper:{paper.canonical_id}"
            nodes[paper_node_id] = ScientificGraphNode(
                node_id=paper_node_id,
                node_type=GraphNodeType.PAPER,
                label=paper.title,
                paper_id=paper.canonical_id,
                epistemic_state=EpistemicState.OBSERVED,
                properties={
                    "doi": paper.doi,
                    "arxiv_id": paper.arxiv_id,
                    "journal": paper.journal,
                    "publication_date": paper.publication_date.isoformat() if paper.publication_date else None,
                    "kind": paper.kind.value,
                    "topics": paper.plasma_topics,
                    "review_depth": analysis.review_depth.value,
                },
            )

            evidence_node_by_id: dict[str, str] = {}
            for evidence in analysis.evidence:
                evidence_count += 1
                nid = f"evidence:{paper.canonical_id}:{evidence.evidence_id}"
                evidence_node_by_id[evidence.evidence_id] = nid
                nodes[nid] = ScientificGraphNode(
                    node_id=nid,
                    node_type=GraphNodeType.EVIDENCE,
                    label=evidence.text,
                    paper_id=paper.canonical_id,
                    evidence_id=evidence.evidence_id,
                    epistemic_state=EpistemicState.MEASURED if evidence.strength.value == "direct" else EpistemicState.INFERRED,
                    properties={
                        "section": evidence.section,
                        "page": evidence.page,
                        "equation": evidence.equation,
                        "figure": evidence.figure,
                        "strength": evidence.strength.value,
                    },
                )
                edge = ScientificGraphEdge(
                    edge_id=_edge_id(paper_node_id, GraphRelation.CONTAINS.value, nid),
                    source_node_id=paper_node_id,
                    target_node_id=nid,
                    relation=GraphRelation.CONTAINS,
                    rationale="Evidence extracted from this paper.",
                )
                edges[edge.edge_id] = edge

            for claim in analysis.claims:
                claim_count += 1
                nid = f"claim:{paper.canonical_id}:{claim.claim_id}"
                nodes[nid] = ScientificGraphNode(
                    node_id=nid,
                    node_type=GraphNodeType.CLAIM,
                    label=claim.text,
                    paper_id=paper.canonical_id,
                    claim_id=claim.claim_id,
                    epistemic_state=_claim_state(claim.claim_type, claim.evidence_ids),
                    properties={
                        "claim_type": claim.claim_type,
                        "confidence": claim.confidence,
                    },
                )
                asserted = ScientificGraphEdge(
                    edge_id=_edge_id(nid, GraphRelation.ASSERTED_IN.value, paper_node_id),
                    source_node_id=nid,
                    target_node_id=paper_node_id,
                    relation=GraphRelation.ASSERTED_IN,
                    rationale="Claim was extracted from this paper.",
                )
                edges[asserted.edge_id] = asserted
                for evidence_id in claim.evidence_ids:
                    target = evidence_node_by_id.get(evidence_id)
                    if not target:
                        continue
                    support = ScientificGraphEdge(
                        edge_id=_edge_id(nid, GraphRelation.SUPPORTED_BY.value, target),
                        source_node_id=nid,
                        target_node_id=target,
                        relation=GraphRelation.SUPPORTED_BY,
                        confidence=claim.confidence,
                        rationale="Claim explicitly references this evidence record.",
                    )
                    edges[support.edge_id] = support

            for model in analysis.physical_model:
                nid = _node_id("model", paper.canonical_id, model)
                nodes[nid] = ScientificGraphNode(
                    node_id=nid,
                    node_type=GraphNodeType.MODEL,
                    label=model,
                    paper_id=paper.canonical_id,
                    epistemic_state=EpistemicState.DERIVED,
                )
                edge = ScientificGraphEdge(
                    edge_id=_edge_id(paper_node_id, GraphRelation.USES_MODEL.value, nid),
                    source_node_id=paper_node_id,
                    target_node_id=nid,
                    relation=GraphRelation.USES_MODEL,
                )
                edges[edge.edge_id] = edge

            for assumption in analysis.assumptions:
                nid = _node_id("assumption", paper.canonical_id, assumption)
                nodes[nid] = ScientificGraphNode(
                    node_id=nid,
                    node_type=GraphNodeType.ASSUMPTION,
                    label=assumption,
                    paper_id=paper.canonical_id,
                    epistemic_state=EpistemicState.INFERRED,
                )
                edge = ScientificGraphEdge(
                    edge_id=_edge_id(paper_node_id, GraphRelation.USES_ASSUMPTION.value, nid),
                    source_node_id=paper_node_id,
                    target_node_id=nid,
                    relation=GraphRelation.USES_ASSUMPTION,
                )
                edges[edge.edge_id] = edge

            for equation in analysis.equations:
                nid = _node_id("equation", paper.canonical_id, equation)
                nodes[nid] = ScientificGraphNode(
                    node_id=nid,
                    node_type=GraphNodeType.EQUATION,
                    label=equation,
                    paper_id=paper.canonical_id,
                    epistemic_state=EpistemicState.DERIVED,
                )
                edge = ScientificGraphEdge(
                    edge_id=_edge_id(paper_node_id, GraphRelation.USES_EQUATION.value, nid),
                    source_node_id=paper_node_id,
                    target_node_id=nid,
                    relation=GraphRelation.USES_EQUATION,
                )
                edges[edge.edge_id] = edge

            for diagnostic in analysis.diagnostics:
                nid = _node_id("diagnostic", paper.canonical_id, diagnostic)
                nodes[nid] = ScientificGraphNode(
                    node_id=nid,
                    node_type=GraphNodeType.DIAGNOSTIC,
                    label=diagnostic,
                    paper_id=paper.canonical_id,
                    epistemic_state=EpistemicState.OBSERVED,
                )
                edge = ScientificGraphEdge(
                    edge_id=_edge_id(paper_node_id, GraphRelation.USES_DIAGNOSTIC.value, nid),
                    source_node_id=paper_node_id,
                    target_node_id=nid,
                    relation=GraphRelation.USES_DIAGNOSTIC,
                )
                edges[edge.edge_id] = edge

        return GraphBuildResult(
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            paper_count=paper_count,
            claim_count=claim_count,
            evidence_count=evidence_count,
        )
