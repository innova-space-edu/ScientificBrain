from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from scientific_brain.auth import require_user
from scientific_brain.jobs import ScientificJobProcessor
from scientific_brain.providers import provider_from_env
from scientific_brain.user_snapshot import UserSnapshotStore
from scientific_brain.web_runtime import temporary_memory


class handler(BaseHTTPRequestHandler):
    def _write(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            job_id = payload.get("job_id")
            if not job_id:
                self._write(400, {"error": "job_id is required"})
                return
            base_store = UserSnapshotStore(user)
            job = base_store.get_job(job_id)
            if job is None:
                self._write(404, {"error": "job_not_found"})
                return
            state = base_store.load_state(job["session_id"])
            if state is None:
                self._write(404, {"error": "session_not_found"})
                return
            store = UserSnapshotStore(user, folder_id=state.folder_id)
            provider = provider_from_env("cloud", task="research")
            with temporary_memory() as memory:
                result = ScientificJobProcessor(memory, provider, store).run(job_id)
            self._write(200, result)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
