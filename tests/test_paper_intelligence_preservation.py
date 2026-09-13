from scientific_brain.paper_intelligence import _DERIVED_ASSET_TYPES


def test_reindex_preserves_model_generated_and_ocr_provenance_assets():
    assert "visual_analysis" not in _DERIVED_ASSET_TYPES
    assert "ocr_page" not in _DERIVED_ASSET_TYPES
    assert "figure_caption" in _DERIVED_ASSET_TYPES
    assert "visual_page_inventory" in _DERIVED_ASSET_TYPES
