from scientific_brain.state_of_art import build_state_of_art_matrix


def test_state_of_art_matrix_keeps_provenance_and_separates_fields():
    papers = [
        {
            "canonical_id": "p1",
            "title": "Paper one",
            "publication_date": "2025-01-01",
            "journal": "J",
            "review_depth": "full_text_reviewed",
            "analysis": {
                "inferred_kind": "experimental",
                "plasma_regime": ["pulsed"],
                "physical_model": ["Lorentz-force model"],
                "experimental_parameters": {"C": "225 nF", "V": "3 kV"},
                "diagnostics": ["fast imaging"],
                "uncertainty": ["current uncertainty ±0.1 kA"],
                "limitations": ["thrust not directly measured"],
                "equations": ["I = V sqrt(C/L)"],
                "evidence": [
                    {"evidence_id": "e1", "text": "Peak current was measured.", "page": 13, "section": "Results", "strength": "direct"}
                ],
                "claims": [
                    {"claim_id": "c1", "text": "Peak current increased.", "claim_type": "result", "evidence_ids": ["e1"], "confidence": 0.9}
                ],
            },
            "critique": {"proposed_tests": ["measure impulse bit"]},
            "specialist_reviews": [],
        },
        {
            "canonical_id": "p2",
            "title": "Paper two",
            "review_depth": "full_text_reviewed",
            "analysis": {
                "plasma_regime": ["pulsed"],
                "physical_model": ["Lorentz-force model"],
                "experimental_parameters": {"V": "2 kV"},
                "diagnostics": ["fast imaging"],
                "evidence": [],
                "claims": [],
            },
        },
        {"canonical_id": "p3", "title": "Metadata only", "review_depth": "metadata_verified"},
    ]
    result = build_state_of_art_matrix(papers)
    assert result["coverage"]["full_text_papers"] == 2
    assert result["coverage"]["skipped_or_not_full_text"] == 1
    first = result["rows"][0]
    assert first["results"][0]["evidence"][0]["page"] == 13
    assert first["limitations"] == ["thrust not directly measured"]
    assert first["variables"][0]["name"] == "C"
    shared = result["recurring_dimensions"]
    assert shared["mechanisms"][0]["paper_count"] == 2
    assert shared["diagnostics"][0]["paper_count"] == 2
    assert result["fingerprint"]
