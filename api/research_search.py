from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from scientific_brain.auth import require_user
from scientific_brain.research_search import ResearchSearchService
from scientific_brain.workspaces import UserWorkspaceStore


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
            body = json.loads(self.rfile.read(length) or b"{}")
            query = str(body.get("query") or "").strip()
            folder_id = str(body.get("folder_id") or "").strip()
            project_id = body.get("project_id")
            if not query:
                raise ValueError("query is required")
            if not folder_id:
                raise ValueError("folder_id is required; research is always scoped to a selected folder")

            store = UserWorkspaceStore(user)
            folder = store.get_folder(folder_id)
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
            store.save_search(
                folder_id,
                query,
                result.get("sources") or [],
                result.get("results") or [],
                project_id=project_id,
            )
            result["folder_id"] = folder_id
            result["folder_name"] = folder.get("name")
            self._write(200, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
