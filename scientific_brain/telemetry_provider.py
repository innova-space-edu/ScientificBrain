from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from .auth import AuthenticatedUser
from .providers import GeminiProvider, OllamaProvider, OpenAICompatibleProvider, RoutedProvider
from .usage import UsageRecorder


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _pricing() -> dict[str, Any]:
    raw = os.getenv("SCIBRAIN_MODEL_PRICING_JSON", "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def estimate_cost_usd(provider: str, model: str, input_tokens: int, output_tokens: int, reported_cost: Any = None) -> tuple[float | None, str | None]:
    exact = _number(reported_cost)
    if exact is not None:
        return max(0.0, exact), "provider_reported"
    price_map = _pricing()
    entry = price_map.get(f"{provider}:{model}") or price_map.get(model) or price_map.get(provider)
    if not isinstance(entry, dict):
        return None, None
    input_rate = _number(entry.get("input_per_million"))
    output_rate = _number(entry.get("output_per_million"))
    if input_rate is None and output_rate is None:
        return None, None
    total = (input_tokens / 1_000_000.0) * float(input_rate or 0.0)
    total += (output_tokens / 1_000_000.0) * float(output_rate or 0.0)
    return round(total, 10), "configured_rate"


def _usage_metadata(provider: str, model: str, usage: dict[str, Any], *, exact: bool, task: str, operation: str, attempts: int) -> dict[str, Any]:
    input_tokens = _integer(usage.get("input_tokens"))
    output_tokens = _integer(usage.get("output_tokens"))
    total_tokens = _integer(usage.get("total_tokens")) or input_tokens + output_tokens
    cost, cost_source = estimate_cost_usd(provider, model, input_tokens, output_tokens, usage.get("reported_cost_usd"))
    metadata = {
        "provider": provider,
        "model": model,
        "task": task,
        "operation": operation,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "usage_exact": bool(exact),
        "attempts": attempts,
        "cached_input_tokens": _integer(usage.get("cached_input_tokens")),
        "reasoning_tokens": _integer(usage.get("reasoning_tokens")),
    }
    if cost is not None:
        metadata["cost_usd"] = cost
        metadata["estimated_cost_usd"] = cost
        metadata["cost_source"] = cost_source
    return metadata


@dataclass
class TelemetryProvider:
    """Usage-aware provider adapter.

    It preserves ScientificBrain's existing routing configuration while capturing provider-reported
    token usage. Pricing is never invented: cost is stored only when a provider reports it or when
    SCIBRAIN_MODEL_PRICING_JSON explicitly configures a rate for the provider/model.
    """

    provider: object
    user: AuthenticatedUser
    folder_id: str | None = None
    operation: str = "ai_completion"
    document_id: str | None = None
    paper_id: str | None = None

    def __post_init__(self) -> None:
        self.recorder = UsageRecorder(self.user, self.folder_id)
        self.last_usage: dict[str, Any] = {}

    @property
    def task(self) -> str:
        return str(getattr(self.provider, "task", "research"))

    @contextmanager
    def operation_context(self, operation: str, *, document_id: str | None = None, paper_id: str | None = None):
        previous = (self.operation, self.document_id, self.paper_id)
        self.operation = operation
        if document_id is not None:
            self.document_id = document_id
        if paper_id is not None:
            self.paper_id = paper_id
        try:
            yield self
        finally:
            self.operation, self.document_id, self.paper_id = previous

    def __getattr__(self, name: str):
        return getattr(self.provider, name)

    def _gemini(self, provider: GeminiProvider, system: str, user: str) -> tuple[str, dict[str, Any], str]:
        model = provider.model.removeprefix("models/")
        response = httpx.post(
            f"{provider.base_url.rstrip('/')}/models/{model}:generateContent",
            params={"key": provider.api_key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": provider.temperature},
            },
            timeout=provider.timeout,
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
        raw = payload.get("usageMetadata") or {}
        usage = {
            "input_tokens": raw.get("promptTokenCount"),
            "output_tokens": raw.get("candidatesTokenCount"),
            "total_tokens": raw.get("totalTokenCount"),
            "cached_input_tokens": raw.get("cachedContentTokenCount"),
            "reasoning_tokens": raw.get("thoughtsTokenCount"),
        }
        return text, usage, str(payload.get("modelVersion") or model)

    def _openai(self, provider: OpenAICompatibleProvider, system: str, user: str) -> tuple[str, dict[str, Any], str]:
        headers = {"Content-Type": "application/json", **provider.extra_headers}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        body: dict[str, Any] = {
            "model": provider.model,
            "temperature": provider.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        body.update(provider.extra_body)
        response = httpx.post(
            provider.base_url.rstrip("/") + "/chat/completions",
            headers=headers,
            json=body,
            timeout=provider.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(f"{provider.provider_name} returned no choices")
        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise RuntimeError(f"{provider.provider_name} returned an empty response")
        if isinstance(content, list):
            text = "\n".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("text"))
        else:
            text = str(content)
        raw = payload.get("usage") or {}
        details = raw.get("completion_tokens_details") or {}
        usage = {
            "input_tokens": raw.get("prompt_tokens") or raw.get("input_tokens"),
            "output_tokens": raw.get("completion_tokens") or raw.get("output_tokens"),
            "total_tokens": raw.get("total_tokens"),
            "cached_input_tokens": (raw.get("prompt_tokens_details") or {}).get("cached_tokens"),
            "reasoning_tokens": details.get("reasoning_tokens"),
            "reported_cost_usd": raw.get("cost") or payload.get("cost"),
        }
        return text, usage, str(payload.get("model") or provider.model)

    def _ollama(self, provider: OllamaProvider, system: str, user: str) -> tuple[str, dict[str, Any], str]:
        response = httpx.post(
            provider.base_url.rstrip("/") + "/api/chat",
            json={
                "model": provider.model,
                "stream": False,
                "options": {"temperature": provider.temperature},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=provider.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        text = str((payload.get("message") or {}).get("content") or "")
        if not text.strip():
            raise RuntimeError("Ollama returned an empty response")
        usage = {
            "input_tokens": payload.get("prompt_eval_count"),
            "output_tokens": payload.get("eval_count"),
            "total_tokens": _integer(payload.get("prompt_eval_count")) + _integer(payload.get("eval_count")),
        }
        return text, usage, provider.model

    def _one(self, provider: object, system: str, user: str) -> tuple[str, dict[str, Any], str, str, bool]:
        name = str(getattr(provider, "provider_name", type(provider).__name__))
        if isinstance(provider, GeminiProvider):
            text, usage, model = self._gemini(provider, system, user)
            return text, usage, name, model, True
        if isinstance(provider, OpenAICompatibleProvider):
            text, usage, model = self._openai(provider, system, user)
            return text, usage, name, model, True
        if isinstance(provider, OllamaProvider):
            text, usage, model = self._ollama(provider, system, user)
            return text, usage, name, model, True
        text = provider.complete(system, user)  # type: ignore[attr-defined]
        return str(text), {}, name, str(getattr(provider, "model", "unknown")), False

    def complete(self, system: str, user: str) -> str:
        started = time.perf_counter()
        providers = self.provider.providers if isinstance(self.provider, RoutedProvider) else [self.provider]
        if not providers:
            return self.provider.complete(system, user)  # type: ignore[atr-defined]
        errors: list[str] = []
        for attempt, provider in enumerate(providers, start=1):
            name = str(getattr(provider, "provider_name", type(provider).__name__))
            try:
                text, usage, provider_name, model, exact = self._one(provider, system, user)
                metadata = _usage_metadata(
                    provider_name,
                    model,
                    usage,
                    exact=exact,
                    task=self.task,
                    operation=self.operation,
                    attempts=attempt,
                )
                self.last_usage = metadata
                self.recorder.record(
                    "ai_completion",
                    paper_id=self.paper_id,
                    document_id=self.document_id,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    metadata=metadata,
                )
                return text
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}")
        self.recorder.record(
            "ai_completion_error",
            paper_id=self.paper_id,
            document_id=self.document_id,
            duration_ms=int((ntime.perf_counter() - started) * 1000),
            metadata={"task": self.task, "operation": self.operation, "attempts": len(providers), "errors": errors[:8]},
        )
        raise RuntimeError("All configured inference providers failed: " + " | ".join(errors))
