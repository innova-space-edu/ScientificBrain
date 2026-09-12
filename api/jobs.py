from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.jobs import SUPPORTED_JOB_TYPES
from scientific_brain.security import require_authorized
from scientific_brain.web_runtime import require_cloud_store


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
            query = parse_qs(urlparse(self.path).query)
            session_id = (query.get("session_id") or [None])[0]
            limit = int((query.get("limit") or ["100"])[0])
            store = require_cloud_store()
            self._write(200, {"jobs": store.list_jobs(session_id=session_id, limit=limit)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        if not require_authorized(self):
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
            store = require_cloud_store()
            job = store.create_job(session_id, job_type, payload.get("payload") or {})
            self._write(201, job)
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
