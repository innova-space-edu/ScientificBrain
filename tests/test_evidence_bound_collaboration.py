from scientific_brain.evidence_bound_collaboration import (
    section_citation_gate,
    targeted_query_from_brief,
)


def test_targeted_query_uses_problem_questions_and_mechanisms():
    query = targeted_query_from_brief({
        "topic": "plasma propulsion",
        "problem_statement": "identify impulse mechanism",
        "questions": ["What controls Ibit?", "Which observable discriminates models?"],
        "mechanisms_or_comparisons": "current sheath versus ablation",
    })
    assert "plasma propulsion" in query
    assert "What controls Ibit?" in query
    assert "current sheath versus ablation" in query


def test_state_of_art_requires_a_valid_citation():
    gate = section_citation_gate(
        "state_of_art",
        {"text": "Established mechanism without a source.", "refs": []},
        {1, 2},
    )
    assert gate["passed"] is False
    assert gate["evidence_required"] is True


def test_visible_reference_must_match_declared_section_refs():
    gate = section_citation_gate(
        "analysis",
        {"text": "The trend was reported [2].", "refs": [1]},
        {1, 2},
    )
    assert gate["passed"] is False
    assert gate["visible_refs_missing_from_section_refs"] == [2]


def test_future_work_can_be_an_explicit_uncited_proposal():
    gate = section_citation_gate(
        "future_work",
        {"text": "We propose measuring a discriminating observable.", "refs": []},
        {1, 2},
    )
    assert gate["passed"] is True
    assert gate["evidence_required"] is False


def test_invalid_reference_is_rejected():
    gate = section_citation_gate(
        "development",
        {"text": "A quantitative result is reported [9].", "refs": [9]},
        {1, 2},
    )
    assert gate["passed"] is False
    assert gate["invalid_refs"] == [9]
