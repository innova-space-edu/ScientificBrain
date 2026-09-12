from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from scientific_brain.auth import require_user
from scientific_brain.persistence import hydrate_memory_from_snapshot
from scientific_brain.providers import provider_from_env
from scientific_brain.stage_stepper import StageStepper
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
            session_id = payload.get("session_id")
            if not session_id:
                self._write(400, {"error": "session_id is required"})
                return
            base_store = UserSnapshotStore(user)
            state = base_store.load_state(session_id)
            if state is None:
                self._write(404, {"error": "session_not_found"})
                return
            store = UserSnapshotStore(user, folder_id=state.folder_id)
            provider = provider_from_env("cloud", task="research")
            with temporary_memory() as memory:
                hydrate_memory_from_snapshot(memory, store, session_id)
                result = StageStepper(memory, provider, store).validate_stage(session_id)
            self._write(200, {
                "session_id": result.session_id,
                "stage": result.stage,
                "gates": [g.model_dump(mode="json") for g in result.gates],
                "decision": {
                    "passed": result.decision.passed,
                    "missing_artifacts": result.decision.missing_artifacts,
                    "failed_gates": result.decision.failed_gates,
                    "completion_rule": result.decision.completion_rule,
                },
                "next_stage": result.next_stage,
            })
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
