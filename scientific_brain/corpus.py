from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from .memory import ScientificMemory
from .models import CorpusAudit, PaperKind, ReviewDepth


def load_corpus_policy(path: str | Path = "config/corpus_policy.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def audit_corpus(memory: ScientificMemory, policy: dict) -> CorpusAudit:
    papers = memory.list_papers()
    method_counts = Counter(p.kind.value for p in papers)
    domain_counts: Counter[str] = Counter()
    time_counts: Counter[str] = Counter()

    for paper in papers:
        domain_counts.update(set(paper.plasma_topics))
        year = paper.publication_date.year if paper.publication_date else None
        if year is None:
            time_counts["unknown"] += 1
        elif year < 2015:
            time_counts["foundational_pre_2015"] += 1
        elif year <= 2023:
            time_counts["consolidation_2015_2023"] += 1
        else:
            time_counts["recent_2024_plus"] += 1

    deep = 0
    for paper in papers:
        status = memory.get_review_status(paper.canonical_id)
        if status and status["review_depth"] == ReviewDepth.FULL_TEXT.value:
            deep += 1

    req = policy.get("requirements", {})
    requirement_results = {
        "target_papers": len(papers) >= int(policy.get("target_papers", 100)),
        "minimum_recent_papers_2024_plus": (
            time_counts["recent_2024_plus"] >= int(req.get("minimum_recent_papers_2024_plus", 0))
        ),
        "minimum_reviews_or_roadmaps": (
            method_counts[PaperKind.REVIEW.value] >= int(req.get("minimum_reviews_or_roadmaps", 0))
        ),
        "minimum_experimental": (
            method_counts[PaperKind.EXPERIMENTAL.value] >= int(req.get("minimum_experimental", 0))
        ),
        "minimum_simulation": (
            method_counts[PaperKind.SIMULATION.value] >= int(req.get("minimum_simulation", 0))
        ),
        "minimum_theoretical": (
            method_counts[PaperKind.THEORETICAL.value] >= int(req.get("minimum_theoretical", 0))
        ),
        "deep_analysis_count": deep >= int(req.get("deep_analysis_count", policy.get("target_papers", 100))),
    }

    return CorpusAudit(
        target_papers=int(policy.get("target_papers", 100)),
        total_papers=len(papers),
        deep_analysis_count=deep,
        method_counts=dict(method_counts),
        time_counts=dict(time_counts),
        domain_counts=dict(domain_counts),
        requirement_results=requirement_results,
        passed=all(requirement_results.values()),
    )


def coverage_gaps(memory: ScientificMemory, policy: dict) -> dict[str, int]:
    """Return only unmet soft domain quotas, expressed as papers still needed."""
    audit = audit_corpus(memory, policy)
    gaps: dict[str, int] = {}
    for topic, target in policy.get("domain_targets", {}).items():
        current = audit.domain_counts.get(topic, 0)
        if current < int(target):
            gaps[topic] = int(target) - current
    return gaps
