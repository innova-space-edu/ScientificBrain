from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def _timeout() -> float:
    raw = os.getenv("SCIBRAIN_VISION_TIMEOUT_MS") or os.getenv("EDUAI_AI_PROVIDER_TIMEOUT_MS") or "60000"
    try:
        return max(5.0, float(raw) / 1000.0)
    except ValueError:
        return 60.0


@dataclass
class VisionResult:
    text: str
    provider: str
    model: str


class VisionRouter:
    """Multimodal router isolated from the text-provider path.

    Only explicitly configured Gemini/OpenRouter credentials are used. Visual analysis is lazy and
    cached by the caller so the same page/question pair is not repeatedly sent to a model.
    """

    def complete(self, system: str, user: str, image_bytes: bytes, mime_type: str = "image/png") -> VisionResult:
        errors: list[str] = []
        gemini_key = _first_env("GEMINI_API_KEY_TEXT", "GEMINI_API_KEY")
        if gemini_key:
            try:
                return self._gemini(gemini_key, system, user, image_bytes, mime_type)
            except Exception as exc:
                errors.append(f"google:{type(exc).__name__}:{exc}")

        openrouter_key = _first_env("OPENROUTER_API_KEY", "OPENROUTER_API_KEY_1")
        if openrouter_key:
            try:
                return self._openrouter(openrouter_key, system, user, image_bytes, mime_type)
            except Exception as exc:
                errors.append(f"openrouter:{type(exc).__name__}:{exc}")

        if not errors:
            raise RuntimeError("No multimodal provider is configured; add GEMINI_API_KEY or OPENROUTER_API_KEY")
        raise RuntimeError("All multimodal providers failed: " + " | ".join(errors))

    def _gemini(self, key: str, system: str, user: str, image_bytes: bytes, mime_type: str) -> VisionResult:
        model = _first_env("GOOGLE_VISION_MODEL", "GOOGLE_TEXT_MODEL_PRIMARY", "GEMINI_TEXT_MODEL_PRIMARY") or "gemini-3.6-flash"
        model = model.removeprefix("models/")
        base_url = os.getenv(
            "GOOGLE_GENERATIVE_LANGUAGE_BASE",
            "https://generativelanguage.googleapis.com/v1beta",
        ).rstrip("/")
        encoded = base64.b64encode(image_bytes).decode("ascii")
        response = httpx.post(
            f"{base_url}/models/{model}:generateContent",
            params={"key": key},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": user},
                            {"inline_data": {"mime_type": mime_type, "data": encoded}},
                        ],
                    }
                ],
                "generationConfig": {"temperature": 0.05},
            },
            timeout=_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        text = "\n".join(str(p.get("text") or "") for p in parts if p.get("text"))
        if not text.strip():
            raise RuntimeError("Gemini returned an empty multimodal response")
        return VisionResult(text=text, provider="google", model=model)

    def _openrouter(self, key: str, system: str, user: str, image_bytes: bytes, mime_type: str) -> VisionResult:
        model = _first_env("OPENROUTER_VISION_MODEL", "OPENROUTER_TEXT_MODEL") or "openrouter/auto"
        encoded = base64.b64encode(image_bytes).decode("ascii")
        headers: dict[str, str] = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        if referer := _first_env("OPENROUTER_REFERER"):
            headers["HTTP-Referer"] = referer
        if title := _first_env("OPENROUTER_APP_TITLE"):
            headers["X-Title"] = title
        response = httpx.post(
            os.getenv("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1").rstrip("/") + "/chat/completions",
            headers=headers,
            json={
                "model": model,
                "temperature": 0.05,
                "messages": [
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                            },
                        ],
                    },
                ],
            },
            timeout=_timeout(),
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("OpenRouter returned no choices")
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, list):
            content = "\n".join(
                str(x.get("text") or "") for x in content if isinstance(x, dict)
            )
        text = str(content or "").strip()
        if not text:
            raise RuntimeError("OpenRouter returned an empty multimodal response")
        return VisionResult(text=text, provider="openrouter", model=model)
