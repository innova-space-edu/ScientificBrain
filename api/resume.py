from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from scientific_brain.auth import require_user
from scientific_brain.project_service import DefinedProjectService
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

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            body = self._body()
            folder_id = str(body.get("folder_id") or "").strip()
            reconstruct = bool(body.get("reconstruct", True))
            if not folder_id:
                raise ValueError("folder_id is required")

            workspace = UserWorkspaceStore(user)
            folder = workspace.get_folder(folder_id)
            if not folder:
                self._write(404, {"error": "folder_not_found"})
                return

            snapshot = UserSnapshotStore(user, folder_id=folder_id)
            state_rows = snapshot._select(
                "scibrain_states",
                {
                    "folder_id": f"eq.{folder_id}",
                    "select": "session_id,project_id,state,updated_at",
                    "order": "updated_at.desc",
                    "limit": "1",
                },
            )
            project_rows = snapshot.list_projects(limit=1)
            document_rows = workspace._select(
                "scibrain_research_documents",
                {
                    "folder_id": f"eq.{folder_id}",
                    "select": "document_id,folder_id,topic,status,revision,updated_at",
                    "order": "updated_at.desc",
                    "limit": "1",
                },
            )

            research_document = document_rows[0] if document_rows else None
            latest_project = project_rows[0] if project_rows else None

            if state_rows:
                row = state_rows[0]
                session_id = str(row.get("session_id") or "")
                artifacts = [
                    artifact.model_dump(mode="json")
                    for artifact in snapshot.list_artifacts(session_id)
                ] if session_id else []
                self._write(
                    200,
                    {
                        "folder_id": folder_id,
                        "folder_name": folder.get("name"),
                        "session": {
                            "session_id": session_id,
                            "state": row.get("state") or {},
                            "artifacts": artifacts,
                            "updated_at": row.get("updated_at"),
                        },
                        "project": latest_project,
                        "research_document": research_document,
                        "reconstructed": False,
                    },
                )
                return

            reconstruction_error = None
            if reconstruct and latest_project:
                project_id = str(latest_project.get("project_id") or "")
                try:
                    project = snapshot.load_project(project_id) if project_id else None
                    if project is not None:
                        paper_ids = [
                            row["canonical_id"]
                            for row in workspace.list_papers(folder_id)
                            if row.get("canonical_id")
                        ]
                        paper_ids = list(dict.fromkeys(paper_ids))
                        with temporary_memory() as memory:
                            state = DefinedProjectService(memory, object(), snapshot).create_session(
                                project,
                                paper_ids=paper_ids,
                                owner_id=user.user_id,
                                folder_id=folder_id,
                            )
                        artifacts = [
                            artifact.model_dump(mode="json")
                            for artifact in snapshot.list_artifacts(state.session_id)
                        ]
                        self._write(
                            200,
                            {
                                "folder_id": folder_id,
                                "folder_name": folder.get("name"),
                                "session": {
                                    "session_id": state.session_id,
                                    "state": state.model_dump(mode="json"),
                                    "artifacts": artifacts,
                                },
                                "project": latest_project,
                                "research_document": research_document,
                                "reconstructed": True,
                            },
                        )
                        return
                except Exception as exc:
                    reconstruction_error = f"{type(exc).__name__}: {exc}"

            self._write(
                200,
                {
                    "folder_id": folder_id,
                    "folder_name": folder.get("name"),
                    "session": None,
                    "project": latest_project,
                    "research_document": research_document,
                    "reconstructed": False,
                    "reconstruction_error": reconstruction_error,
                },
            )
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_GET(self):
        self._write(405, {"error": "method_not_allowed", "detail": "Use POST with folder_id"})
