from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from pydantic import ValidationError

from scientific_brain.research_contracts import ResearchProjectDefinition, definition_gate


class handler(BaseHTTPRequestHandler):
    def _write(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
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
