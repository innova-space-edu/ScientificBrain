from pathlib import Path

from scientific_brain.corpus_intelligence_v174 import _query_terms


def test_project_session_is_persisted_before_artifact():
    source = Path("scientific_brain/project_service.py").read_text(encoding="utf-8")
    state_pos = source.index("self.snapshot_store.save_state")
    artifact_pos = source.index("self.snapshot_store.save_artifact")
    assert state_pos < artifact_pos


def test_spanish_corpus_query_terms_expand_for_legacy_evidence_ranking():
    terms = _query_terms("que mecanismos explican los impulsos de los propulsores")
    assert "mechanism" in terms
    assert "impulse" in terms
    assert "thruster" in terms
