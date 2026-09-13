from __future__ import annotations

import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler

from scientific_brain.auth import require_user
from scientific_brain.autonomous_jobs import AutonomousScientificJobProcessor
from scientific_brain.providers import provider_from_env
from scientific_brain.user_snapshot import UserSnapshotStore
from scientific_brain.web_runtime import temporary_memory


os.environ.setdefault(
    "EDUAI_AI_PROVIDER_TIMEOUT_MS",
    os.getenv("SCIBRAIN_RESEARCH_PROVIDER_TIMEOUT_MS", "30000"),
)


class SoftJobTimeout(BaseException):
    pass


def _deadline_seconds() -> int:
    raw = int(os.getenv("SCIBRAIN_JOB_SOFT_DEADLINE_SECONDS", "225"))
    return max(60, min(raw, 240))


def _run_with_soft_timeout(fn, seconds: int):
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "SIGALRM"):
        return fn()

    def handler(_signum, _frame):
        raise SoftJobTimeout(f"soft deadline reached after {seconds}s")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(max(1, seconds))
    try:
        return fn()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


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
        started = time.monotonic()
        user = require_user(self)
        if not user:
            return
        try:
            body = self._body()
            job_id = str(body.get("job_id") or "").strip()
            if not job_id:
                raise ValueError("job_id is required")

            base_store = UserSnapshotStore(user)
            job = base_store.get_job(job_id)
            if job is None:
                self._write(404, {"error": "job_not_found"})
                return

            folder_id = job.get("folder_id")
            if not folder_id and job.get("session_id"):
                state = base_store.load_state(job["session_id"])
                if state is None:
                    self._write(404, {"error": "session_not_found"})
                    return
                folder_id = state.folder_id
            if not folder_id:
                raise ValueError("job is not attached to a folder or session")

            store = UserSnapshotStore(user, folder_id=str(folder_id))
            provider = provider_from_env("cloud", task="research")
            deadline = _deadline_seconds()
            remaining = max(1, deadline - int(time.monotonic() - started))
            try:
                with temporary_memory() as memory:
                    result = _run_with_soft_timeout(
                        lambda: AutonomousScientificJobProcessor(memory, provider, store).run(job_id),
                        remaining,
                    )
            except SoftJobTimeout as exc:
                current = store.get_job(job_id) or job
                progress = dict(current.get("progress") or {})
                history = list(progress.get("error_history") or [])
                history.append({
                    "phase": progress.get("phase") or "unknown",
                    "attempt": "soft_timeout",
                    "error": str(exc),
                })
                progress.update({
                    "retryable": True,
                    "reason": "soft_timeout",
                    "soft_deadline_seconds": deadline,
                    "error_history": history[-12:],
                })
                store.update_job(
                    job_id,
                    status="pending",
                    progress=progress,
                    last_error=f"SoftJobTimeout: {exc}. Checkpoint preserved; automatic resume is allowed.",
                )
                self._write(202, store.get_job(job_id) or current)
                return

            self._write(202 if result.get("status") == "pending" else 200, result)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
