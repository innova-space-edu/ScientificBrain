from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value).strip()


def _unique(values: list[Any], limit: int = 24) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value).strip()
        if not text:
            continue
        key = re.sub(r"\s+", " ", text).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _pointer(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": evidence.get("evidence_id"),
        "page": evidence.get("page"),
        "section": evidence.get("section"),
        "equation": evidence.get("equation"),
        "figure": evidence.get("figure"),
        "strength": evidence.get("strength"),
    }


def _claim_entry(claim: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    refs = [
        _pointer(evidence_by_id[eid])
        for eid in claim.get("evidence_ids") or []
        if eid in evidence_by_id
    ]
    return {
        "claim_id": claim.get("claim_id"),
        "text": _text(claim.get("text")),
        "claim_type": claim.get("claim_type") or "other",
        "confidence": claim.get("confidence"),
        "evidence": refs,
    }


def _normal_key(value: str) -> str:
    return re.sub(r"[^a-z0-9áéíóúüñ]+", " ", value.casefold()).strip()


def _recurring(rows: list[dict[str, Any]], field: str, *, min_papers: int = 2, limit: int = 18) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    papers_by_key: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        paper_id = str(row.get("paper_id") or "")
        values = row.get(field) or []
        if field == "variables":
            values = [x.get("name") for x in values if isinstance(x, dict)]
        for value in values:
            text = _text(value)
            key = _normal_key(text)
            if not key:
                continue
            by_key.setdefault(key, {"label": text})
            papers_by_key[key].add(paper_id)
    items = [
        {"label": by_key[key]["label"], "paper_count": len(papers), "paper_ids": sorted(papers)}
        for key, papers in papers_by_key.items()
        if len(papers) >= min_papers
    ]
    items.sort(key=lambda item: (-item["paper_count"], item["label"].casefold()))
    return items[:limit]


def build_state_of_art_matrix(papers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic literature matrix from stored full-text paper analyses.

    No cross-paper scientific relation is invented here. Every cell is copied or
    mechanically organized from accepted analysis fields, claims, critique and
    specialist reviews.
    """
    rows: list[dict[str, Any]] = []
    skipped = 0
    for paper in papers:
        if paper.get("review_depth") != "full_text_reviewed":
            skipped += 1
            continue
        analysis = paper.get("analysis") or {}
        if not isinstance(analysis, dict) or not analysis:
            skipped += 1
            continue
        critique = paper.get("critique") or {}
        specialist = paper.get("specialist_reviews") or []
        evidence = [x for x in analysis.get("evidence") or [] if isinstance(x, dict)]
        evidence_by_id = {
            str(item.get("evidence_id")): item
            for item in evidence
            if item.get("evidence_id")
        }
        claims = [x for x in analysis.get("claims") or [] if isinstance(x, dict)]
        claim_entries = [_claim_entry(claim, evidence_by_id) for claim in claims]
        results = [x for x in claim_entries if x.get("claim_type") == "result"]
        methods = [x for x in claim_entries if x.get("claim_type") == "method"]
        claim_limitations = [x.get("text") for x in claim_entries if x.get("claim_type") == "limitation"]
        claim_hypotheses = [x for x in claim_entries if x.get("claim_type") == "hypothesis"]

        parameters = analysis.get("experimental_parameters") or {}
        variables = [
            {"name": str(key), "value": _text(value)}
            for key, value in parameters.items()
            if str(key).strip()
        ]
        simulation_setup = analysis.get("simulation_setup") or {}
        simulation = [
            {"name": str(key), "value": _text(value)}
            for key, value in simulation_setup.items()
            if str(key).strip()
        ]
        proposed_tests: list[Any] = []
        if isinstance(critique, dict):
            proposed_tests.extend(critique.get("proposed_tests") or [])
        for review in specialist:
            if isinstance(review, dict):
                proposed_tests.extend(review.get("proposed_tests") or [])

        locations: list[str] = []
        for item in evidence:
            parts: list[str] = []
            if item.get("page") not in (None, ""):
                parts.append(f"p. {item.get('page')}")
            if item.get("section"):
                parts.append(str(item.get("section")))
            if item.get("equation"):
                parts.append(f"eq. {item.get('equation')}")
            if item.get("figure"):
                parts.append(f"fig. {item.get('figure')}")
            if parts:
                locations.append(" · ".join(parts))

        rows.append({
            "paper_id": paper.get("canonical_id"),
            "title": paper.get("title"),
            "publication_date": paper.get("publication_date"),
            "journal": paper.get("journal"),
            "doi": paper.get("doi"),
            "kind": analysis.get("inferred_kind") or (paper.get("record") or {}).get("kind") or "unknown",
            "summary": _text(analysis.get("summary")),
            "regimes": _unique(list(analysis.get("plasma_regime") or [])),
            "mechanisms": _unique(list(analysis.get("physical_model") or [])),
            "variables": variables[:30],
            "simulation_setup": simulation[:24],
            "diagnostics": _unique(list(analysis.get("diagnostics") or [])),
            "methods": methods[:20],
            "results": results[:30],
            "hypotheses": claim_hypotheses[:16],
            "equations": _unique(list(analysis.get("equations") or []), 24),
            "initial_conditions": _unique(list(analysis.get("initial_conditions") or [])),
            "boundary_conditions": _unique(list(analysis.get("boundary_conditions") or [])),
            "uncertainties": _unique(list(analysis.get("uncertainty") or [])),
            "limitations": _unique([*(analysis.get("limitations") or []), *claim_limitations], 30),
            "reproducibility": _unique(list(analysis.get("reproducibility") or [])),
            "proposed_tests": _unique(proposed_tests, 24),
            "evidence_locations": _unique(locations, 20),
            "evidence_count": len(evidence),
            "claim_count": len(claim_entries),
            "direct_evidence_count": sum(str(x.get("strength") or "") == "direct" for x in evidence),
        })

    coverage = {
        "full_text_papers": len(rows),
        "skipped_or_not_full_text": skipped,
        "papers_with_results": sum(bool(row["results"]) for row in rows),
        "papers_with_uncertainty": sum(bool(row["uncertainties"]) for row in rows),
        "papers_with_limitations": sum(bool(row["limitations"]) for row in rows),
        "papers_with_diagnostics": sum(bool(row["diagnostics"]) for row in rows),
        "papers_with_equations": sum(bool(row["equations"]) for row in rows),
        "evidence_records": sum(int(row["evidence_count"]) for row in rows),
        "claims": sum(int(row["claim_count"]) for row in rows),
    }
    recurring = {
        "regimes": _recurring(rows, "regimes"),
        "mechanisms": _recurring(rows, "mechanisms"),
        "variables": _recurring(rows, "variables"),
        "diagnostics": _recurring(rows, "diagnostics"),
        "equations": _recurring(rows, "equations"),
    }
    fingerprint_source = [
        {
            "paper_id": row.get("paper_id"),
            "claim_count": row.get("claim_count"),
            "evidence_count": row.get("evidence_count"),
            "results": [x.get("claim_id") for x in row.get("results") or []],
        }
        for row in rows
    ]
    fingerprint = hashlib.sha1(
        json.dumps(fingerprint_source, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "version": "state_of_art_matrix_v1",
        "fingerprint": fingerprint,
        "coverage": coverage,
        "recurring_dimensions": recurring,
        "rows": rows,
        "epistemic_note": (
            "The matrix is deterministic organization of stored full-text analyses. "
            "Recurring items are shared dimensions, not proof of consensus or causality."
        ),
    }
