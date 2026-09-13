from scientific_brain.visual_sweep import prioritize_visual_pages


def test_visual_sweep_prioritizes_captioned_scientific_pages():
    assets = [
        {"page": 2, "asset_type": "visual_page_inventory", "metadata": {"embedded_image_count": 1}},
        {"page": 7, "asset_type": "figure_caption", "metadata": {}},
        {"page": 5, "asset_type": "table_caption", "metadata": {}},
        {"page": 9, "asset_type": "visual_page_inventory", "metadata": {"vector_drawing_count": 80}},
    ]
    pages = prioritize_visual_pages(assets, max_pages=4)
    assert pages[0] == 7
    assert 5 in pages
    assert 9 in pages


def test_visual_sweep_does_not_repeat_already_analyzed_page():
    assets = [
        {"page": 3, "asset_type": "figure_caption", "metadata": {}},
        {"page": 3, "asset_type": "visual_analysis", "metadata": {"automatic": True}},
        {"page": 4, "asset_type": "table_caption", "metadata": {}},
    ]
    assert prioritize_visual_pages(assets, max_pages=4) == [4]
