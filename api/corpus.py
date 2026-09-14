from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
from scientific_brain.corpus_intelligence import CorpusIntelligenceService
from scientific_brain.corpus_intelligence_v174 import ResilientTelemetryCorpusIntelligenceService
from scientific_brain.literature_watch import LiteratureWatchService
from scientific_brain.observability import ScientificObservabilityService
from scientific_brain.workspaces import UserWorkspaceStore


class handler(BaseHTTPRequestHandler):
    def _query(self):
        return parse_qs(urlparse(self.path).query)

    def _op(self) -> str:
        return str((self._query().get("op") or ["status"])[0]).strip().lower()

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

    def _folder(self, user, folder_id: str):
        if not folder_id:
            raise ValueError("folder_id is required")
        folder = UserWorkspaceStore(user).get_folder(folder_id)
        if not folder:
            raise KeyError("folder_not_found")
        return folder

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        try:
            query = self._query()
            folder_id = str((query.get("folder_id") or [""])[0]).strip()
            folder = self._folder(user, folder_id)
            op = self._op()
            if op == "status":
                corpus = CorpusIntelligenceService(user, folder_id)
                self._write(200, {
                    "folder_id": folder_id,
                    "folder_name": folder.get("name"),
                    "embedding": corpus.embedding_stats(),
                    "watches": LiteratureWatchService(user, folder_id).list_watches(),
                })
                return
            if op == "history":
                thread_id = str((query.get("thread_id") or [""])[0]).strip() or None
                rows = CorpusIntelligenceService(user, folder_id).history(thread_id=thread_id)
                self._write(200, {"folder_id": folder_id, "thread_id": thread_id, "messages": rows})
                return
            if op == "watches":
                service = LiteratureWatchService(user, folder_id)
                watch_id = str((query.get("watch_id") or [""])[0]).strip() or None
                self._write(200, {
                    "folder_id": folder_id,
                    "watches": service.list_watches(),
                    "runs": service.list_runs(watch_id=watch_id, limit=30),
                })
                return
            if op == "observability":
                days = int((query.get("days") or ["7"])[0])
                result = ScientificObservabilityService(user, folder_id).snapshot(days=days)
                self._write(200, {"folder_id": folder_id, "folder_name": folder.get("name"), **result})
                return
            self._write(404, {"error": "unknown_corpus_operation", "op": op})
        except KeyError as exc:
            self._write(404, {"error": str(exc).strip("'")})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            body = self._body()
            folder_id = str(body.get("folder_id") or "").strip()
            self._folder(user, folder_id)
            op = self._op()
            if op == "search":
                result = CorpusIntelligenceService(user, folder_id).search(
                    str(body.get("query") or ""),
                    limit=int(body.get("limit") or 24),
                    per_paper=int(body.get("per_paper") or 4),
                    lazy_embed=bool(body.get("lazy_embed", True)),
                )
                self._write(200, result)
                return
            if op == "ask":
                result = ResilientTelemetryCorpusIntelligenceService(user, folder_id).ask(
                    str(body.get("question") or ""),
                    thread_id=str(body.get("thread_id") or "").strip() or None,
                    language=str(body.get("language") or "es"),
                    limit=int(body.get("limit") or 24),
                )
                self._write(200, result)
                return
            watches = LiteratureWatchService(user, folder_id)
            if op == "create_watch":
                self._write(201, {"watch": watches.create_watch(body)})
                return
            if op == "update_watch":
                watch_id = str(body.get("watch_id") or "").strip()
                if not watch_id:
                    raise ValueError("watch_id is required")
                self._write(200, {"watch": watches.update_watch(watch_id, body)})
                return
            if op == "run_watch":
                watch_id = str(body.get("watch_id") or "").strip()
                if not watch_id:
                    raise ValueError("watch_id is required")
                self._write(200, watches.run_watch(watch_id))
                return
            self._write(404, {"error": "unknown_corpus_operation", "op": op})
        except KeyError as exc:
            self._write(404, {"error": str(exc).strip("'")})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
