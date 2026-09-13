from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.adaptive_collaboration import AdaptiveCollaborativeResearchService
from scientific_brain.auth import require_user
from scientific_brain.providers import provider_from_env


os.environ.setdefault(
    "EDUAI_AI_PROVIDER_TIMEOUT_MS",
    os.getenv("SCIBRAIN_RESEARCH_PROVIDER_TIMEOUT_MS", "30000"),
)


class handler(BaseHTTPRequestHandler):
    def _query(self):
        return parse_qs(urlparse(self.path).query)

    def _op(self) -> str:
        return (self._query().get("op") or [""])[0]

    def _write(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _service(self, user, folder_id: str):
        if not folder_id:
            raise ValueError("folder_id is required")
        return AdaptiveCollaborativeResearchService(
            user=user,
            folder_id=folder_id,
            provider=provider_from_env("cloud", task="research"),
        )

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        try:
            folder_id = (self._query().get("folder_id") or [""])[0]
            if self._op() == "research_workspace":
                self._write(200, self._service(user, folder_id).get_workspace())
                return
            self._write(404, {"error": "unknown_collaboration_operation", "op": self._op()})
        except (ValueError, KeyError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            payload = self._body()
            service = self._service(user, str(payload.get("folder_id") or "").strip())
            op = self._op()
            if op == "generate_draft":
                self._write(200, service.generate_draft(
                    str(payload.get("topic") or ""),
                    language=str(payload.get("language") or "es"),
                ))
                return
            if op == "save_section":
                self._write(200, service.save_section(
                    str(payload.get("section_key") or ""),
                    str(payload.get("content") or ""),
                ))
                return
            if op == "save_topic":
                self._write(200, service.save_topic(str(payload.get("topic") or "")))
                return
            if op == "discuss":
                self._write(200, service.discuss(
                    str(payload.get("message") or ""),
                    agent_id=str(payload.get("agent_id") or "critical_reviewer"),
                    section_key=payload.get("section_key"),
                    language=str(payload.get("language") or "es"),
                ))
                return
            if op == "review_section":
                self._write(200, service.review_section(
                    str(payload.get("section_key") or ""),
                    agent_id=str(payload.get("agent_id") or "critical_reviewer"),
                    language=str(payload.get("language") or "es"),
                ))
                return
            self._write(404, {"error": "unknown_collaboration_operation", "op": op})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
