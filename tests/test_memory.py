from datetime import date

from scientific_brain.memory import ScientificMemory
from scientific_brain.models import Paper
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
    memory.close()


def test_topic_classification():
    taxonomy = {"domains": {"reconnection": {"keywords": ["magnetic reconnection"]}}}
    assert classify_topics("Fast magnetic reconnection in plasma", taxonomy) == ["reconnection"]
