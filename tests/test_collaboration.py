from scientific_brain.collaboration import SECTION_KEYS, _parse_json_response


def test_collaborative_sections_cover_research_draft():
    assert SECTION_KEYS == (
        "abstract",
        "state_of_art",
        "research_question",
        "objectives",
        "development",
        "analysis",
        "conclusion",
    )


def test_parse_json_response_accepts_fenced_json():
    payload = _parse_json_response('```json\n{"sections": {"abstract": {"text": "x"}}}\n```')
    assert payload["sections"]["abstract"]["text"] == "x"
