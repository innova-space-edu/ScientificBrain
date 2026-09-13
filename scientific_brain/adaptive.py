from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .models import Claim, Evidence, PaperAnalysis, PaperKind, ReviewDepth


@dataclass(frozen=True)
class DocumentProfile:
    page_count: int
    character_count: int
    word_count: int
    estimated_tokens: int


@dataclass(frozen=True)
class ReviewPlan:
    mode: str
    pages_per_chunk: int
    chunk_ranges: tuple[tuple[int, int], ...]
    rationale: str


@dataclass(frozen=True)
class CorpusPlan:
    mode: str
    paper_count: int
    dispatch_batch_size: int
    synthesis_group_size: int
    evidence_warning: str | None


def profile_document(page_texts: Iterable[str]) -> DocumentProfile:
    pages = list(page_texts)
    text = "\n".join(pages)
    characters = len(text)
    words = len(text.split())
    estimated_tokens = max(1, (characters + 3) // 4)
    return DocumentProfile(
        page_count=len(pages),
        character_count=characters,
        word_count=words,
        estimated_tokens=estimated_tokens,
    )


def _ranges(page_count: int, pages_per_chunk: int) -> tuple[tuple[int, int], ...]:
    if page_count <= 0:
        return ()
    result: list[tuple[int, int]] = []
    start = 1
    while start <= page_count:
        end = min(page_count, start + pages_per_chunk - 1)
        result.append((start, end))
        start = end + 1
    return tuple(result)


def _bounded_pages(profile: DocumentProfile, base_pages: int, target_tokens: int = 12000) -> int:
    average = max(1, profile.estimated_tokens // max(1, profile.page_count))
    token_bounded = max(1, target_tokens // average)
    return max(1, min(base_pages, token_bounded))


def plan_review(profile: DocumentProfile) -> ReviewPlan:
    """Select a bounded strategy from both page count and extracted-text size."""

    if profile.page_count <= 12 and profile.estimated_tokens <= 24000:
        pages = max(1, profile.page_count)
        return ReviewPlan(
            mode="direct",
            pages_per_chunk=pages,
            chunk_ranges=_ranges(profile.page_count, pages),
            rationale="Short paper: one full-context extraction preserves cross-section relationships.",
        )
    if profile.page_count <= 35 and profile.estimated_tokens <= 65000:
        pages = _bounded_pages(profile, 8)
        return ReviewPlan(
            mode="sectional",
            pages_per_chunk=pages,
            chunk_ranges=_ranges(profile.page_count, pages),
            rationale="Medium paper: section-sized extraction prevents provider/context overflow.",
        )
    base = 6 if profile.page_count <= 80 else 5
    pages = _bounded_pages(profile, base)
    return ReviewPlan(
        mode="hierarchical",
        pages_per_chunk=pages,
        chunk_ranges=_ranges(profile.page_count, pages),
        rationale="Long paper: checkpointed hierarchical extraction is required for completeness and resumability.",
    )


def plan_corpus(paper_count: int) -> CorpusPlan:
    n = max(0, int(paper_count))
    if n <= 5:
        return CorpusPlan(
            mode="deep_small_corpus",
            paper_count=n,
            dispatch_batch_size=max(1, n),
            synthesis_group_size=max(1, n),
            evidence_warning=(
                "Small corpus: conclusions must be labelled as limited by literature coverage."
                if n < 3 else None
            ),
        )
    if n <= 25:
        return CorpusPlan("balanced", n, 5, 8, None)
    if n <= 100:
        return CorpusPlan("batched", n, 8, 10, None)
    return CorpusPlan("large_corpus_hierarchical", n, 10, 12, None)


def chunk_text(document, start_page: int, end_page: int) -> str:
    pages = [p for p in document.pages if start_page <= p.page <= end_page]
    return "\n\n".join(f"[[PAGE {p.page}]]\n{p.text}" for p in pages)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def merge_chunk_analyses(paper_id: str, analyses: list[PaperAnalysis]) -> PaperAnalysis:
    """Deterministically consolidate chunk extractions without asking an LLM to re-invent facts."""

    if not analyses:
        raise ValueError("At least one chunk analysis is required")

    kinds = [a.inferred_kind for a in analyses if a.inferred_kind != PaperKind.UNKNOWN]
    inferred_kind = Counter(kinds).most_common(1)[0][0] if kinds else PaperKind.UNKNOWN

    evidence: list[Evidence] = []
    claims: list[Claim] = []
    evidence_id_map: dict[tuple[int, str], str] = {}

    for chunk_index, analysis in enumerate(analyses, start=1):
        for item_index, item in enumerate(analysis.evidence, start=1):
            new_id = f"{paper_id}:c{chunk_index}:e{item_index}"
            evidence_id_map[(chunk_index, item.evidence_id)] = new_id
            evidence.append(item.model_copy(update={"evidence_id": new_id, "paper_id": paper_id}))

        for item_index, claim in enumerate(analysis.claims, start=1):
            mapped_ids = [
                evidence_id_map.get((chunk_index, evidence_id), evidence_id)
                for evidence_id in claim.evidence_ids
            ]
            claims.append(claim.model_copy(update={
                "claim_id": f"{paper_id}:c{chunk_index}:cl{item_index}",
                "paper_id": paper_id,
                "evidence_ids": mapped_ids,
            }))

    experimental_parameters: dict[str, str] = {}
    simulation_setup: dict[str, str] = {}
    for analysis in analyses:
        for key, value in analysis.experimental_parameters.items():
            experimental_parameters.setdefault(str(key), str(value))
        for key, value in analysis.simulation_setup.items():
            simulation_setup.setdefault(str(key), str(value))

    summaries = [a.summary.strip() for a in analyses if a.summary.strip()]
    summary = "\n\n".join(f"Chunk {i}: {text}" for i, text in enumerate(summaries, start=1))

    return PaperAnalysis(
        paper_id=paper_id,
        inferred_kind=inferred_kind,
        review_depth=ReviewDepth.FULL_TEXT,
        summary=summary,
        plasma_regime=_unique(x for a in analyses for x in a.plasma_regime),
        physical_model=_unique(x for a in analyses for x in a.physical_model),
        assumptions=_unique(x for a in analyses for x in a.assumptions),
        equations=_unique(x for a in analyses for x in a.equations),
        experimental_parameters=experimental_parameters,
        diagnostics=_unique(x for a in analyses for x in a.diagnostics),
        simulation_setup=simulation_setup,
        initial_conditions=_unique(x for a in analyses for x in a.initial_conditions),
        boundary_conditions=_unique(x for a in analyses for x in a.boundary_conditions),
        uncertainty=_unique(x for a in analyses for x in a.uncertainty),
        limitations=_unique(x for a in analyses for x in a.limitations),
        reproducibility=_unique(x for a in analyses for x in a.reproducibility),
        evidence=evidence,
        claims=claims,
    )
