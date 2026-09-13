from __future__ import annotations

import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
from scientific_brain.jobs import SUPPORTED_JOB_TYPES, ScientificJobProcessor
from scientific_brain.providers import provider_from_env
from scientific_brain.research_search import ResearchSearchService
from scientific_brain.user_snapshot import UserSnapshotStore
from scientific_brain.web_runtime import temporary_memory
from scientific_brain.workspaces import UserWorkspaceStore


class SoftJobTimeout(BaseException):
    """Control-flow sentinel raised before the hosting platform hard timeout.

    It intentionally derives from BaseException so broad provider/application
    ``except Exception`` failover handlers cannot swallow the deadline signal.
    """


def _run_with_soft_timeout(callback, seconds: int):
    can_alarm = (
        seconds > 0
        and hasattr(signal, "SIGALRM")
        and hasattr(signal, "setitimer")
        and threading.current_thread() is threading.main_thread()
    )
    if not can_alarm:
        return callback()

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum, _frame):
        raise SoftJobTimeout(f"Research job exceeded the {seconds}s remaining execution budget")

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return callback()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _job_deadline_seconds() -> int:
    try:
        requested = int(os.getenv("SCIBRAIN_JOB_SOFT_DEADLINE_SECONDS", "225"))
    except ValueError:
        requested = 225
    # Reserve at least ~60 s of a 300 s function for status recovery and response I/O.
    return max(60, min(requested, 240))


def _configure_research_provider_timeout() -> None:
    if "EDUAI_AI_PROVIDER_TIMEOUT_MS" not in os.environ:
        os.environ["EDUAI_AI_PROVIDER_TIMEOUT_MS"] = os.getenv(
            "SCIBRAIN_RESEARCH_PROVIDER_TIMEOUT_MS",
            "30000",
        )


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
        if op != "jobs":
            self._write(404, {"error": "unknown_research_operation", "op": op})
            return
        try:
            query = self._query()
            session_id = (query.get("session_id") or [None])[0]
            folder_id = (query.get("folder_id") or [None])[0]
            limit = int((query.get("limit") or ["100"])[0])
            store = UserSnapshotStore(user, folder_id=folder_id)
            self._write(200, {
                "jobs": store.list_jobs(session_id=session_id, folder_id=folder_id, limit=limit)
            })
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        invocation_started = time.monotonic()
        user = require_user(self)
        if not user:
            return
        op = self._op()
        try:
            body = self._body()
            if op == "research_search":
                query = str(body.get("query") or "").strip()
                folder_id = str(body.get("folder_id") or "").strip()
                project_id = body.get("project_id")
                if not query:
                    raise ValueError("query is required")
                if not folder_id:
                    raise ValueError("folder_id is required; research is always scoped to a selected folder")
                workspace = UserWorkspaceStore(user)
                folder = workspace.get_folder(folder_id)
                if not folder:
                    self._write(404, {"error": "folder_not_found"})
                    return
                result = ResearchSearchService().search(
                    query,
                    from_year=int(body.get("from_year") or 1900),
                    max_results=max(1, min(int(body.get("max_results") or 50), 100)),
                    include_web=bool(body.get("include_web", True)),
                    resolve_open_access=bool(body.get("resolve_open_access", True)),
                )
                workspace.save_search(
                    folder_id,
                    query,
                    result.get("sources") or [],
                    result.get("results") or [],
                    project_id=project_id,
                )
                result["folder_id"] = folder_id
                result["folder_name"] = folder.get("name")
                self._write(200, result)
                return

            if op == "jobs":
                session_id = body.get("session_id")
                folder_id = str(body.get("folder_id") or "").strip() or None
                job_type = body.get("job_type")
                if not job_type:
                    raise ValueError("job_type is required")
                if job_type not in SUPPORTED_JOB_TYPES:
                    self._write(400, {"error": "unsupported_job_type", "supported": sorted(SUPPORTED_JOB_TYPES)})
                    return

                effective_folder = folder_id
                if session_id:
                    base_store = UserSnapshotStore(user)
                    state = base_store.load_state(session_id)
                    if state is None:
                        self._write(404, {"error": "session_not_found"})
                        return
                    effective_folder = effective_folder or state.folder_id
                if not effective_folder:
                    raise ValueError("folder_id or session_id is required")

                workspace = UserWorkspaceStore(user)
                if not workspace.get_folder(str(effective_folder)):
                    self._write(404, {"error": "folder_not_found"})
                    return
                store = UserSnapshotStore(user, folder_id=str(effective_folder))
                job = store.create_job(
                    session_id,
                    job_type,
                    body.get("payload") or {},
                    folder_id=str(effective_folder),
                )
                self._write(201, job)
                return

            if op == "run_job":
                job_id = body.get("job_id")
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
                _configure_research_provider_timeout()
                provider = provider_from_env("cloud", task="research")
                deadline = _job_deadline_seconds()
                elapsed = int(time.monotonic() - invocation_started)
                remaining = max(1, deadline - elapsed)
                try:
                    with temporary_memory() as memory:
                        result = _run_with_soft_timeout(
                            lambda: ScientificJobProcessor(memory, provider, store).run(job_id),
                            remaining,
                        )
                except SoftJobTimeout as exc:
                    current = store.get_job(job_id) or job
                    progress = dict(current.get("progress") or {})
                    progress.update({
                        "retryable": True,
                        "reason": "soft_timeout",
                        "soft_deadline_seconds": deadline,
                    })
                    store.update_job(
                        job_id,
                        status="pending",
                        progress=progress,
                        last_error=(
                            f"SoftJobTimeout: {exc}. Progress was preserved and the job can resume "
                            "from its last checkpoint."
                        ),
                    )
                    recovered = store.get_job(job_id) or current
                    self._write(202, recovered)
                    return
                self._write(200, result)
                return

            self._write(404, {"error": "unknown_research_operation", "op": op})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
