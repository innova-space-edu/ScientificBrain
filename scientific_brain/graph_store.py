from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .auth import AuthenticatedUser, supabase_public_config
from .graph_models import (
    ContradictionRecord,
    EvidenceLineage,
    GraphBuildResult,
    HypothesisCompetition,
    ScientificGraphEdge,
    ScientificGraphNode,
)


@dataclass
class ScientificGraphStore:
    user: AuthenticatedUser
    folder_id: str
    timeout: float = 30.0

    def __post_init__(self) -> None:
        config = supabase_public_config()
        self.url = config["url"].rstrip("/")
        self.key = config["publishable_key"]
        if not self.url or not self.key:
            raise RuntimeError("Supabase public configuration is incomplete")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.user.access_token}",
            "Content-Type": "application/json",
        }

    def _endpoint(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def _delete_folder_rows(self, table: str) -> None:
        response = httpx.delete(
            self._endpoint(table),
            headers=self.headers,
            params={"folder_id": f"eq.{self.folder_id}"},
            timeout=self.timeout,
        )
        response.raise_for_status()

    def _bulk_insert(self, table: str, rows: list[dict[str, Any]], conflict: str) -> None:
        if not rows:
            return
        # Keep request bodies comfortably below serverless/provider limits.
        for start in range(0, len(rows), 250):
            batch = rows[start:start + 250]
            response = httpx.post(
                self._endpoint(table),
                headers={
                    **self.headers,
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                params={"on_conflict": conflict},
                json=batch,
                timeout=max(self.timeout, 60.0),
            )
            response.raise_for_status()

    def replace_graph(self, result: GraphBuildResult) -> None:
        self._delete_folder_rows("scibrain_graph_edges")
        self._delete_folder_rows("scibrain_graph_nodes")
        node_rows = [
            {
                "owner_id": self.user.user_id,
                "folder_id": self.folder_id,
                "node_id": node.node_id,
                "node_type": node.node_type.value,
                "label": node.label,
                "paper_id": node.paper_id,
                "claim_id": node.claim_id,
                "evidence_id": node.evidence_id,
                "epistemic_state": node.epistemic_state.value,
                "properties": node.properties,
            }
            for node in result.nodes
        ]
        edge_rows = [
            {
                "owner_id": self.user.user_id,
                "folder_id": self.folder_id,
                "edge_id": edge.edge_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "relation": edge.relation.value,
                "confidence": edge.confidence,
                "rationale": edge.rationale,
                "properties": edge.properties,
            }
            for edge in result.edges
        ]
        self._bulk_insert(
            "scibrain_graph_nodes",
            node_rows,
            "owner_id,folder_id,node_id",
        )
        self._bulk_insert(
            "scibrain_graph_edges",
            edge_rows,
            "owner_id,folder_id,edge_id",
        )

    def replace_contradictions(self, contradictions: list[ContradictionRecord]) -> None:
        self._delete_folder_rows("scibrain_contradictions")
        rows = [
            {
                "owner_id": self.user.user_id,
                "folder_id": self.folder_id,
                "contradiction_id": item.contradiction_id,
                "claim_a_id": item.claim_a_id,
                "claim_b_id": item.claim_b_id,
                "contradiction_type": item.contradiction_type,
                "summary": item.summary,
                "regime_difference": item.regime_difference,
                "possible_explanation": item.possible_explanation,
                "discriminating_observables": item.discriminating_observables,
                "required_test": item.required_test,
                "confidence": item.confidence,
                "status": item.status,
            }
            for item in contradictions
        ]
        self._bulk_insert(
            "scibrain_contradictions",
            rows,
            "owner_id,folder_id,contradiction_id",
        )

    def replace_competition(self, competition: HypothesisCompetition) -> None:
        self._delete_folder_rows("scibrain_hypothesis_competitions")
        self._bulk_insert(
            "scibrain_hypothesis_competitions",
            [{
                "owner_id": self.user.user_id,
                "folder_id": self.folder_id,
                "competition_id": competition.competition_id,
                "question": competition.question,
                "contradiction_ids": competition.contradiction_ids,
                "hypotheses": [item.model_dump(mode="json") for item in competition.hypotheses],
                "decision_needed": competition.decision_needed,
            }],
            "owner_id,folder_id,competition_id",
        )

    def replace_lineage(self, lineage: list[EvidenceLineage]) -> None:
        self._delete_folder_rows("scibrain_evidence_lineage")
        rows = [
            {
                "owner_id": self.user.user_id,
                "folder_id": self.folder_id,
                "lineage_id": item.lineage_id,
                "source_evidence_id": item.source_evidence_id,
                "target_evidence_id": item.target_evidence_id,
                "lineage_type": item.lineage_type.value,
                "confidence": item.confidence,
                "rationale": item.rationale,
                "status": item.status,
            }
            for item in lineage
        ]
        self._bulk_insert(
            "scibrain_evidence_lineage",
            rows,
            "owner_id,folder_id,lineage_id",
        )

    def _select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = httpx.get(
            self._endpoint(table),
            headers=self.headers,
            params={"folder_id": f"eq.{self.folder_id}", **params},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def list_nodes(self, node_type: str | None = None, limit: int = 5000) -> list[ScientificGraphNode]:
        params = {
            "select": "node_id,node_type,label,paper_id,claim_id,evidence_id,epistemic_state,properties",
            "limit": str(max(1, min(limit, 10000))),
        }
        if node_type:
            params["node_type"] = f"eq.{node_type}"
        return [ScientificGraphNode.model_validate(row) for row in self._select("scibrain_graph_nodes", params)]

    def list_edges(self, limit: int = 10000) -> list[ScientificGraphEdge]:
        params = {
            "select": "edge_id,source_node_id,target_node_id,relation,confidence,rationale,properties",
            "limit": str(max(1, min(limit, 20000))),
        }
        return [ScientificGraphEdge.model_validate(row) for row in self._select("scibrain_graph_edges", params)]

    def list_contradictions(self, limit: int = 500) -> list[ContradictionRecord]:
        rows = self._select(
            "scibrain_contradictions",
            {
                "select": "contradiction_id,claim_a_id,claim_b_id,contradiction_type,summary,regime_difference,possible_explanation,discriminating_observables,required_test,confidence,status,created_at",
                "order": "confidence.desc",
                "limit": str(max(1, min(limit, 2000))),
            },
        )
        return [ContradictionRecord.model_validate(row) for row in rows]

    def list_competitions(self, limit: int = 20) -> list[HypothesisCompetition]:
        rows = self._select(
            "scibrain_hypothesis_competitions",
            {
                "select": "competition_id,question,contradiction_ids,hypotheses,decision_needed",
                "order": "updated_at.desc",
                "limit": str(max(1, min(limit, 100))),
            },
        )
        return [HypothesisCompetition.model_validate(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        nodes = self.list_nodes(limit=10000)
        edges = self.list_edges(limit=20000)
        contradictions = self.list_contradictions(limit=2000)
        competitions = self.list_competitions(limit=100)
        counts: dict[str, int] = {}
        for node in nodes:
            counts[node.node_type.value] = counts.get(node.node_type.value, 0) + 1
        return {
            "folder_id": self.folder_id,
            "nodes": len(nodes),
            "edges": len(edges),
            "node_types": counts,
            "contradictions": len(contradictions),
            "hypothesis_competitions": len(competitions),
            "candidate_hypotheses": sum(len(item.hypotheses) for item in competitions),
        }
