from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
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
            if not session_id:
                self._write(400, {"error": "session_id is required"})
                return
            store = UserSnapshotStore(user)
            state = store.load_state(session_id)
            if state is None:
                self._write(404, {"error": "session_not_found"})
                return
            artifacts = [a.model_dump(mode="json") for a in store.list_artifacts(session_id)]
            self._write(200, {
                "state": state.model_dump(mode="json"),
                "artifacts": artifacts,
            })
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
