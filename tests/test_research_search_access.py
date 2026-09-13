from scientific_brain.research_search import ResearchSearchService, _merge_results


def test_duplicate_merge_keeps_open_access_route():
    left = {
        "title": "Example paper",
        "doi": "10.1000/example",
        "access_status": "metadata_only",
        "manual_lookup_required": True,
    }
    right = {
        "title": "Example paper",
        "doi": "10.1000/example",
        "arxiv_id": "2601.12345",
        "pdf_url": "https://arxiv.org/pdf/2601.12345",
        "access_status": "open_access",
        "is_open_access": True,
        "manual_lookup_required": False,
    }
    merged = _merge_results(left, right)
    assert merged["access_status"] == "open_access"
    assert merged["pdf_url"].startswith("https://arxiv.org/pdf/")
    assert merged["manual_lookup_required"] is False


def test_researchgate_page_is_public_page_not_open_access(monkeypatch):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    service = ResearchSearchService()
    row = {
        "title": "Example",
        "url": "https://www.researchgate.net/publication/12345_Example",
        "access_status": "metadata_only",
        "is_open_access": False,
    }
    service._resolve_access(row)
    assert row["access_status"] == "public_page"
    assert row["manual_lookup_required"] is True
    assert row.get("pdf_url") is None


def test_direct_public_pdf_is_not_mislabeled_open_access(monkeypatch):
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    monkeypatch.delenv("OPENALEX_MAILTO", raising=False)
    service = ResearchSearchService()
    row = {
        "title": "Public PDF",
        "url": "https://example.org/manuscript.pdf",
        "access_status": "metadata_only",
        "is_open_access": False,
    }
    service._resolve_access(row)
    assert row["access_status"] == "public_full_text"
    assert row["is_public_full_text"] is True
    assert row["manual_lookup_required"] is False
