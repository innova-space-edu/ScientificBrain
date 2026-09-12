from datetime import date

from scientific_brain.memory import ScientificMemory
from scientific_brain.models import (
    Claim,
    Evidence,
    Paper,
    PaperAnalysis,
    ReviewDepth,
)
from scientific_brain.taxonomy import classify_topics


def test_memory_roundtrip(tmp_path):
    memory = ScientificMemory(tmp_path / "brain.db")
    paper = Paper(
        canonical_id="doi:10.0000/test",
        title="Gyrokinetic turbulence in a tokamak plasma",
        abstract="A test of turbulent transport.",
        publication_date=date(2025, 1, 1),
        doi="10.0000/test",
        plasma_topics=["gyrokinetics", "turbulence_transport"],
        source="test",
    )
    memory.upsert_paper(paper)
    assert memory.stats()["papers"] == 1
    assert memory.search("gyrokinetic")[0]["canonical_id"] == paper.canonical_id
    assert memory.get_review_status(paper.canonical_id)["review_depth"] == ReviewDepth.METADATA.value

    evidence = Evidence(
        evidence_id="e1",
        paper_id=paper.canonical_id,
        text="The measured transport decreased.",
        section="Results",
        page=4,
    )
    claim = Claim(
        claim_id="c1",
        paper_id=paper.canonical_id,
        text="Transport decreased.",
        claim_type="result",
        evidence_ids=["e1"],
        confidence=0.9,
    )
    analysis = PaperAnalysis(
        paper_id=paper.canonical_id,
        review_depth=ReviewDepth.FULL_TEXT,
        physical_model=["gyrokinetic"],
        assumptions=["electrostatic limit"],
        uncertainty=["reported statistical uncertainty"],
        reproducibility=["input parameters listed"],
        evidence=[evidence],
        claims=[claim],
    )
    memory.save_analysis(analysis)
    loaded = memory.get_analysis(paper.canonical_id)
    assert loaded is not None
    assert loaded.claims[0].evidence_ids == ["e1"]
    assert memory.stats()["analyses"] == 1
    assert memory.get_review_status(paper.canonical_id)["review_depth"] == ReviewDepth.FULL_TEXT.value
    memory.close()


def test_topic_classification():
    taxonomy = {"domains": {"reconnection": {"keywords": ["magnetic reconnection"]}}}
    assert classify_topics("Fast magnetic reconnection in plasma", taxonomy) == ["reconnection"]
