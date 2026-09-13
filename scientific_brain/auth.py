from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    email: str | None
    access_token: str
    raw: dict[str, Any]


def supabase_public_config() -> dict[str, str]:
    url = os.getenv("SUPABASE_URL", "https://cwbnvukerekgcedcyydd.supabase.co").strip()
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    return {"url": url, "publishable_key": key}


def bearer_token(headers) -> str | None:
    supplied = headers.get("Authorization", "")
    if not supplied.startswith("Bearer "):
        return None
    token = supplied[len("Bearer "):].strip()
    return token or None


def verify_supabase_access_token(token: str, timeout: float = 15.0) -> AuthenticatedUser:
    config = supabase_public_config()
    if not config["url"] or not config["publishable_key"]:
        raise RuntimeError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be configured")
    response = httpx.get(
        config["url"].rstrip("/") + "/auth/v1/user",
        headers={
            "apikey": config["publishable_key"],
            "Authorization": f"Bearer {token}",
        },
        timeout=timeout,
    )
    if response.status_code in {401, 403}:
        raise PermissionError("Invalid or expired Supabase session")
    response.raise_for_status()
    payload = response.json()
    user_id = payload.get("id")
    if not user_id:
        raise PermissionError("Supabase session did not resolve to a user")
    return AuthenticatedUser(
        user_id=str(user_id),
        email=payload.get("email"),
        access_token=token,
        raw=payload,
    )


def user_from_headers(headers) -> AuthenticatedUser:
    token = bearer_token(headers)
    if not token:
        raise PermissionError("Supabase Bearer access token required")
    return verify_supabase_access_token(token)


def require_user(handler) -> AuthenticatedUser | None:
    try:
        return user_from_headers(handler.headers)
    except PermissionError as exc:
        body = json.dumps({"error": "unauthorized", "detail": str(exc)}).encode("utf-8")
        handler.send_response(401)
    except Exception as exc:
        body = json.dumps({"error": type(exc).__name__, "detail": str(exc)}).encode("utf-8")
        handler.send_response(503)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return None
