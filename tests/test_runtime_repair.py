from scientific_brain.adaptive_collaboration import _stable_source_id
from scientific_brain.bounded_search import BoundedResearchSearchService


def test_stable_source_id_is_order_independent():
    paper = {"canonical_id": "doi:10.1000/example", "title": "Example"}
    assert _stable_source_id(paper) == _stable_source_id(dict(paper))
    assert _stable_source_id(paper).startswith("P")


def test_bounded_search_caps_unpaywall_budget(monkeypatch):
    service = BoundedResearchSearchService()
    service.email = "test@example.org"
    calls = []
    monkeypatch.setattr("scientific_brain.bounded_search.unpaywall_pdf_url", lambda doi, email, timeout: calls.append((doi, timeout)) or None)
    for i in range(20):
        service._resolve_access({"title": f"Paper {i}", "result_type": "paper", "source": "crossref", "doi": f"10.1000/{i}", "url": f"https://doi.org/10.1000/{i}"})
    assert len(calls) == service.max_unpaywall_lookups
    assert all(timeout == service.unpaywall_timeout_seconds for _, timeout in calls)
