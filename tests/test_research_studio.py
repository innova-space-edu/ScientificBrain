from scientific_brain.studio import _clean_sections, _extract_json


def test_extract_json_from_fenced_response():
    payload = _extract_json('```json\n{"title":"x","sections":{}}\n```')
    assert payload["title"] == "x"


def test_clean_sections_keeps_only_known_sections():
    sections = _clean_sections({
        "resumen": {"content": "Texto", "source_refs": ["doi:10.1/x"]},
        "invented": {"content": "no"},
    })
    assert sections["resumen"]["content"] == "Texto"
    assert "invented" not in sections
