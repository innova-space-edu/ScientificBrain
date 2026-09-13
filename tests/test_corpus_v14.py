from scientific_brain.corpus_intelligence import (
    _parse_json_response,
    audit_citations,
    citation_numbers_in_text,
)
from scientific_brain.literature_watch import result_key


def test_corpus_json_parser_accepts_fenced_payload():
    parsed = _parse_json_response('```json\n{"answer":"ok","claims":[]}\n```')
    assert parsed["answer"] == "ok"


def test_visible_citation_parser_ignores_page_number():
    assert citation_numbers_in_text("Resultado [2, p. 7] y comparación [1,3].") == {1, 2, 3}


def test_citation_audit_blocks_unknown_and_uncited_claims():
    audit = audit_citations(
        "La tendencia aumenta [1] pero aparece otra fuente [9].",
        [
            {"claim": "La tendencia aumenta", "refs": [1]},
            {"claim": "Hay una segunda causa", "refs": []},
        ],
        {1, 2},
    )
    assert audit["passed"] is False
    assert audit["invalid_reference_numbers"] == [9]
    assert audit["uncited_claims"] == ["Hay una segunda causa"]


def test_citation_audit_passes_grounded_inventory():
    audit = audit_citations(
        "Una fuente reporta A [1]; otra reporta B [2, p. 4].",
        [
            {"claim": "Una fuente reporta A", "refs": [1]},
            {"claim": "Otra fuente reporta B", "refs": [2]},
        ],
        {1, 2},
    )
    assert audit["passed"] is True


def test_literature_watch_result_key_prefers_doi_then_title():
    assert result_key({"doi": "https://doi.org/10.1000/ABC", "title": "Ignored"}) == "doi:10.1000/abc"
    key = result_key({"title": "A Plasma Propulsion Study"})
    assert key.startswith("title:aplasmapropulsionstudy")
