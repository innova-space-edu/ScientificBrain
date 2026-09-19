from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx


class InferenceTask(StrEnum):
    TEXT = "text"
    STRUCTURED = "structured"
    LONG_CONTEXT = "long_context"
    RESEARCH = "research"
    RETRIEVAL = "retrieval"
    CODE = "code"
    FAST = "fast"


DEFAULT_PROVIDER_ORDERS = {
    InferenceTask.TEXT.value: "google,nvidia,vertex-model-cloud,groq,openrouter,cerebras,together",
    InferenceTask.STRUCTURED.value: "google,nvidia,vertex-model-cloud,groq,openrouter,cerebras,together",
    InferenceTask.LONG_CONTEXT.value: "google,nvidia,vertex-model-cloud,openrouter,groq,cerebras,together",
    InferenceTask.RESEARCH.value: "google,nvidia,groq,openrouter",
    InferenceTask.RETRIEVAL.value: "google",
    InferenceTask.CODE.value: "google,nvidia,vertex-model-cloud,groq,cerebras,openrouter,together",
    InferenceTask.FAST.value: "google,nvidia,groq,openrouter,cerebras,together",
}

ORDER_ENV = {
    InferenceTask.TEXT.value: "EDUAI_AI_PROVIDER_ORDER_TEXT",
    InferenceTask.STRUCTURED.value: "EDUAI_AI_PROVIDER_ORDER_STRUCTURED",
    InferenceTask.LONG_CONTEXT.value: "EDUAI_AI_PROVIDER_ORDER_LONG_CONTEXT",
    InferenceTask.RESEARCH.value: "EDUAI_AI_PROVIDER_ORDER_RESEARCH",
    InferenceTask.RETRIEVAL.value: "EDUAI_AI_PROVIDER_ORDER_RETRIEVAL",
    InferenceTask.CODE.value: "EDUAI_AI_PROVIDER_ORDER_CODE",
    InferenceTask.FAST.value: "EDUAI_AI_PROVIDER_ORDER_TEXT",
}


def _timeout_seconds() -> float:
    raw = os.getenv("EDUAI_AI_PROVIDER_TIMEOUT_MS", "60000")
    try:
        return max(1.0, float(raw) / 1000.0)
    except ValueError:
        return 60.0


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _key_pool(prefix: str) -> list[str]:
    keys: list[str] = []
    for name in (prefix, f"{prefix}_1", f"{prefix}_2", f"{prefix}_3"):
        value = os.getenv(name)
        if value and value.strip() and value.strip() not in keys:
            keys.append(value.strip())
    return keys


@dataclass
class OllamaProvider:
    model: str = field(default_factory=lambda: os.getenv("SCIBRAIN_OLLAMA_MODEL", "qwen3:8b"))
    base_url: str = field(
        default_factory=lambda: os.getenv("SCIBRAIN_OLLAMA_URL", "http://127.0.0.1:11434")
    )
    temperature: float = 0.1
    timeout: float = 120.0
    provider_name: str = "ollama"

    def complete(self, system: str, user: str) -> str:
        response = httpx.post(
            self.base_url.rstrip("/") + "/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "options": {"temperature": self.temperature},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["message"]["content"]


@dataclass
class GeminiProvider:
    api_key: str
    model: str
    temperature: float = 0.1
    timeout: float = 60.0
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    provider_name: str = "google"

    def complete(self, system: str, user: str) -> str:
        model = self.model.removeprefix("models/")
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/models/{model}:generateContent",
            params={"key": self.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": self.temperature},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Google Gemini returned no candidates")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
        if not text.strip():
            raise RuntimeError("Google Gemini returned an empty response")
        return text


@dataclass
class OpenAICompatibleProvider:
    model: str
    base_url: str
    api_key: str | None = None
    temperature: float = 0.1
    timeout: float = 60.0
    provider_name: str = "openai-compatible"
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)

    def complete(self, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        body.update(self.extra_body)
        response = httpx.post(
            self.base_url.rstrip("/") + "/chat/completions",
            headers=headers,
            json=body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(f"{self.provider_name} returned no choices")
        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise RuntimeError(f"{self.provider_name} returned an empty response")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "") for item in content if isinstance(item, dict) and item.get("text")
            )
        return str(content)


@dataclass
class RoutedProvider:
    """Try providers in order without moving ScientificBrain memory between providers."""

    providers: list[object]
    task: str = InferenceTask.RESEARCH.value

    def complete(self, system: str, user: str) -> str:
        if not self.providers:
            raise RuntimeError(
                "No inference provider is configured. Add at least one cloud API key in the "
                "deployment environment, or explicitly enable local inference."
            )
        errors: list[str] = []
        for provider in self.providers:
            name = getattr(provider, "provider_name", type(provider).__name__)
            try:
                return provider.complete(system, user)  # type: ignore[attr-defined]
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}")
        raise RuntimeError("All configured inference providers failed: " + " | ".join(errors))

    def for_task(self, task: str | InferenceTask) -> "RoutedProvider":
        return build_cloud_router(str(task.value if isinstance(task, InferenceTask) else task))

    @property
    def configured_provider_names(self) -> list[str]:
        names: list[str] = []
        for provider in self.providers:
            name = str(getattr(provider, "provider_name", type(provider).__name__))
            if name not in names:
                names.append(name)
        return names


def _provider_order(task: str) -> list[str]:
    normalized = task.strip().lower().replace("-", "_")
    env_name = ORDER_ENV.get(normalized, ORDER_ENV[InferenceTask.RESEARCH.value])
    default = DEFAULT_PROVIDER_ORDERS.get(normalized, DEFAULT_PROVIDER_ORDERS[InferenceTask.RESEARCH.value])
    raw = os.getenv(env_name, default)
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _google_provider(task: str) -> GeminiProvider | None:
    key = _first_env("GEMINI_API_KEY_TEXT", "GEMINI_API_KEY")
    if not key:
        return None
    if task == InferenceTask.FAST.value:
        model = _first_env("GOOGLE_TEXT_MODEL_LITE", "GEMINI_TEXT_MODEL_LITE") or "gemini-3.5-flash-lite"
    else:
        model = _first_env("GOOGLE_TEXT_MODEL_PRIMARY", "GEMINI_TEXT_MODEL_PRIMARY") or "gemini-3.6-flash"
    return GeminiProvider(
        api_key=key,
        model=model,
        timeout=_timeout_seconds(),
        base_url=os.getenv(
            "GOOGLE_GENERATIVE_LANGUAGE_BASE",
            "https://generativelanguage.googleapis.com/v1beta",
        ),
    )


def _nvidia_provider(task: str) -> OpenAICompatibleProvider | None:
    key = _first_env("NVIDIA_API_KEY")
    if not key:
        return None
    model = _first_env("SCIBRAIN_NVIDIA_TEXT_MODEL") or "openai/gpt-oss-20b"
    return OpenAICompatibleProvider(
        model=model,
        base_url=os.getenv("SCIBRAIN_NVIDIA_API_BASE", "https://integrate.api.nvidia.com/v1"),
        api_key=key,
        timeout=_timeout_seconds(),
        provider_name="nvidia",
    )


def _groq_provider(task: str) -> OpenAICompatibleProvider | None:
    key = _first_env("GROQ_API_KEY")
    if not key:
        return None
    model = (
        _first_env("GROQ_RESEARCH_MODEL", "GROQ_TEXT_MODEL")
        if task == InferenceTask.RESEARCH.value
        else _first_env("GROQ_TEXT_MODEL", "GROQ_RESEARCH_MODEL")
    ) or "llama-3.3-70b-versatile"
    return OpenAICompatibleProvider(
        model=model,
        base_url=os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1"),
        api_key=key,
        timeout=_timeout_seconds(),
        provider_name="groq",
    )


def _openrouter_providers(task: str) -> list[OpenAICompatibleProvider]:
    keys = _key_pool("OPENROUTER_API_KEY")
    if not keys:
        return []
    if task == InferenceTask.STRUCTURED.value:
        model = _first_env("OPENROUTER_STRUCTURED_MODEL", "OPENROUTER_TEXT_MODEL") or "openrouter/auto"
    else:
        model = _first_env("OPENROUTER_TEXT_MODEL", "OPENROUTER_STRUCTURED_MODEL") or "openrouter/auto"

    headers: dict[str, str] = {}
    if referer := _first_env("OPENROUTER_REFERER"):
        headers["HTTP-Referer"] = referer
    if title := _first_env("OPENROUTER_APP_TITLE"):
        headers["X-Title"] = title

    provider_prefs: dict[str, Any] = {
        "sort": os.getenv("OPENROUTER_PROVIDER_SORT", "price"),
        "allow_fallbacks": True,
    }
    if not _truthy("OPENROUTER_ALLOW_DATA_COLLECTION", False):
        provider_prefs["data_collection"] = "deny"
    if _truthy("OPENROUTER_ZDR_ONLY", False):
        provider_prefs["zdr"] = True

    return [
        OpenAICompatibleProvider(
            model=model,
            base_url=os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1"),
            api_key=key,
            timeout=_timeout_seconds(),
            provider_name="openrouter",
            extra_headers=headers,
            extra_body={"provider": provider_prefs},
        )
        for key in keys
    ]


def _cerebras_provider() -> OpenAICompatibleProvider | None:
    key = _first_env("CEREBRAS_API_KEY")
    if not key:
        return None
    return OpenAICompatibleProvider(
        model=os.getenv("CEREBRAS_TEXT_MODEL", "gpt-oss-120b"),
        base_url=os.getenv("CEREBRAS_API_BASE", "https://api.cerebras.ai/v1"),
        api_key=key,
        timeout=_timeout_seconds(),
        provider_name="cerebras",
    )


def _together_providers() -> list[OpenAICompatibleProvider]:
    keys = _key_pool("TOGETHER_API_KEY")
    if not keys:
        return []
    return [
        OpenAICompatibleProvider(
            model=os.getenv("TOGETHER_TEXT_MODEL", "Qwen/Qwen3.5-9B"),
            base_url=os.getenv("TOGETHER_API_BASE", "https://api.together.xyz/v1"),
            api_key=key,
            timeout=_timeout_seconds(),
            provider_name="together",
        )
        for key in keys
    ]


def build_cloud_router(task: str = InferenceTask.RESEARCH.value) -> RoutedProvider:
    task = task.strip().lower().replace("-", "_")
    providers: list[object] = []
    for name in _provider_order(task):
        if name in {"google", "gemini"}:
            provider = _google_provider(task)
            if provider:
                providers.append(provider)
        elif name == "nvidia":
            provider = _nvidia_provider(task)
            if provider:
                providers.append(provider)
        elif name == "groq":
            provider = _groq_provider(task)
            if provider:
                providers.append(provider)
        elif name == "openrouter":
            providers.extend(_openrouter_providers(task))
        elif name == "cerebras":
            provider = _cerebras_provider()
            if provider:
                providers.append(provider)
        elif name == "together":
            providers.extend(_together_providers())
        elif name == "vertex-model-cloud":
            # Reserved to stay compatible with EDUAI routing. It is skipped until a
            # ScientificBrain Vertex endpoint implementation is explicitly configured.
            continue
        elif name in {"ollama", "local"} and _truthy("SCIBRAIN_ENABLE_LOCAL_FALLBACK", False):
            providers.append(OllamaProvider())

    if _truthy("SCIBRAIN_ENABLE_LOCAL_FALLBACK", False):
        if not any(getattr(p, "provider_name", "") == "ollama" for p in providers):
            providers.append(OllamaProvider())
    return RoutedProvider(providers=providers, task=task)


def provider_configuration_summary(task: str | None = None) -> dict[str, Any]:
    selected_task = (task or os.getenv("SCIBRAIN_DEFAULT_TASK", InferenceTask.RESEARCH.value)).lower()
    router = build_cloud_router(selected_task)
    return {
        "inference_mode": os.getenv("SCIBRAIN_INFERENCE_MODE", "cloud"),
        "task": selected_task,
        "provider_order": _provider_order(selected_task),
        "configured_providers": router.configured_provider_names,
        "local_fallback_enabled": _truthy("SCIBRAIN_ENABLE_LOCAL_FALLBACK", False),
        "vertex_model_cloud_enabled": _truthy("VERTEX_MODEL_CLOUD_ENABLED", False),
        "nvidia_scientific_tools_configured": bool(
            _first_env("NVIDIA_API_KEY", "NGC_API_KEY", "SCIBRAIN_NVIDIA_NIM_BASE_URL")
        ),
    }


def provider_from_env(kind: str | None = None, task: str | None = None):
    selected = (kind or os.getenv("SCIBRAIN_INFERENCE_MODE", "cloud")).strip().lower()
    selected_task = (task or os.getenv("SCIBRAIN_DEFAULT_TASK", InferenceTask.RESEARCH.value)).strip().lower()

    if selected in {"cloud", "online", "eduai", "router"}:
        return build_cloud_router(selected_task)
    if selected == "nvidia":
        provider = _nvidia_provider(selected_task)
        if provider is None:
            raise RuntimeError("NVIDIA_API_KEY is required for NVIDIA inference")
        return provider
    if selected in {"ollama", "local"}:
        return OllamaProvider()
    if selected in {"openai-compatible", "openai_compatible"}:
        base_url = _first_env("SCIBRAIN_API_BASE")
        model = _first_env("SCIBRAIN_MODEL")
        if not base_url or not model:
            raise RuntimeError(
                "SCIBRAIN_API_BASE and SCIBRAIN_MODEL are required for openai-compatible provider"
            )
        return OpenAICompatibleProvider(
            model=model,
            base_url=base_url,
            api_key=_first_env("SCIBRAIN_API_KEY"),
            timeout=_timeout_seconds(),
        )
    raise ValueError(f"Unknown provider kind: {selected}")
