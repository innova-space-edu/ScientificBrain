from scientific_brain.adaptive import (
    merge_chunk_analyses,
    plan_corpus,
    plan_review,
    profile_document,
)
from scientific_brain.models import Claim, Evidence, PaperAnalysis, PaperKind


def test_short_medium_and_long_review_plans():
    short = profile_document(["word " * 200 for _ in range(5)])
    medium = profile_document(["word " * 900 for _ in range(20)])
    long = profile_document(["word " * 1300 for _ in range(90)])

    assert plan_review(short).mode == "direct"
    assert plan_review(medium).mode in {"sectional", "hierarchical"}
    assert plan_review(long).mode == "hierarchical"
    assert len(plan_review(long).chunk_ranges) > len(plan_review(short).chunk_ranges)


def test_corpus_plan_changes_with_folder_size():
    assert plan_corpus(2).mode == "deep_small_corpus"
    assert plan_corpus(20).mode == "balanced"
    assert plan_corpus(80).mode == "batched"
    assert plan_corpus(150).mode == "large_corpus_hierarchical"


def test_chunk_merge_rewrites_evidence_ids_without_losing_claim_links():
    a1 = PaperAnalysis(
        paper_id="p",
        inferred_kind=PaperKind.EXPERIMENTAL,
        summary="first",
        evidence=[Evidence(evidence_id="e1", paper_id="p", text="A", page=1)],
        claims=[Claim(claim_id="c1", paper_id="p", text="claim A", evidence_ids=["e1"])],
    )
    a2 = PaperAnalysis(
        paper_id="p",
        inferred_kind=PaperKind.EXPERIMENTAL,
        summary="second",
        evidence=[Evidence(evidence_id="e1", paper_id="p", text="B", page=8)],
        claims=[Claim(claim_id="c1", paper_id="p", text="claim B", evidence_ids=["e1"])],
    )

    merged = merge_chunk_analyses("p", [a1, a2])

    assert len(merged.evidence) == 2
    assert merged.evidence[0].evidence_id != merged.evidence[1].evidence_id
    assert merged.claims[0].evidence_ids == [merged.evidence[0].evidence_id]
    assert merged.claims[1].evidence_ids == [merged.evidence[1].evidence_id]
