from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx


@dataclass
class OllamaProvider:
    model: str = field(default_factory=lambda: os.getenv("SCIBRAIN_OLLAMA_MODEL", "qwen3:8b"))
    base_url: str = field(default_factory=lambda: os.getenv("SCIBRAIN_OLLAMA_URL", "http://127.0.0.1:11434"))
    temperature: float = 0.1
    timeout: float = 120.0

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
class OpenAICompatibleProvider:
    model: str
    base_url: str
    api_key: str | None = None
    temperature: float = 0.1
    timeout: float = 120.0

    def complete(self, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json"}
        key = self.api_key or os.getenv("SCIBRAIN_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        response = httpx.post(
            self.base_url.rstrip("/") + "/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]


@dataclass
class RoutedProvider:
    """Try providers in order without moving ScientificBrain's memory between providers."""

    providers: list[object]

    def complete(self, system: str, user: str) -> str:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.complete(system, user)  # type: ignore[attr-defined]
            except Exception as exc:
                errors.append(f"{type(provider).__name__}: {exc}")
        raise RuntimeError("All configured LLM providers failed: " + " | ".join(errors))


def provider_from_env(kind: str = "ollama"):
    kind = kind.lower()
    if kind == "ollama":
        return OllamaProvider()
    if kind in {"openai-compatible", "openai_compatible"}:
        base_url = os.getenv("SCIBRAIN_API_BASE")
        model = os.getenv("SCIBRAIN_MODEL")
        if not base_url or not model:
            raise RuntimeError(
                "SCIBRAIN_API_BASE and SCIBRAIN_MODEL are required for openai-compatible provider"
            )
        return OpenAICompatibleProvider(
            model=model,
            base_url=base_url,
            api_key=os.getenv("SCIBRAIN_API_KEY"),
        )
    raise ValueError(f"Unknown provider kind: {kind}")
