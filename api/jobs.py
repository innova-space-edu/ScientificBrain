from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
from scientific_brain.jobs import SUPPORTED_JOB_TYPES
from scientific_brain.user_snapshot import UserSnapshotStore


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
            session_id = (query.get("session_id") or [None])[0]
            limit = int((query.get("limit") or ["100"])[0])
            store = UserSnapshotStore(user)
            self._write(200, {"jobs": store.list_jobs(session_id=session_id, limit=limit)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            session_id = payload.get("session_id")
            job_type = payload.get("job_type")
            if not session_id or not job_type:
                self._write(400, {"error": "session_id and job_type are required"})
                return
            if job_type not in SUPPORTED_JOB_TYPES:
                self._write(400, {"error": "unsupported_job_type", "supported": sorted(SUPPORTED_JOB_TYPES)})
                return
            base_store = UserSnapshotStore(user)
            state = base_store.load_state(session_id)
            if state is None:
                self._write(404, {"error": "session_not_found"})
                return
            store = UserSnapshotStore(user, folder_id=state.folder_id)
            job = store.create_job(session_id, job_type, payload.get("payload") or {})
            self._write(201, job)
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
