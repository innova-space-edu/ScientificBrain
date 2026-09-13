from __future__ import annotations

import hashlib

from .agents import _complete_model
from .graph_models import (
    CompetingHypothesis,
    ContradictionBatch,
    ContradictionRecord,
    HypothesisCompetition,
    ScientificGraphNode,
)


CONTRADICTION_SYSTEM = """You are ScientificBrain Contradiction Analyst.
Your job is not to manufacture disagreements. Compare only claims provided in the input.
A contradiction candidate must involve two different claim node IDs and a scientifically meaningful
incompatibility: opposite trend, incompatible magnitude/regime conclusion, mutually exclusive
mechanism, or a result that cannot simultaneously hold under the same stated conditions.

Before calling two claims contradictory, actively check whether the difference can be explained by
regime, geometry, diagnostic, model assumptions, initial/boundary conditions, dimensionality,
collisionality, magnetization, uncertainty or normalization. If those differences plausibly reconcile
the claims, classify the item as a conditional/apparent contradiction and say what must be measured
or controlled to discriminate them.

Do not treat different questions as contradictions. Do not infer facts absent from the supplied claim
records. Every output pair must use exact graph claim node IDs from the input. Set status=candidate.
"""


HYPOTHESIS_SYSTEM = """You are ScientificBrain Hypothesis Competition Agent.
Given validated claim nodes, evidence nodes and contradiction candidates, generate competing,
falsifiable scientific hypotheses that can explain the disagreement. Include a null/measurement or
regime explanation when scientifically appropriate. Each hypothesis must state mechanism, domain of
validity, predictions, discriminating observables, an experiment or simulation that distinguishes it,
and an explicit rejection criterion.

Do not select a winner because a statement sounds plausible. Link only to graph claim/evidence IDs
that are present in the supplied context. If evidence is insufficient, retain uncertainty and specify
the decisive missing measurement. Return a competition, not a narrative essay.
"""


def _stable(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha1(value.encode('utf-8')).hexdigest()[:20]}"


class ContradictionAgent:
    def __init__(self, provider) -> None:
        self.provider = provider

    def detect(self, claims: list[ScientificGraphNode], context: str = "") -> list[ContradictionRecord]:
        if len(claims) < 2:
            return []
        compact = [
            {
                "claim_node_id": node.node_id,
                "paper_id": node.paper_id,
                "text": node.label,
                "epistemic_state": node.epistemic_state.value,
                "properties": node.properties,
            }
            for node in claims
        ]
        batch = _complete_model(
            self.provider,
            CONTRADICTION_SYSTEM,
            "CONTEXT:\n" + context + "\n\nCLAIMS:\n" + __import__("json").dumps(compact, ensure_ascii=False),
            ContradictionBatch,
        )
        valid_ids = {node.node_id for node in claims}
        results: list[ContradictionRecord] = []
        seen: set[tuple[str, str]] = set()
        for item in batch.contradictions:
            if item.claim_a_id not in valid_ids or item.claim_b_id not in valid_ids:
                continue
            if item.claim_a_id == item.claim_b_id:
                continue
            pair = tuple(sorted((item.claim_a_id, item.claim_b_id)))
            if pair in seen:
                continue
            seen.add(pair)
            item.contradiction_id = _stable("contradiction", "|".join(pair))
            item.status = "candidate"
            results.append(item)
        return results


class HypothesisCompetitionAgent:
    def __init__(self, provider) -> None:
        self.provider = provider

    def generate(
        self,
        question: str,
        claims: list[ScientificGraphNode],
        evidence: list[ScientificGraphNode],
        contradictions: list[ContradictionRecord],
    ) -> HypothesisCompetition:
        import json

        payload = {
            "question": question,
            "claims": [
                {"id": n.node_id, "paper_id": n.paper_id, "text": n.label, "state": n.epistemic_state.value}
                for n in claims
            ],
            "evidence": [
                {"id": n.node_id, "paper_id": n.paper_id, "text": n.label, "properties": n.properties}
                for n in evidence
            ],
            "contradictions": [item.model_dump(mode="json") for item in contradictions],
        }
        competition = _complete_model(
            self.provider,
            HYPOTHESIS_SYSTEM,
            json.dumps(payload, ensure_ascii=False),
            HypothesisCompetition,
        )
        valid_claims = {n.node_id for n in claims}
        valid_evidence = {n.node_id for n in evidence}
        valid_contradictions = {c.contradiction_id for c in contradictions}
        competition.competition_id = _stable(
            "competition",
            question + "|" + "|".join(sorted(valid_contradictions)),
        )
        competition.contradiction_ids = [
            cid for cid in competition.contradiction_ids if cid in valid_contradictions
        ] or sorted(valid_contradictions)
        cleaned: list[CompetingHypothesis] = []
        for index, hypothesis in enumerate(competition.hypotheses, start=1):
            hypothesis.hypothesis_id = _stable(
                "hypothesis",
                competition.competition_id + "|" + str(index) + "|" + hypothesis.statement,
            )
            hypothesis.explains_claim_ids = [cid for cid in hypothesis.explains_claim_ids if cid in valid_claims]
            hypothesis.supporting_evidence_ids = [eid for eid in hypothesis.supporting_evidence_ids if eid in valid_evidence]
            hypothesis.contradicting_evidence_ids = [eid for eid in hypothesis.contradicting_evidence_ids if eid in valid_evidence]
            hypothesis.status = "candidate"
            cleaned.append(hypothesis)
        competition.hypotheses = cleaned
        return competition
