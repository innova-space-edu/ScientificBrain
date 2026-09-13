from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler

from scientific_brain.literature_watch import LiteratureWatchCronRunner


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
        expected = os.getenv("CRON_SECRET", "").strip()
        supplied = self.headers.get("Authorization", "")
        if not expected:
            self._write(503, {"error": "cron_not_configured"})
            return
        if supplied != f"Bearer {expected}":
            self._write(401, {"error": "unauthorized"})
            return
        try:
            limit = max(1, min(int(os.getenv("SCIBRAIN_WATCH_CRON_BATCH", "2")), 3))
            self._write(200, LiteratureWatchCronRunner().run_due(limit=limit))
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
