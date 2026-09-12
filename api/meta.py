from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from scientific_brain import __version__
from scientific_brain.auth import supabase_public_config
from scientific_brain.persistence import persistence_status
from scientific_brain.providers import provider_configuration_summary
from scientific_brain.registry import scientific_manifest
from scientific_brain.research_contracts import ResearchProjectDefinition, definition_gate
from scientific_brain.security import security_status
from scientific_brain.templates import theoretical_project_template


class handler(BaseHTTPRequestHandler):
    def _op(self) -> str:
        return (parse_qs(urlparse(self.path).query).get("op") or [""])[0]

    def _write(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        op = self._op()
        if op == "health":
            manifest = scientific_manifest()
            security = security_status()
            supabase = supabase_public_config()
            self._write(200, {
                "service": "ScientificBrain",
                "version": __version__,
                "status": "ok",
                "scientific_protocol": {
                    "agents": len(manifest["agents"]),
                    "stages": len(manifest["stages"]),
                    "hard_rules": len(manifest["hard_rules"]),
                },
                "persistence": persistence_status(),
                "auth": {
                    "provider": "supabase",
                    "url_configured": bool(supabase.get("url")),
                    "publishable_key_configured": bool(supabase.get("publishable_key")),
                    "row_level_security": True,
                    "workspace_isolation": "owner_id = auth.uid()",
                },
                "security": {
                    "legacy_api_token_required": security.token_required,
                    "legacy_api_token_configured": security.token_configured,
                    "primary_user_security": "Supabase Auth + RLS",
                },
                **provider_configuration_summary("research"),
            })
            return
        if op == "manifest":
            self._write(200, scientific_manifest())
            return
        if op == "client_config":
            self._write(200, supabase_public_config())
            return
        if op == "project_schema":
            self._write(200, ResearchProjectDefinition.model_json_schema())
            return
        if op == "project_template":
            self._write(200, theoretical_project_template())
            return
        self._write(404, {"error": "unknown_meta_operation", "op": op})

    def do_POST(self):
        op = self._op()
        if op != "validate_project":
            self._write(404, {"error": "unknown_meta_operation", "op": op})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            project = ResearchProjectDefinition.model_validate(payload)
            gate = definition_gate(project)
            self._write(200 if gate.passed else 422, {
                "valid": gate.passed,
                "project_id": project.project_id,
                "gate": gate.model_dump(mode="json"),
            })
        except ValidationError as exc:
            self._write(422, {"valid": False, "errors": exc.errors()})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"valid": False, "error": str(exc)})
