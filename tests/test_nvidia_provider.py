import json

from scientific_brain.nvidia_provider import (
    NvidiaProvider,
    nvidia_configuration_summary,
    physics_toolkit_manifest,
)


def _clear(monkeypatch):
    for name in [
        "NVIDIA_API_KEY",
        "NGC_API_KEY",
        "SCIBRAIN_NVIDIA_NIM_BASE_URL",
        "SCIBRAIN_NVIDIA_NIM_MODEL",
        "SCIBRAIN_NVIDIA_NIM_API_KEY",
        "SCIBRAIN_NVIDIA_CAPABILITIES_JSON",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_status_never_exposes_nvidia_keys(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-do-not-leak")
    monkeypatch.setenv("NGC_API_KEY", "ngc-do-not-leak")
    status = nvidia_configuration_summary()
    rendered = json.dumps(status)
    assert "nvapi-do-not-leak" not in rendered
    assert "ngc-do-not-leak" not in rendered
    assert status["hosted_api_configured"] is True
    assert status["ngc_key_configured"] is True


def test_physics_toolkit_exposes_expanded_stack():
    manifest = physics_toolkit_manifest()
    assert manifest["version"] == "0.3.0"
    assert len(manifest["skills"]) == 44
    assert "PIC/hybrid routing" in manifest["implemented_extensions"]
    assert "active learning" in manifest["implemented_extensions"]
    assert "direct ScientificBrain orchestration" in manifest["implemented_extensions"]
    assert "physics-wide model routing" in manifest["implemented_extensions"]
    assert "independent observable-level validation" in manifest["implemented_extensions"]
    assert "physics-model-router" in manifest["skills"]
    assert "physics-validator" in manifest["skills"]


def test_custom_capability_is_server_configured(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(
        "SCIBRAIN_NVIDIA_CAPABILITIES_JSON",
        json.dumps({
            "bionemo-demo": {
                "domain": "bionemo",
                "description": "Configured BioNeMo NIM",
                "endpoint": "https://example.invalid/v1/infer",
                "auth": "nvidia",
            }
        }),
    )
    caps = NvidiaProvider.from_env().capabilities()
    assert any(item["name"] == "bionemo-demo" for item in caps)
    assert all("endpoint" not in item for item in caps)


def test_hosted_complete_uses_openai_compatible_endpoint(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "physics response"}}]}

    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        return Response()

    monkeypatch.setattr("scientific_brain.nvidia_provider.httpx.post", fake_post)
    provider = NvidiaProvider.from_env()
    assert provider.complete("system", "question") == "physics response"
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer nvapi-test"


def test_status_ignores_invalid_custom_endpoint(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(
        "SCIBRAIN_NVIDIA_CAPABILITIES_JSON",
        json.dumps({
            "broken": {
                "domain": "physics",
                "endpoint": "PLACEHOLDER",
                "auth": "nvidia",
            }
        }),
    )
    status = NvidiaProvider.from_env().status()
    assert status["capabilities"] == []
    assert status["configuration_warnings"]
    assert "broken" in status["configuration_warnings"][0]


def test_model_catalog_uses_nvidia_models_endpoint(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"data": [{"id": "openai/gpt-oss-20b"}, {"id": "meta/llama-3.3-70b-instruct"}]}

    monkeypatch.setattr("scientific_brain.nvidia_provider.httpx.get", lambda *args, **kwargs: Response())
    result = NvidiaProvider.from_env().models_status()
    assert result["configured"] is True
    assert "meta/llama-3.3-70b-instruct" in result["models"]
    assert result["source"] == "nvidia-v1-models"


def test_invoke_can_select_model_from_catalog(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    provider = NvidiaProvider.from_env()
    monkeypatch.setattr(provider, "models_status", lambda: {"models": ["openai/gpt-oss-20b", "meta/llama-3.3-70b-instruct"]})
    captured = {}
    def fake_chat(**kwargs):
        captured["model"] = kwargs["model"]
        return "ok"
    monkeypatch.setattr(provider, "_chat", fake_chat)
    result = provider.invoke("nvidia-chat", {"prompt": "test", "model": "meta/llama-3.3-70b-instruct"})
    assert result["model"] == "meta/llama-3.3-70b-instruct"
    assert captured["model"] == "meta/llama-3.3-70b-instruct"
