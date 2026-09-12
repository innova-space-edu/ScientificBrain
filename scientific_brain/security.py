from __future__ import annotations

import hmac
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityStatus:
    token_required: bool
    token_configured: bool

    @property
    def secure_for_public_mutations(self) -> bool:
        return self.token_required and self.token_configured


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def security_status() -> SecurityStatus:
    required = _truthy(os.getenv("SCIBRAIN_REQUIRE_API_TOKEN"), default=False)
    configured = bool(os.getenv("SCIBRAIN_API_TOKEN", "").strip())
    return SecurityStatus(token_required=required, token_configured=configured)


def authorize_headers(headers) -> tuple[bool, str | None]:
    status = security_status()
    if not status.token_required:
        return True, None
    expected = os.getenv("SCIBRAIN_API_TOKEN", "").strip()
    if not expected:
        return False, "SCIBRAIN_REQUIRE_API_TOKEN=true but SCIBRAIN_API_TOKEN is not configured"
    supplied = headers.get("Authorization", "")
    prefix = "Bearer "
    if not supplied.startswith(prefix):
        return False, "Bearer token required"
    token = supplied[len(prefix):].strip()
    if not hmac.compare_digest(token, expected):
        return False, "Invalid API token"
    return True, None


def require_authorized(handler) -> bool:
    ok, detail = authorize_headers(handler.headers)
    if ok:
        return True
    import json

    body = json.dumps({"error": "unauthorized", "detail": detail}).encode("utf-8")
    handler.send_response(401 if detail != "SCIBRAIN_REQUIRE_API_TOKEN=true but SCIBRAIN_API_TOKEN is not configured" else 503)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return False
