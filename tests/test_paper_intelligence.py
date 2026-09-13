from scientific_brain.fulltext import FullTextDocument, TextPage
from scientific_brain.paper_intelligence import build_structure, chunk_document, extract_text_assets


def sample_document():
    return FullTextDocument(
        paper_id="doi:10.1/test",
        source_url="memory://test.pdf",
        pages=[
            TextPage(1, "INTRODUCTION\nA short scientific introduction.\nFigure 1: Current versus time for the discharge.\nI = C dV/dt"),
            TextPage(2, "2. Methods\nThe experiment used a calibrated probe.\nTable 1: Main operating parameters.\nE = 1/2 C V^2"),
        ],
    )


def test_structure_detects_headings():
    structure = build_structure(sample_document())
    titles = [x["title"] for x in structure["headings"]]
    assert "INTRODUCTION" in titles
    assert any("Methods" in x for x in titles)


def test_chunking_preserves_pages():
    chunks = chunk_document(sample_document(), target_chars=80, overlap_chars=10)
    assert chunks
    assert {c["page_start"] for c in chunks} == {1, 2}
    assert all(c["page_start"] == c["page_end"] for c in chunks)


def test_assets_extract_figures_tables_and_equations():
    assets = extract_text_assets(sample_document())
    kinds = [a["asset_type"] for a in assets]
    assert "figure_caption" in kinds
    assert "table_caption" in kinds
    assert kinds.count("equation_candidate") >= 2
