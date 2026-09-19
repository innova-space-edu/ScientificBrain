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


def test_physics_toolkit_keeps_future_extensions():
    manifest = physics_toolkit_manifest()
    assert len(manifest["skills"]) == 15
    assert "PIC/hybrid routing" in manifest["planned_extensions"]
    assert "active learning" in manifest["planned_extensions"]
    assert "direct ScientificBrain orchestration" in manifest["planned_extensions"]


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
