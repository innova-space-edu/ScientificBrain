from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from scientific_brain.auth import require_user
from scientific_brain.project_service import DefinedProjectService
from scientific_brain.research_contracts import ResearchProjectDefinition
from scientific_brain.user_snapshot import UserSnapshotStore
from scientific_brain.web_runtime import temporary_memory
from scientific_brain.workspaces import UserWorkspaceStore


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
        user = require_user(self)
        if not user:
            return
        try:
            query = parse_qs(urlparse(self.path).query)
            limit = int((query.get("limit") or ["50"])[0])
            folder_id = (query.get("folder_id") or [None])[0]
            store = UserSnapshotStore(user, folder_id=folder_id)
            self._write(200, {"projects": store.list_projects(limit=limit)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            project_payload = body.get("project", body)
            folder_id = str(body.get("folder_id") or "").strip()
            if not folder_id:
                self._write(400, {"error": "folder_id is required; every project must be attached to a research folder"})
                return

            workspace = UserWorkspaceStore(user)
            folder = workspace.get_folder(folder_id)
            if not folder:
                self._write(404, {"error": "folder_not_found"})
                return

            requested = body.get("paper_ids") or []
            if requested:
                paper_ids = list(dict.fromkeys(str(x) for x in requested if x))
            else:
                paper_ids = [
                    row["canonical_id"]
                    for row in workspace.list_papers(folder_id)
                    if row.get("canonical_id")
                ]

            project = ResearchProjectDefinition.model_validate(project_payload)
            store = UserSnapshotStore(user, folder_id=folder_id)
            with temporary_memory() as memory:
                state = DefinedProjectService(memory, object(), store).create_session(
                    project,
                    paper_ids=paper_ids,
                    owner_id=user.user_id,
                    folder_id=folder_id,
                )
            self._write(201, {
                "project_id": project.project_id,
                "folder_id": folder_id,
                "folder_name": folder.get("name"),
                "session_id": state.session_id,
                "state": state.model_dump(mode="json"),
            })
        except ValidationError as exc:
            self._write(422, {"error": "validation_error", "details": exc.errors()})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
