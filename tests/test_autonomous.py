from scientific_brain.adaptive_collaboration import _reference_text, _stable_source_id
from scientific_brain.autonomous_jobs import _retryable


def test_source_identity_and_reference_are_stable():
    paper = {
        "canonical_id": "doi:10.1234/example",
        "title": "Example paper",
        "authors": ["A. Author", "B. Author"],
        "journal": "Journal",
        "publication_date": "2026-01-02",
        "doi": "10.1234/example",
    }
    assert _stable_source_id(paper) == _stable_source_id(dict(paper))
    ref = _reference_text(paper, 3)
    assert ref.startswith("[3]")
    assert "10.1234/example" in ref


def test_retry_classifier_does_not_loop_on_structural_pdf_error():
    assert not _retryable(ValueError("PDF contains no extractable text; a layout/OCR parser is required"))
    assert _retryable(RuntimeError("temporary provider timeout"))
