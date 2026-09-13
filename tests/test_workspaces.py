from scientific_brain.research_search import _clean_doi, _manual_message
from scientific_brain.workspaces import _canonical_id


def test_canonical_id_prefers_doi():
    value = _canonical_id({"doi": "https://doi.org/10.1234/ABC"})
    assert value == "doi:10.1234/abc"


def test_canonical_id_uses_arxiv():
    assert _canonical_id({"arxiv_id": "2601.01234"}) == "arxiv:2601.01234"


def test_user_upload_gets_private_canonical_id():
    value = _canonical_id({})
    assert value.startswith("userdoc:")


def test_doi_cleanup():
    assert _clean_doi("https://doi.org/10.1000/test") == "10.1000/test"


def test_manual_lookup_includes_doi_and_explains_unconfirmed_oa():
    msg = _manual_message({"doi": "10.1000/test", "url": "https://example.org/paper"})
    assert "10.1000/test" in msg
    assert "Open Access no confirmado" in msg
