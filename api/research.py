from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
from scientific_brain.jobs import SUPPORTED_JOB_TYPES, ScientificJobProcessor
from scientific_brain.providers import provider_from_env
from scientific_brain.research_search import ResearchSearchService
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
                provider = provider_from_env("cloud", task="research")
                with temporary_memory() as memory:
                    result = ScientificJobProcessor(memory, provider, store).run(job_id)
                self._write(200, result)
                return

            self._write(404, {"error": "unknown_research_operation", "op": op})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
