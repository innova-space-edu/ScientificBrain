from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.advanced_roles import register_advanced_roles
from scientific_brain.auth import require_user
from scientific_brain.collaboration import AGENT_ROLES
from scientific_brain.providers import provider_from_env
from scientific_brain.quality_control import ScientificQualityControlService
from scientific_brain.research_versions import ResearchVersionStore


register_advanced_roles(AGENT_ROLES)

os.environ.setdefault(
    "EDUAI_AI_PROVIDER_TIMEOUT_MS",
    os.getenv("SCIBRAIN_RESEARCH_PROVIDER_TIMEOUT_MS", "30000"),
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

    def _service(self, user, folder_id: str):
        if not folder_id:
            raise ValueError("folder_id is required")
        return ScientificQualityControlService(
            user=user,
            folder_id=folder_id,
            provider=provider_from_env("cloud", task="research"),
        )

    @staticmethod
    def _snapshot_result(store: ResearchVersionStore, result, reason: str):
        if isinstance(result, dict):
            document = result.get("document")
            if isinstance(document, dict):
                store.snapshot(document, reason=reason)
        return result

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        try:
            query = self._query()
            folder_id = (query.get("folder_id") or [""])[0]
            op = self._op()
            if op == "research_workspace":
                self._write(200, self._service(user, folder_id).get_workspace())
                return
            if op == "versions":
                store = ResearchVersionStore(user, folder_id)
                self._write(200, {"versions": store.list_versions(), "document": store.document()})
                return
            if op == "export":
                fmt = (query.get("format") or ["markdown"])[0]
                self._write(200, ResearchVersionStore(user, folder_id).export(fmt))
                return
            self._write(404, {"error": "unknown_collaboration_operation", "op": op})
        except KeyError as exc:
            self._write(404, {"error": type(exc).__name__, "detail": str(exc)})
        except ValueError as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        try:
            payload = self._body()
            folder_id = str(payload.get("folder_id") or "").strip()
            service = self._service(user, folder_id)
            versions = ResearchVersionStore(user, folder_id)
            op = self._op()

            mutation_ops = {
                "generate_draft", "save_brief", "assess_brief", "save_section", "save_topic",
                "rewrite_section", "verify_document", "benchmark_document", "repair_failed_sections",
            }
            if op in mutation_ops:
                versions.snapshot(versions.document(), reason=f"before_{op}")

            if op == "generate_draft":
                result = service.generate_draft(
                    str(payload.get("topic") or ""),
                    language=str(payload.get("language") or "es"),
                    preserve_user_edits=bool(payload.get("preserve_user_edits", True)),
                )
                if isinstance(result, dict) and isinstance(result.get("document"), dict):
                    fresh = versions.mark_fresh(result["document"])
                    if fresh:
                        result["document"] = fresh
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "save_brief":
                result = service.save_brief(payload.get("brief") or {})
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "assess_brief":
                result = service.assess_brief(language=str(payload.get("language") or "es"))
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "save_section":
                result = service.save_section(
                    str(payload.get("section_key") or ""),
                    str(payload.get("content") or ""),
                )
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "save_topic":
                result = service.save_topic(str(payload.get("topic") or ""))
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "discuss":
                self._write(200, service.discuss(
                    str(payload.get("message") or ""),
                    agent_id=str(payload.get("agent_id") or "critical_reviewer"),
                    section_key=payload.get("section_key"),
                    language=str(payload.get("language") or "es"),
                ))
                return
            if op == "review_section":
                self._write(200, service.review_section(
                    str(payload.get("section_key") or ""),
                    agent_id=str(payload.get("agent_id") or "critical_reviewer"),
                    language=str(payload.get("language") or "es"),
                ))
                return
            if op == "rewrite_section":
                result = service.rewrite_section(
                    str(payload.get("section_key") or ""),
                    language=str(payload.get("language") or "es"),
                )
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "verify_document":
                result = service.verify_document(
                    language=str(payload.get("language") or "es"),
                    use_model=bool(payload.get("use_model", True)),
                )
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "benchmark_document":
                result = service.benchmark_document(
                    language=str(payload.get("language") or "es"),
                    use_model=bool(payload.get("use_model", True)),
                    persist=True,
                )
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "repair_failed_sections":
                result = service.repair_failed_sections(
                    language=str(payload.get("language") or "es"),
                    max_sections=int(payload.get("max_sections") or 4),
                )
                self._write(200, self._snapshot_result(versions, result, op))
                return
            if op == "restore_version":
                current = versions.document()
                versions.snapshot(current, reason="before_restore")
                document = versions.restore(str(payload.get("version_id") or ""))
                self._write(200, {"document": document})
                return
            self._write(404, {"error": "unknown_collaboration_operation", "op": op})
        except KeyError as exc:
            self._write(404, {"error": type(exc).__name__, "detail": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
