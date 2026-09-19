from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx


NVIDIA_API_BASE = "https://integrate.api.nvidia.com/v1"
PHYSICS_SKILLS_REPO = "https://github.com/innova-space-edu/scientificbrain-physics-skills"


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _json_env(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def _safe_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("NVIDIA capability endpoint must be an absolute http(s) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        if not _truthy("SCIBRAIN_NVIDIA_ALLOW_INSECURE_HTTP", False):
            raise ValueError("Plain HTTP NVIDIA endpoints are allowed only for localhost by default")
    return url.rstrip("/")


def physics_toolkit_manifest() -> dict[str, Any]:
    from .physics_tools import physics_toolkit_manifest as _manifest

    return _manifest()


@dataclass(frozen=True)
class NvidiaCapability:
    name: str
    domain: str
    description: str
    endpoint: str
    method: str = "POST"
    auth: str = "nvidia"
    enabled: bool = True

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "method": self.method,
            "enabled": self.enabled,
        }


@dataclass
class NvidiaProvider:
    api_key: str | None = field(default_factory=lambda: os.getenv("NVIDIA_API_KEY") or None)
    ngc_api_key: str | None = field(default_factory=lambda: os.getenv("NGC_API_KEY") or None)
    api_base: str = field(
        default_factory=lambda: os.getenv("SCIBRAIN_NVIDIA_API_BASE", NVIDIA_API_BASE)
    )
    text_model: str = field(
        default_factory=lambda: os.getenv("SCIBRAIN_NVIDIA_TEXT_MODEL", "openai/gpt-oss-20b")
    )
    nim_base_url: str | None = field(
        default_factory=lambda: os.getenv("SCIBRAIN_NVIDIA_NIM_BASE_URL") or None
    )
    nim_model: str | None = field(
        default_factory=lambda: os.getenv("SCIBRAIN_NVIDIA_NIM_MODEL") or None
    )
    nim_api_key: str | None = field(
        default_factory=lambda: os.getenv("SCIBRAIN_NVIDIA_NIM_API_KEY") or None
    )
    timeout: float = 120.0
    provider_name: str = "nvidia"

    def __post_init__(self) -> None:
        self.api_base = _safe_endpoint(self.api_base)
        if self.nim_base_url:
            self.nim_base_url = _safe_endpoint(self.nim_base_url)

    @classmethod
    def from_env(cls) -> "NvidiaProvider":
        raw = os.getenv("SCIBRAIN_NVIDIA_TIMEOUT_MS", "120000")
        try:
            timeout = max(1.0, float(raw) / 1000.0)
        except ValueError:
            timeout = 120.0
        return cls(timeout=timeout)

    @property
    def hosted_configured(self) -> bool:
        return bool(self.api_key and self.text_model)

    @property
    def local_nim_configured(self) -> bool:
        return bool(self.nim_base_url and self.nim_model)

    def _chat(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        system: str,
        user: str,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = httpx.post(
            base_url.rstrip("/") + "/chat/completions",
            headers=headers,
            json={
                "model": model,
                "temperature": 0.1,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("NVIDIA returned no choices")
        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise RuntimeError("NVIDIA returned an empty response")
        return content if isinstance(content, str) else str(content)

    def complete(self, system: str, user: str) -> str:
        if not self.hosted_configured:
            raise RuntimeError("NVIDIA_API_KEY is not configured")
        return self._chat(
            base_url=self.api_base,
            model=self.text_model,
            api_key=self.api_key,
            system=system,
            user=user,
        )

    def _custom_capabilities(self) -> dict[str, NvidiaCapability]:
        raw = _json_env("SCIBRAIN_NVIDIA_CAPABILITIES_JSON")
        result: dict[str, NvidiaCapability] = {}
        for name, spec in raw.items():
            if not isinstance(spec, dict):
                continue
            endpoint = str(spec.get("endpoint") or "").strip()
            if not endpoint:
                continue
            method = str(spec.get("method") or "POST").upper()
            if method not in {"GET", "POST"}:
                raise ValueError(f"Unsupported method for NVIDIA capability {name}: {method}")
            auth = str(spec.get("auth") or "nvidia").lower()
            if auth not in {"nvidia", "ngc", "nim", "none"}:
                raise ValueError(f"Unsupported auth mode for NVIDIA capability {name}: {auth}")
            result[str(name)] = NvidiaCapability(
                name=str(name),
                domain=str(spec.get("domain") or "scientific"),
                description=str(spec.get("description") or name),
                endpoint=_safe_endpoint(endpoint),
                method=method,
                auth=auth,
                enabled=bool(spec.get("enabled", True)),
            )
        return result

    def capabilities(self) -> list[dict[str, Any]]:
        caps: list[dict[str, Any]] = []
        if self.hosted_configured:
            caps.append({
                "name": "nvidia-chat",
                "domain": "general",
                "description": "NVIDIA hosted OpenAI-compatible chat inference",
                "method": "POST",
                "enabled": True,
            })
        if self.local_nim_configured:
            caps.append({
                "name": "local-nim-chat",
                "domain": "local-nim",
                "description": "Self-hosted NVIDIA NIM OpenAI-compatible chat endpoint",
                "method": "POST",
                "enabled": True,
            })
        caps.extend(cap.public_dict() for cap in self._custom_capabilities().values())
        return caps

    def status(self) -> dict[str, Any]:
        return {
            "provider": "nvidia",
            "tools_enabled": _truthy("SCIBRAIN_NVIDIA_TOOLS_ENABLED", True),
            "hosted_api_configured": self.hosted_configured,
            "ngc_key_configured": bool(self.ngc_api_key),
            "api_base": self.api_base,
            "text_model": self.text_model if self.hosted_configured else None,
            "local_nim_configured": self.local_nim_configured,
            "local_nim_model": self.nim_model if self.local_nim_configured else None,
            "capabilities": self.capabilities(),
            "physics_toolkit": physics_toolkit_manifest(),
        }

    def _auth_header(self, mode: str) -> dict[str, str]:
        if mode == "none":
            return {}
        if mode == "nvidia":
            if not self.api_key:
                raise RuntimeError("NVIDIA_API_KEY is required for this capability")
            return {"Authorization": f"Bearer {self.api_key}"}
        if mode == "ngc":
            if not self.ngc_api_key:
                raise RuntimeError("NGC_API_KEY is required for this capability")
            return {"Authorization": f"Bearer {self.ngc_api_key}"}
        if mode == "nim":
            return {"Authorization": f"Bearer {self.nim_api_key}"} if self.nim_api_key else {}
        raise ValueError(f"Unknown NVIDIA auth mode: {mode}")

    def invoke(self, capability: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not _truthy("SCIBRAIN_NVIDIA_TOOLS_ENABLED", True):
            raise RuntimeError("NVIDIA scientific tools are disabled")
        payload = payload or {}

        if capability == "nvidia-chat":
            prompt = str(payload.get("prompt") or payload.get("user") or "").strip()
            if not prompt:
                raise ValueError("prompt is required")
            text = self.complete(
                str(payload.get("system") or "You are a scientific assistant. Preserve uncertainty and units."),
                prompt,
            )
            return {"capability": capability, "provider": "nvidia", "model": self.text_model, "output": text}

        if capability == "local-nim-chat":
            if not self.local_nim_configured:
                raise RuntimeError("Local NVIDIA NIM is not configured")
            prompt = str(payload.get("prompt") or payload.get("user") or "").strip()
            if not prompt:
                raise ValueError("prompt is required")
            text = self._chat(
                base_url=str(self.nim_base_url),
                model=str(self.nim_model),
                api_key=self.nim_api_key,
                system=str(payload.get("system") or "You are a scientific assistant."),
                user=prompt,
            )
            return {"capability": capability, "provider": "nvidia-local-nim", "model": self.nim_model, "output": text}

        cap = self._custom_capabilities().get(capability)
        if cap is None or not cap.enabled:
            raise ValueError(f"Unknown or disabled NVIDIA capability: {capability}")
        headers = {"Content-Type": "application/json", **self._auth_header(cap.auth)}
        response = httpx.request(
            cap.method,
            cap.endpoint,
            headers=headers,
            json=payload if cap.method == "POST" else None,
            params=payload if cap.method == "GET" else None,
            timeout=self.timeout,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        result: Any = response.json() if "json" in content_type else response.text
        return {
            "capability": capability,
            "provider": "nvidia",
            "domain": cap.domain,
            "result": result,
        }


def nvidia_provider_from_env() -> NvidiaProvider:
    return NvidiaProvider.from_env()


def nvidia_configuration_summary() -> dict[str, Any]:
    try:
        return nvidia_provider_from_env().status()
    except Exception as exc:
        return {
            "provider": "nvidia",
            "configured": False,
            "error": type(exc).__name__,
            "capabilities": [],
            "physics_toolkit": physics_toolkit_manifest(),
        }
