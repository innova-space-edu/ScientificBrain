from scientific_brain.professional_exports import _docx, _pdf, _ris


def sample_document():
    return {
        "topic": "Plasma propulsion",
        "sections": {"abstract": {"text": "Evidence-bound abstract [1]."}},
        "evidence_manifest": {"sources": [{"citation_number": 1, "title": "Paper", "authors": ["A. Author"], "publication_date": "2025-01-01", "doi": "10.1/example", "reference": "[1] A. Author. Paper. 2025."}]},
    }


def test_ris_contains_reference_fields():
    text = _ris(sample_document())
    assert "TY  - JOUR" in text and "TI  - Paper" in text and "DO  - 10.1/example" in text


def test_binary_exports_have_expected_signatures():
    docx = _docx(sample_document())
    pdf = _pdf(sample_document())
    assert docx[:2] == b"PK"
    assert pdf[:4] == b"%PDF"
