from datetime import date

from scientific_brain.graph_builder import ScientificGraphBuilder
from scientific_brain.graph_models import GraphNodeType, GraphRelation
from scientific_brain.models import Claim, Evidence, Paper, PaperAnalysis, ReviewDepth


def _bundle():
    paper = Paper(
        canonical_id="doi:10.1000/test",
        title="Magnetized plasma experiment",
        publication_date=date(2025, 1, 1),
        doi="10.1000/test",
        plasma_topics=["shock_physics"],
        source="test",
    )
    evidence = Evidence(
        evidence_id="e1",
        paper_id=paper.canonical_id,
        text="The measured shock velocity was 42 km/s.",
        section="Results",
        page=6,
    )
    claim = Claim(
        claim_id="c1",
        paper_id=paper.canonical_id,
        text="The shock velocity reaches 42 km/s.",
        claim_type="result",
        evidence_ids=["e1"],
        confidence=0.91,
    )
    analysis = PaperAnalysis(
        paper_id=paper.canonical_id,
        review_depth=ReviewDepth.FULL_TEXT,
        physical_model=["resistive MHD"],
        assumptions=["quasi-neutrality"],
        equations=["Ohm law with resistive term"],
        diagnostics=["interferometry"],
        evidence=[evidence],
        claims=[claim],
    )
    return {"record": paper.model_dump(mode="json"), "analysis": analysis.model_dump(mode="json")}


def test_graph_builder_preserves_claim_evidence_provenance():
    result = ScientificGraphBuilder().build([_bundle()])
    assert result.paper_count == 1
    assert result.claim_count == 1
    assert result.evidence_count == 1

    types = {node.node_type for node in result.nodes}
    assert GraphNodeType.PAPER in types
    assert GraphNodeType.CLAIM in types
    assert GraphNodeType.EVIDENCE in types
    assert GraphNodeType.MODEL in types
    assert GraphNodeType.ASSUMPTION in types
    assert GraphNodeType.EQUATION in types
    assert GraphNodeType.DIAGNOSTIC in types

    relations = {edge.relation for edge in result.edges}
    assert GraphRelation.ASSERTED_IN in relations
    assert GraphRelation.SUPPORTED_BY in relations
    assert GraphRelation.CONTAINS in relations

    claim_node = next(node for node in result.nodes if node.node_type == GraphNodeType.CLAIM)
    evidence_node = next(node for node in result.nodes if node.node_type == GraphNodeType.EVIDENCE)
    support = next(edge for edge in result.edges if edge.relation == GraphRelation.SUPPORTED_BY)
    assert support.source_node_id == claim_node.node_id
    assert support.target_node_id == evidence_node.node_id


def test_graph_builder_skips_metadata_only_bundle_without_analysis():
    paper = Paper(canonical_id="doi:10.1000/metadata", title="Metadata only", source="test")
    result = ScientificGraphBuilder().build([{"record": paper.model_dump(mode="json"), "analysis": None}])
    assert result.paper_count == 0
    assert not result.nodes
    assert not result.edges
