from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
from scientific_brain.user_snapshot import UserSnapshotStore
from scientific_brain.workspaces import UserWorkspaceStore


SUPPORTED_JOB_TYPES = {
    "discover_literature",
    "build_scientific_graph",
    "detect_contradictions",
    "enqueue_selected_reviews",
    "generate_competing_hypotheses",
    "review_paper",
}


class handler(BaseHTTPRequestHandler):
    def _query(self):
        return parse_qs(urlparse(self.path).query)

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
        try:
            query = self._query()
            session_id = (query.get("session_id") or [None])[0]
            folder_id = (query.get("folder_id") or [None])[0]
            limit = max(1, min(int((query.get("limit") or ["100"])[0]), 500))
            if folder_id and not UserWorkspaceStore(user).get_folder(str(folder_id)):
                self._write(404, {"error": "folder_not_found"})
                return
            store = UserSnapshotStore(user, folder_id=str(folder_id) if folder_id else None)
            self._write(200, {"jobs": store.list_jobs(
                session_id=str(session_id) if session_id else None,
                folder_id=str(folder_id) if folder_id else None,
                limit=limit,
            )})
        except (ValueError, KeyError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            body = self._body()
            session_id = str(body.get("session_id") or "").strip() or None
            folder_id = str(body.get("folder_id") or "").strip() or None
            job_type = str(body.get("job_type") or "").strip()
            if not job_type:
                raise ValueError("job_type is required")
            if job_type not in SUPPORTED_JOB_TYPES:
                self._write(400, {"error": "unsupported_job_type", "supported": sorted(SUPPORTED_JOB_TYPES)})
                return

            effective_folder = folder_id
            if session_id:
                state = UserSnapshotStore(user).load_state(session_id)
                if state is None:
                    self._write(404, {"error": "session_not_found"})
                    return
                if effective_folder and str(state.folder_id or "") != effective_folder:
                    self._write(409, {"error": "folder_context_mismatch", "detail": "The session belongs to another research folder."})
                    return
                effective_folder = effective_folder or str(state.folder_id or "").strip()

            if not effective_folder:
                raise ValueError("folder_id or session_id is required")
            if not UserWorkspaceStore(user).get_folder(effective_folder):
                self._write(404, {"error": "folder_not_found"})
                return
            store = UserSnapshotStore(user, folder_id=effective_folder)
            job = store.create_job(session_id, job_type, body.get("payload") or {}, folder_id=effective_folder)
            self._write(201, job)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
