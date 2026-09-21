from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from scientific_brain.auth import require_user
from scientific_brain.collaboration import CollaborativeResearchService
from scientific_brain.graph_service import ScientificGraphService
from scientific_brain.graph_store import ScientificGraphStore
from scientific_brain.google_batch import google_batch_from_env
from scientific_brain.google_setup import google_cloud_setup_plan
from scientific_brain.nvidia_provider import nvidia_provider_from_env, physics_toolkit_manifest
from scientific_brain.persistence import hydrate_memory_from_snapshot
from scientific_brain.physics_jobs import physics_execution_profiles, physics_model_catalog, prepare_physics_job
from scientific_brain.physics_tools import (
    monte_carlo_samples,
    physics_worker_status,
    route_plasma_model,
    submit_physics_job,
)
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

    def _google_batch(self):
        token = str(self.headers.get("x-vercel-oidc-token", "") or "").strip()
        return google_batch_from_env(
            vercel_oidc_token=token or None,
            vercel_oidc_token_source="request_header" if token else None,
        )

    def _graph_service(self, user, folder_id: str, provider=None) -> ScientificGraphService:
        return ScientificGraphService(
            snapshot_store=UserSnapshotStore(user, folder_id=folder_id),
            workspace_store=UserWorkspaceStore(user),
            graph_store=ScientificGraphStore(user, folder_id=folder_id),
            provider=provider or provider_from_env("cloud", task="research"),
        )

    def _collab_service(self, user, folder_id: str, provider=None) -> CollaborativeResearchService:
        return CollaborativeResearchService(
            user=user,
            folder_id=folder_id,
            provider=provider or provider_from_env("cloud", task="research"),
        )

    def do_GET(self):
        user = require_user(self)
        if not user:
            return
        op = self._op()
        query = self._query()
        try:
            if op == "nvidia_status":
                self._write(200, nvidia_provider_from_env().status())
                return
            if op == "physics_toolkit":
                self._write(200, physics_toolkit_manifest())
                return
            if op == "physics_workers":
                self._write(200, physics_worker_status())
                return
            if op == "physics_profiles":
                self._write(200, physics_execution_profiles())
                return
            if op == "physics_model_catalog":
                self._write(200, physics_model_catalog())
                return
            if op == "nvidia_models":
                self._write(200, nvidia_provider_from_env().models_status())
                return
            if op == "gcp_batch_status":
                self._write(200, self._google_batch().status())
                return
            if op == "gcp_auth_probe":
                self._write(200, self._google_batch().auth_probe())
                return
            if op == "gcp_setup_plan":
                self._write(200, google_cloud_setup_plan())
                return
            if op == "gcp_batch_get":
                job_id = str((query.get("job_id") or [""])[0]).strip()
                if not job_id:
                    raise ValueError("job_id is required")
                self._write(200, self._google_batch().get(job_id))
                return
            if op == "gcp_output_list":
                scientific_job_id = str((query.get("scientific_job_id") or [""])[0]).strip()
                if not scientific_job_id:
                    raise ValueError("scientific_job_id is required")
                self._write(200, self._google_batch().list_outputs(scientific_job_id))
                return
            if op == "gcp_output_manifest":
                scientific_job_id = str((query.get("scientific_job_id") or [""])[0]).strip()
                if not scientific_job_id:
                    raise ValueError("scientific_job_id is required")
                self._write(200, self._google_batch().output_manifest(scientific_job_id))
                return
            folder_id = (query.get("folder_id") or [""])[0]
            if not folder_id:
                raise ValueError("folder_id is required")
            if op == "research_workspace":
                self._write(200, self._collab_service(user, folder_id).get_workspace())
                return
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
            if op == "gcp_batch_preview":
                job = payload.get("job") or {}
                if not isinstance(job, dict):
                    raise ValueError("job must be a JSON object")
                self._write(200, self._google_batch().build_job(job))
                return
            if op == "gcp_batch_submit":
                job = payload.get("job") or {}
                if not isinstance(job, dict):
                    raise ValueError("job must be a JSON object")
                self._write(202, self._google_batch().submit(job))
                return
            if op == "gcp_batch_delete":
                job_id = str(payload.get("job_id") or "").strip()
                if not job_id:
                    raise ValueError("job_id is required")
                self._write(202, self._google_batch().delete(job_id))
                return
            if op == "physics_prepare_job":
                self._write(200, prepare_physics_job(payload))
                return
            if op == "physics_route":
                self._write(200, route_plasma_model(payload))
                return
            if op == "physics_monte_carlo":
                self._write(200, monte_carlo_samples(payload))
                return
            if op == "physics_submit_job":
                worker = str(payload.get("worker") or "").strip()
                job = payload.get("job") or {}
                if not worker:
                    raise ValueError("worker is required")
                if not isinstance(job, dict):
                    raise ValueError("job must be a JSON object")
                self._write(202, submit_physics_job(worker, job))
                return
            if op == "nvidia_invoke":
                capability = str(payload.get("capability") or "").strip()
                if not capability:
                    raise ValueError("capability is required")
                tool_input = payload.get("input") or {}
                if not isinstance(tool_input, dict):
                    raise ValueError("input must be a JSON object")
                self._write(200, nvidia_provider_from_env().invoke(capability, tool_input))
                return
            if op in {"generate_draft", "save_section", "save_topic", "discuss", "review_section"}:
                folder_id = str(payload.get("folder_id") or "").strip()
                if not folder_id:
                    raise ValueError("folder_id is required")
                service = self._collab_service(user, folder_id, provider_from_env("cloud", task="research"))
                if op == "generate_draft":
                    self._write(200, service.generate_draft(str(payload.get("topic") or ""), language=str(payload.get("language") or "es")))
                    return
                if op == "save_section":
                    self._write(200, service.save_section(str(payload.get("section_key") or ""), str(payload.get("content") or "")))
                    return
                if op == "save_topic":
                    self._write(200, service.save_topic(str(payload.get("topic") or "")))
                    return
                if op == "discuss":
                    self._write(200, service.discuss(
                        str(payload.get("message") or ""),
                        agent_id=str(payload.get("agent_id") or "critical_reviewer"),
                        section_key=payload.get("section_key"),
                        language=str(payload.get("language") or "es"),
                    ))
                    return
                self._write(200, service.review_section(
                    str(payload.get("section_key") or ""),
                    agent_id=str(payload.get("agent_id") or "critical_reviewer"),
                    language=str(payload.get("language") or "es"),
                ))
                return

            if op in {"build_graph", "detect_contradictions", "generate_hypotheses"}:
                folder_id = str(payload.get("folder_id") or "").strip()
                session_id = payload.get("session_id")
                question = str(payload.get("question") or "").strip()
                if session_id:
                    state = UserSnapshotStore(user).load_state(session_id)
                    if state is None:
                        self._write(404, {"error": "session_not_found"})
                        return
                    folder_id = folder_id or str(state.folder_id or "")
                    question = question or state.question
                if not folder_id:
                    raise ValueError("folder_id or session_id is required")
                service = self._graph_service(user, folder_id, provider_from_env("cloud", task="research"))
                if op == "build_graph":
                    result = service.build(full_text_only=bool(payload.get("full_text_only", True)))
                    self._write(200, {"folder_id": folder_id, "paper_count": result.paper_count, "claim_count": result.claim_count, "evidence_count": result.evidence_count, "nodes": len(result.nodes), "edges": len(result.edges)})
                    return
                if op == "detect_contradictions":
                    rows = service.detect_contradictions(context=str(payload.get("context") or ""))
                    self._write(200, {"folder_id": folder_id, "count": len(rows), "contradictions": [x.model_dump(mode="json") for x in rows]})
                    return
                if not question:
                    raise ValueError("question is required when no research session is supplied")
                self._write(200, service.generate_hypotheses(question).model_dump(mode="json"))
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
                    result = StageStepper(memory, provider, store).run_agent(session_id, role_id, extra_context=payload.get("context"))
                self._write(200, result.model_dump(mode="json"))
                return
            if op == "validate_stage":
                with temporary_memory() as memory:
                    hydrate_memory_from_snapshot(memory, store, session_id)
                    result = StageStepper(memory, provider, store).validate_stage(session_id)
                self._write(200, {
                    "session_id": result.session_id, "stage": result.stage,
                    "gates": [g.model_dump(mode="json") for g in result.gates],
                    "decision": {"passed": result.decision.passed, "missing_artifacts": result.decision.missing_artifacts, "failed_gates": result.decision.failed_gates, "completion_rule": result.decision.completion_rule},
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
                        session_id, artifact_type, payload["payload"], stage=payload.get("stage"),
                        evidence_ids=payload.get("evidence_ids") or [], accepted=bool(payload.get("accepted", True)),
                        producer=payload.get("producer") or "human_or_instrument",
                    )
                self._write(201, artifact.model_dump(mode="json"))
                return
            self._write(404, {"error": "unknown_science_operation", "op": op})
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._write(400, {"error": type(exc).__name__, "detail": str(exc)})
        except Exception as exc:
            self._write(500, {"error": type(exc).__name__, "detail": str(exc)})
