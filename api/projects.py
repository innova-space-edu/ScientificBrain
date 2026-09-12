from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from scientific_brain.project_service import DefinedProjectService
from scientific_brain.research_contracts import ResearchProjectDefinition
from scientific_brain.security import require_authorized
from scientific_brain.web_runtime import require_cloud_store, temporary_memory


class handler(BaseHTTPRequestHandler):
    def _write(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not require_authorized(self):
            return
        try:
            store = require_cloud_store()
            query = parse_qs(urlparse(self.path).query)
            limit = int((query.get("limit") or ["50"])[0])
            self._write(200, {"projects": store.list_projects(limit=limit)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        if not require_authorized(self):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            project_payload = body.get("project", body)
            paper_ids = body.get("paper_ids", []) if isinstance(body, dict) else []
            project = ResearchProjectDefinition.model_validate(project_payload)
            store = require_cloud_store()
            with temporary_memory() as memory:
                state = DefinedProjectService(memory, object(), store).create_session(
                    project,
                    paper_ids=paper_ids,
                )
            self._write(201, {
                "project_id": project.project_id,
                "session_id": state.session_id,
                "state": state.model_dump(mode="json"),
            })
        except ValidationError as exc:
            self._write(422, {"error": "validation_error", "details": exc.errors()})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
