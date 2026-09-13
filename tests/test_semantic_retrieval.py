from scientific_brain.semantic_retrieval import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    GeminiEmbeddingProvider,
    format_document,
    format_query,
)


def test_retrieval_prompt_formats_are_asymmetric():
    assert format_query("What controls the sheath velocity?") == (
        "task: question answering | query: What controls the sheath velocity?"
    )
    document = format_document("The sheath velocity increased with current.", "Plasma study")
    assert document.startswith("title: Plasma study | text: ")
    assert "task: question answering" not in document


def test_embedding_dimension_is_fixed_to_database_schema(monkeypatch):
    monkeypatch.setenv("SCIBRAIN_EMBEDDING_DIMENSIONS", "3072")
    provider = GeminiEmbeddingProvider(api_key="test-key")
    assert provider.dimensions == DEFAULT_EMBEDDING_DIMENSIONS == 768
