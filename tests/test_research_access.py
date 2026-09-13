from scientific_brain.research_search import _classify_web_access


def test_researchgate_is_public_copy_not_oa():
    row = {"url": "https://www.researchgate.net/publication/123_test"}
    _classify_web_access(row)
    assert row["access_kind"] == "public_copy"
    assert row["access_status"] == "manual_download"
    assert row["system_can_read"] is False
    assert "ResearchGate" in row["access_label"]


def test_direct_public_pdf_is_readable_but_not_silently_oa():
    row = {"url": "https://example.edu/papers/test.pdf"}
    _classify_web_access(row)
    assert row["access_kind"] == "public_pdf"
    assert row["system_can_read"] is True
    assert row["access_kind"] != "open_access"
