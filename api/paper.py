from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
from scientific_brain.cloud_papers import CloudPaperService
from scientific_brain.paper_memory import PaperMemoryStore
from scientific_brain.providers import provider_from_env
from scientific_brain.user_snapshot import UserSnapshotStore
from scientific_brain.web_runtime import temporary_memory
from scientific_brain.workspaces import UserWorkspaceStore


os.environ.setdefault(
    "EDUAI_AI_PROVIDER_TIMEOUT_MS",
    os.getenv("SCIBRAIN_RESEARCH_PROVIDER_TIMEOUT_MS", "30000"),
)


class handler(BaseHTTPRequestHandler):
    def _write(self, status: int, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query(self):
        return parse_qs(urlparse(self.path).query)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _ensure_memory(self, user, folder_id: str, paper_id: str, pdf_url: str | None = None):
        memory_store = PaperMemoryStore(user, folder_id)
        if memory_store.get(paper_id):
            return memory_store
        snapshot = UserSnapshotStore(user, folder_id=folder_id)
        with temporary_memory() as memory:
            CloudPaperService(memory, object(), snapshot).load_document(paper_id, pdf_url=pdf_url)
        return memory_store

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        try:
            query = self._query()
            folder_id = str((query.get("folder_id") or [""])[0]).strip()
            paper_id = str((query.get("paper_id") or [""])[0]).strip()
            if not folder_id or not paper_id:
                raise ValueError("folder_id and paper_id are required")
            if not UserWorkspaceStore(user).get_folder(folder_id):
                self._write(404, {"error": "folder_not_found"})
                return
            self._write(200, PaperMemoryStore(user, folder_id).status(paper_id))
        except (ValueError, KeyError) as exc:
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
            paper_id = str(body.get("paper_id") or "").strip()
            question = str(body.get("question") or "").strip()
            if not folder_id or not paper_id or not question:
                raise ValueError("folder_id, paper_id and question are required")
            if not UserWorkspaceStore(user).get_folder(folder_id):
                self._write(404, {"error": "folder_not_found"})
                return

            memory_store = self._ensure_memory(user, folder_id, paper_id, body.get("pdf_url"))
            page_hits = memory_store.search_pages(paper_id, question, max_pages=int(body.get("max_pages") or 8))
            if not page_hits:
                raise ValueError("paper text is not available in persistent memory")

            snapshot = UserSnapshotStore(user, folder_id=folder_id)
            bundles = snapshot.load_paper_bundles([paper_id])
            bundle = bundles[0] if bundles else {}
            analysis = bundle.get("analysis") or {}
            critique = bundle.get("critique") or {}
            reviews = bundle.get("specialist_reviews") or []
            page_context = "\n\n".join(
                f"[[PAGE {item['page']}]]\n{item['text']}" for item in page_hits
            )

            system = """You are ScientificBrain Paper Chat.
Answer the user's question using the persistent extracted paper text and its already-saved scientific analysis.
Do not re-analyze the whole PDF from scratch and do not invent information.
When the answer comes directly from the paper, cite page markers as [p. X].
Separate explicit paper content from your interpretation. If the available pages do not support an answer, say what is missing.
Use the saved claims, evidence, critique and specialist reviews when they materially help."""
            user_prompt = f"""QUESTION:\n{question}\n\nSAVED SCIENTIFIC ANALYSIS:\n{json.dumps(analysis, ensure_ascii=False, default=str)[:30000]}\n\nSAVED CRITIQUE:\n{json.dumps(critique, ensure_ascii=False, default=str)[:12000]}\n\nSPECIALIST REVIEWS:\n{json.dumps(reviews, ensure_ascii=False, default=str)[:16000]}\n\nRELEVANT EXTRACTED PAGES:\n{page_context[:50000]}"""
            answer = provider_from_env("cloud", task="research").complete(system, user_prompt)
            self._write(200, {
                "paper_id": paper_id,
                "question": question,
                "answer": answer,
                "pages_used": [item["page"] for item in page_hits],
                "memory": memory_store.status(paper_id),
            })
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
