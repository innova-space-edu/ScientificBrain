from datetime import date

from scientific_brain.corpus import audit_corpus
from scientific_brain.memory import ScientificMemory
from scientific_brain.models import Paper, PaperKind


def test_corpus_audit_counts_methods_and_time(tmp_path):
    memory = ScientificMemory(tmp_path / "brain.db")
    memory.upsert_paper(Paper(
        canonical_id="doi:a",
        title="Experiment",
        publication_date=date(2025, 1, 1),
        doi="a",
        kind=PaperKind.EXPERIMENTAL,
        plasma_topics=["diagnostics"],
        source="test",
    ))
    policy = {
        "target_papers": 1,
        "requirements": {
            "minimum_recent_papers_2024_plus": 1,
            "minimum_reviews_or_roadmaps": 0,
            "minimum_experimental": 1,
            "minimum_simulation": 0,
            "minimum_theoretical": 0,
            "deep_analysis_count": 0,
        },
    }
    audit = audit_corpus(memory, policy)
    assert audit.total_papers == 1
    assert audit.method_counts["experimental"] == 1
    assert audit.time_counts["recent_2024_plus"] == 1
    assert audit.passed
    memory.close()
