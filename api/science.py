from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
from scientific_brain.graph_service import ScientificGraphService
from scientific_brain.graph_store import ScientificGraphStore
from scientific_brain.persistence import hydrate_memory_from_snapshot
from scientific_brain.providers import provider_from_env
from scientific_brain.stage_stepper import StageStepper
from scientific_brain.user_snapshot import UserSnapshotStore
from scientific_brain.web_runtime import temporary_memory
from scientific_brain.workspaces import UserWorkspaceStore


class handler(BaseHTTPRequestHandler):
    def _query(self) -> dict[str, list[str]]:
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

    def _graph_service(self, user, folder_id: str, provider=None) -> ScientificGraphService:
        snapshot = UserSnapshotStore(user, folder_id=folder_id)
        workspace = UserWorkspaceStore(user)
        graph = ScientificGraphStore(user, folder_id=folder_id)
        return ScientificGraphService(
            snapshot_store=snapshot,
            workspace_store=workspace,
            graph_store=graph,
            provider=provider or provider_from_env("cloud", task="research"),
        )

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        op = self._op()
        query = self._query()
        try:
            folder_id = (query.get("folder_id") or [""])[0]
            if not folder_id:
                raise ValueError("folder_id is required")
            graph_store = ScientificGraphStore(user, folder_id=folder_id)

            if op == "graph_summary":
                self._write(200, graph_store.summary())
                return
            if op == "graph_nodes":
                node_type = (query.get("node_type") or [None])[0]
                nodes = graph_store.list_nodes(node_type=node_type, limit=int((query.get("limit") or ["5000"])[0]))
                self._write(200, {"nodes": [n.model_dump(mode="json") for n in nodes]})
                return
            if op == "graph_edges":
                edges = graph_store.list_edges(limit=int((query.get("limit") or ["10000"])[0]))
                self._write(200, {"edges": [e.model_dump(mode="json") for e in edges]})
                return
            if op == "contradictions":
                rows = graph_store.list_contradictions(limit=int((query.get("limit") or ["500"])[0]))
                self._write(200, {"contradictions": [x.model_dump(mode="json") for x in rows]})
                return
            if op == "hypotheses":
                rows = graph_store.list_competitions(limit=int((query.get("limit") or ["20"])[0]))
                self._write(200, {"competitions": [x.model_dump(mode="json") for x in rows]})
                return

            self._write(404, {"error": "unknown_science_operation", "op": op})
        except (ValueError, KeyError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})

    def do_POST(self):
        user = require_user(self)
        if not user:
            return
        op = self._op()
        try:
            payload = self._body()

            if op in {"build_graph", "detect_contradictions", "generate_hypotheses"}:
                folder_id = str(payload.get("folder_id") or "").strip()
                session_id = payload.get("session_id")
                question = str(payload.get("question") or "").strip()
                if session_id:
                    base_store = UserSnapshotStore(user)
                    state = base_store.load_state(session_id)
                    if state is None:
                        self._write(404, {"error": "session_not_found"})
                        return
                    folder_id = folder_id or str(state.folder_id or "")
                    question = question or state.question
                if not folder_id:
                    raise ValueError("folder_id or session_id is required")

                provider = provider_from_env("cloud", task="research")
                service = self._graph_service(user, folder_id, provider)

                if op == "build_graph":
                    result = service.build(full_text_only=bool(payload.get("full_text_only", True)))
                    self._write(200, {
                        "folder_id": folder_id,
                        "paper_count": result.paper_count,
                        "claim_count": result.claim_count,
                        "evidence_count": result.evidence_count,
                        "nodes": len(result.nodes),
                        "edges": len(result.edges),
                    })
                    return

                if op == "detect_contradictions":
                    contradictions = service.detect_contradictions(context=str(payload.get("context") or ""))
                    self._write(200, {
                        "folder_id": folder_id,
                        "count": len(contradictions),
                        "contradictions": [x.model_dump(mode="json") for x in contradictions],
                    })
                    return

                if op == "generate_hypotheses":
                    if not question:
                        raise ValueError("question is required when no research session is supplied")
                    competition = service.generate_hypotheses(question)
                    self._write(200, competition.model_dump(mode="json"))
                    return

            session_id = payload.get("session_id")
            if not session_id:
                raise ValueError("session_id is required")

            base_store = UserSnapshotStore(user)
            state = base_store.load_state(session_id)
            if state is None:
                self._write(404, {"error": "session_not_found"})
                return
            store = UserSnapshotStore(user, folder_id=state.folder_id)
            provider = provider_from_env("cloud", task="research")

            if op == "run_agent":
                role_id = payload.get("role_id")
                if not role_id:
                    raise ValueError("role_id is required")
                with temporary_memory() as memory:
                    hydrate_memory_from_snapshot(memory, store, session_id)
                    result = StageStepper(memory, provider, store).run_agent(
                        session_id,
                        role_id,
                        extra_context=payload.get("context"),
                    )
                self._write(200, result.model_dump(mode="json"))
                return

            if op == "validate_stage":
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
                return

            if op == "artifact":
                artifact_type = payload.get("artifact_type")
                if not artifact_type or "payload" not in payload:
                    raise ValueError("artifact_type and payload are required")
                with temporary_memory() as memory:
                    hydrate_memory_from_snapshot(memory, store, session_id)
                    artifact = StageStepper(memory, provider, store).add_external_artifact(
                        session_id,
                        artifact_type,
                        payload["payload"],
                        stage=payload.get("stage"),
                        evidence_ids=payload.get("evidence_ids") or [],
                        accepted=bool(payload.get("accepted", True)),
                        producer=payload.get("producer") or "human_or_instrument",
                    )
                self._write(201, artifact.model_dump(mode="json"))
                return

            self._write(404, {"error": "unknown_science_operation", "op": op})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
