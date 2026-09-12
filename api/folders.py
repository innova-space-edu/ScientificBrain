from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
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

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        try:
            store = UserWorkspaceStore(user)
            self._write(200, {"folders": store.list_folders()})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            row = UserWorkspaceStore(user).create_folder(payload)
            self._write(201, {"folder": row})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_PATCH(self):
        user = require_user(self)
        if not user:
            return
        try:
            query = parse_qs(urlparse(self.path).query)
            folder_id = (query.get("folder_id") or [""])[0]
            if not folder_id:
                raise ValueError("folder_id is required")
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            row = UserWorkspaceStore(user).update_folder(folder_id, payload)
            self._write(200, {"folder": row})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_DELETE(self):
        user = require_user(self)
        if not user:
            return
        try:
            query = parse_qs(urlparse(self.path).query)
            folder_id = (query.get("folder_id") or [""])[0]
            if not folder_id:
                raise ValueError("folder_id is required")
            UserWorkspaceStore(user).delete_folder(folder_id)
            self._write(200, {"deleted": True, "folder_id": folder_id})
        except ValueError as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
