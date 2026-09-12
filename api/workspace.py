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

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        op = self._op()
        q = self._query()
        try:
            if op == "folders":
                self._write(200, {"folders": UserWorkspaceStore(user).list_folders()})
                return
            if op == "library":
                folder_id = (q.get("folder_id") or [""])[0]
                if not folder_id:
                    raise ValueError("folder_id is required")
                store = UserWorkspaceStore(user)
                folder = store.get_folder(folder_id)
                if not folder:
                    self._write(404, {"error": "folder_not_found"})
                    return
                papers = store.list_papers(folder_id)
                self._write(200, {"folder": folder, "papers": papers, "count": len(papers), "target": folder.get("paper_target", 100)})
                return
            if op == "projects":
                limit = int((q.get("limit") or ["50"])[0])
                folder_id = (q.get("folder_id") or [None])[0]
                store = UserSnapshotStore(user, folder_id=folder_id)
                self._write(200, {"projects": store.list_projects(limit=limit)})
                return
            if op == "session":
                session_id = (q.get("session_id") or [None])[0]
                if not session_id:
                    raise ValueError("session_id is required")
                store = UserSnapshotStore(user)
                state = store.load_state(session_id)
                if state is None:
                    self._write(404, {"error": "session_not_found"})
                    return
                artifacts = [a.model_dump(mode="json") for a in store.list_artifacts(session_id)]
                self._write(200, {"state": state.model_dump(mode="json"), "artifacts": artifacts})
                return
            self._write(404, {"error": "unknown_workspace_operation", "op": op})
        except ValueError as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        op = self._op()
        try:
            body = self._body()
            if op == "folders":
                row = UserWorkspaceStore(user).create_folder(body)
                self._write(201, {"folder": row})
                return
            if op == "library":
                folder_id = str(body.pop("folder_id", "")).strip()
                if not folder_id:
                    raise ValueError("folder_id is required")
                store = UserWorkspaceStore(user)
                if not store.get_folder(folder_id):
                    self._write(404, {"error": "folder_not_found"})
                    return
                self._write(201, {"paper": store.add_paper(folder_id, body)})
                return
            if op == "projects":
                project_payload = body.get("project", body)
                folder_id = str(body.get("folder_id") or "").strip()
                if not folder_id:
                    raise ValueError("folder_id is required; every project must be attached to a research folder")
                workspace = UserWorkspaceStore(user)
                folder = workspace.get_folder(folder_id)
                if not folder:
                    self._write(404, {"error": "folder_not_found"})
                    return
                requested = body.get("paper_ids") or []
                if requested:
                    paper_ids = list(dict.fromkeys(str(x) for x in requested if x))
                else:
                    paper_ids = [row["canonical_id"] for row in workspace.list_papers(folder_id) if row.get("canonical_id")]
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
                return
            self._write(404, {"error": "unknown_workspace_operation", "op": op})
        except ValidationError as exc:
            self._write(422, {"error": "validation_error", "details": exc.errors()})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_PATCH(self):
        user = require_user(self)
        if not user:
            return
        op = self._op()
        q = self._query()
        try:
            body = self._body()
            if op == "folders":
                folder_id = (q.get("folder_id") or [""])[0]
                if not folder_id:
                    raise ValueError("folder_id is required")
                self._write(200, {"folder": UserWorkspaceStore(user).update_folder(folder_id, body)})
                return
            if op == "library":
                item_id = (q.get("item_id") or [""])[0]
                if not item_id:
                    raise ValueError("item_id is required")
                self._write(200, {"paper": UserWorkspaceStore(user).update_paper(item_id, body)})
                return
            self._write(404, {"error": "unknown_workspace_operation", "op": op})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_DELETE(self):
        user = require_user(self)
        if not user:
            return
        op = self._op()
        q = self._query()
        try:
            if op == "folders":
                folder_id = (q.get("folder_id") or [""])[0]
                if not folder_id:
                    raise ValueError("folder_id is required")
                UserWorkspaceStore(user).delete_folder(folder_id)
                self._write(200, {"deleted": True, "folder_id": folder_id})
                return
            if op == "library":
                item_id = (q.get("item_id") or [""])[0]
                if not item_id:
                    raise ValueError("item_id is required")
                UserWorkspaceStore(user).delete_paper(item_id)
                self._write(200, {"deleted": True, "item_id": item_id})
                return
            self._write(404, {"error": "unknown_workspace_operation", "op": op})
        except ValueError as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
