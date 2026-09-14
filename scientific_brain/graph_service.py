from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .graph_agents import ContradictionAgent, HypothesisCompetitionAgent
from .graph_builder import ScientificGraphBuilder
from .graph_models import (
    ContradictionRecord,
    GraphBuildResult,
    GraphNodeType,
    GraphRelation,
    HypothesisCompetition,
    ScientificGraphNode,
)
from .graph_store import ScientificGraphStore
from .user_snapshot import UserSnapshotStore
from .workspaces import UserWorkspaceStore


@dataclass
class ScientificGraphService:
    snapshot_store: UserSnapshotStore
    workspace_store: UserWorkspaceStore
    graph_store: ScientificGraphStore
    provider: object

    def _folder_bundles(self, *, full_text_only: bool = True) -> list[dict[str, Any]]:
        papers = self.workspace_store.list_papers(self.graph_store.folder_id)
        if full_text_only:
            papers = [p for p in papers if p.get("review_depth") == "full_text_reviewed"]
        ids = [p.get("canonical_id") for p in papers if p.get("canonical_id")]
        return self.snapshot_store.load_paper_bundles(ids)

    def build(self, *, full_text_only: bool = True) -> GraphBuildResult:
        result = ScientificGraphBuilder().build(self._folder_bundles(full_text_only=full_text_only))
        self.graph_store.replace_graph(result)
        return result

    def _topic_claim_groups(self, claims: list[ScientificGraphNode], papers: list[ScientificGraphNode]) -> list[list[ScientificGraphNode]]:
        topics_by_paper: dict[str, list[str]] = {}
        for paper in papers:
            topics = [str(x).strip().lower() for x in paper.properties.get("topics", []) if str(x).strip()]
            topics_by_paper[paper.paper_id or ""] = topics or ["general"]

        groups: dict[str, dict[str, ScientificGraphNode]] = defaultdict(dict)
        for claim in claims:
            for topic in topics_by_paper.get(claim.paper_id or "", ["general"]):
                groups[topic][claim.node_id] = claim

        # If taxonomy labels are sparse, add a general cross-paper group so genuine
        # contradictions are not hidden only because papers were classified differently.
        if len({c.paper_id for c in claims}) > 1:
            groups["__cross_paper__"] = {c.node_id: c for c in claims}

        batches: list[list[ScientificGraphNode]] = []
        for items in groups.values():
            values = list(items.values())
            if len(values) < 2:
                continue
            if len(values) <= 70:
                batches.append(values)
                continue
            step = 55
            overlap = 15
            start = 0
            while start < len(values):
                chunk = values[start:start + step]
                if len(chunk) >= 2:
                    batches.append(chunk)
                if start + step >= len(values):
                    break
                start += step - overlap
        return batches

    def detect_contradictions(self, *, context: str = "") -> list[ContradictionRecord]:
        nodes = self.graph_store.list_nodes(limit=10000)
        claims = [n for n in nodes if n.node_type == GraphNodeType.CLAIM]
        papers = [n for n in nodes if n.node_type == GraphNodeType.PAPER]
        if len(claims) < 2:
            self.graph_store.replace_contradictions([])
            return []

        agent = ContradictionAgent(self.provider)
        by_pair: dict[tuple[str, str], ContradictionRecord] = {}
        for batch in self._topic_claim_groups(claims, papers):
            for item in agent.detect(batch, context=context):
                pair = tuple(sorted((item.claim_a_id, item.claim_b_id)))
                previous = by_pair.get(pair)
                if previous is None or item.confidence > previous.confidence:
                    by_pair[pair] = item
        results = sorted(by_pair.values(), key=lambda x: x.confidence, reverse=True)
        self.graph_store.replace_contradictions(results)
        return results

    @staticmethod
    def _question_terms(question: str) -> set[str]:
        stop = {
            "what", "which", "when", "where", "how", "does", "with", "from", "that", "this", "into",
            "que", "qué", "cual", "cuál", "como", "cómo", "para", "con", "por", "una", "uno", "las", "los",
            "the", "and", "are", "del", "entre", "sobre", "under", "bajo",
        }
        return {
            word
            for word in re.findall(r"[a-záéíóúüñ0-9][a-záéíóúüñ0-9_+./-]{2,}", question.casefold())
            if word not in stop and not word.isdigit()
        }

    def _claims_for_open_question(
        self,
        question: str,
        claims: list[ScientificGraphNode],
        *,
        limit: int = 80,
    ) -> list[ScientificGraphNode]:
        """Select bounded, question-relevant validated claims when no contradiction exists.

        This is retrieval only. It does not infer support, novelty or causality.
        """
        terms = self._question_terms(question)
        ranked: list[tuple[int, str, ScientificGraphNode]] = []
        for claim in claims:
            haystack = f"{claim.label} {claim.properties}".casefold()
            score = sum(1 for term in terms if term in haystack)
            ranked.append((score, claim.node_id, claim))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        if terms and any(score > 0 for score, _, _ in ranked):
            relevant = [claim for score, _, claim in ranked if score > 0]
            # Preserve some broader corpus context so the model can consider alternatives
            # rather than overfit only to lexical matches.
            broader = [claim for score, _, claim in ranked if score == 0]
            return (relevant[:60] + broader[:20])[:limit]
        return [claim for _, _, claim in ranked[:limit]]

    def generate_hypotheses(self, question: str) -> HypothesisCompetition:
        question = question.strip()
        if not question:
            raise ValueError("question is required")

        contradictions = self.graph_store.list_contradictions(limit=1000)
        nodes = self.graph_store.list_nodes(limit=10000)
        node_by_id = {n.node_id: n for n in nodes}
        all_claims = [n for n in nodes if n.node_type == GraphNodeType.CLAIM]
        if not all_claims:
            raise ValueError(
                "No validated claim nodes are available. Build the scientific graph from full-text-reviewed papers first."
            )

        involved_claim_ids = {
            cid
            for item in contradictions
            for cid in (item.claim_a_id, item.claim_b_id)
        }
        if involved_claim_ids:
            claims = [node_by_id[cid] for cid in involved_claim_ids if cid in node_by_id][:100]
        else:
            claims = self._claims_for_open_question(question, all_claims, limit=80)
            involved_claim_ids = {claim.node_id for claim in claims}

        edges = self.graph_store.list_edges(limit=20000)
        evidence_ids = {
            edge.target_node_id
            for edge in edges
            if edge.relation == GraphRelation.SUPPORTED_BY and edge.source_node_id in involved_claim_ids
        }
        evidence = [
            node_by_id[eid]
            for eid in evidence_ids
            if eid in node_by_id and node_by_id[eid].node_type == GraphNodeType.EVIDENCE
        ][:160]

        competition = HypothesisCompetitionAgent(self.provider).generate(
            question,
            claims,
            evidence,
            contradictions,
        )
        self.graph_store.replace_competition(competition)
        return competition

    def summary(self) -> dict[str, Any]:
        return self.graph_store.summary()
