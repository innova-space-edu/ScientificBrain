from scientific_brain.providers import (
    InferenceTask,
    build_cloud_router,
    provider_configuration_summary,
    provider_from_env,
)


def _clear_provider_env(monkeypatch):
    names = [
        "GEMINI_API_KEY",
        "GEMINI_API_KEY_TEXT",
        "GROQ_API_KEY",
        "NVIDIA_API_KEY",
        "OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY_1",
        "OPENROUTER_API_KEY_2",
        "OPENROUTER_API_KEY_3",
        "CEREBRAS_API_KEY",
        "TOGETHER_API_KEY",
        "TOGETHER_API_KEY_1",
        "TOGETHER_API_KEY_2",
        "TOGETHER_API_KEY_3",
        "SCIBRAIN_ENABLE_LOCAL_FALLBACK",
        "SCIBRAIN_INFERENCE_MODE",
    ]
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_cloud_is_default_inference_mode(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    provider = provider_from_env(task="research")
    assert provider.task == "research"
    assert provider.configured_provider_names == ["google"]


def test_eduai_research_order(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "google-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    router = build_cloud_router(InferenceTask.RESEARCH.value)
    assert router.configured_provider_names == ["google", "groq", "openrouter"]


def test_local_model_is_optional(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "google-key")
    router = build_cloud_router("research")
    assert "ollama" not in router.configured_provider_names

    monkeypatch.setenv("SCIBRAIN_ENABLE_LOCAL_FALLBACK", "true")
    router = build_cloud_router("research")
    assert router.configured_provider_names[-1] == "ollama"


def test_provider_status_never_exposes_keys(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "do-not-leak-this")
    summary = provider_configuration_summary("research")
    rendered = str(summary)
    assert "do-not-leak-this" not in rendered
    assert summary["inference_mode"] == "cloud"
