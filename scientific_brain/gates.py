from __future__ import annotations

from .models import GateResult, PaperAnalysis, PaperKind


def evidence_gate(analysis: PaperAnalysis) -> GateResult:
    """Require every extracted claim to point to stored evidence."""
    if not analysis.claims:
        return GateResult(
            name="evidence",
            passed=False,
            score=0.0,
            blockers=["No claims were extracted from the paper."],
        )

    evidence_ids = {item.evidence_id for item in analysis.evidence}
    unsupported: list[str] = []
    dangling: list[str] = []
    for claim in analysis.claims:
        if not claim.evidence_ids:
            unsupported.append(claim.claim_id)
            continue
        missing = [item for item in claim.evidence_ids if item not in evidence_ids]
        if missing:
            dangling.append(f"{claim.claim_id}: {', '.join(missing)}")

    supported = len(analysis.claims) - len(unsupported) - len(dangling)
    score = max(0.0, supported / len(analysis.claims))
    blockers = []
    if unsupported:
        blockers.append("Claims without evidence pointers: " + ", ".join(unsupported))
    if dangling:
        blockers.append("Claims referencing missing evidence: " + " | ".join(dangling))

    return GateResult(
        name="evidence",
        passed=not blockers,
        score=score,
        blockers=blockers,
        details={
            "claims": len(analysis.claims),
            "evidence_items": len(analysis.evidence),
            "supported_claims": supported,
        },
    )


def provenance_gate(analysis: PaperAnalysis) -> GateResult:
    """Check that evidence can be traced to a location in the source."""
    if not analysis.evidence:
        return GateResult(
            name="provenance",
            passed=False,
            score=0.0,
            blockers=["No evidence records are available."],
        )

    foreign = [
        item.evidence_id
        for item in analysis.evidence
        if item.paper_id != analysis.paper_id
    ]
    no_pointer = [
        item.evidence_id
        for item in analysis.evidence
        if not item.has_source_pointer
    ]

    pointer_count = len(analysis.evidence) - len(no_pointer)
    score = pointer_count / len(analysis.evidence)
    blockers = []
    warnings = []
    if foreign:
        blockers.append("Evidence assigned to a different paper: " + ", ".join(foreign))
    if no_pointer:
        warnings.append(
            "Evidence without section/page/equation/figure pointer: " + ", ".join(no_pointer)
        )

    return GateResult(
        name="provenance",
        passed=not foreign and score >= 0.8,
        score=score,
        blockers=blockers,
        warnings=warnings,
        details={
            "evidence_items": len(analysis.evidence),
            "items_with_pointer": pointer_count,
        },
    )


def reproducibility_gate(analysis: PaperAnalysis, kind: PaperKind) -> GateResult:
    """Measure whether the extraction contains enough information to reproduce or audit the work.

    Missing reporting is not treated as proof that the paper is invalid. It lowers the
    reproducibility score and is surfaced explicitly.
    """
    checks: list[tuple[str, bool]] = [
        ("physical_model", bool(analysis.physical_model)),
        ("assumptions", bool(analysis.assumptions)),
        ("uncertainty_or_limitations", bool(analysis.uncertainty or analysis.limitations)),
        ("reproducibility_notes", bool(analysis.reproducibility)),
    ]

    if kind in {PaperKind.EXPERIMENTAL, PaperKind.HYBRID}:
        checks.extend([
            ("experimental_parameters", bool(analysis.experimental_parameters)),
            ("diagnostics", bool(analysis.diagnostics)),
        ])
    if kind in {PaperKind.THEORETICAL, PaperKind.HYBRID}:
        checks.extend([
            ("equations", bool(analysis.equations)),
        ])
    if kind in {PaperKind.SIMULATION, PaperKind.HYBRID}:
        checks.extend([
            ("simulation_setup", bool(analysis.simulation_setup)),
            ("initial_conditions", bool(analysis.initial_conditions)),
            ("boundary_conditions", bool(analysis.boundary_conditions)),
        ])

    completed = [name for name, present in checks if present]
    missing = [name for name, present in checks if not present]
    score = len(completed) / len(checks) if checks else 1.0

    return GateResult(
        name="reproducibility",
        passed=score >= 0.70,
        score=score,
        warnings=[f"Missing or unreported reproducibility field: {name}" for name in missing],
        details={
            "checks": len(checks),
            "completed": len(completed),
            "missing": len(missing),
        },
    )


def run_paper_gates(analysis: PaperAnalysis, kind: PaperKind) -> list[GateResult]:
    return [
        evidence_gate(analysis),
        provenance_gate(analysis),
        reproducibility_gate(analysis, kind),
    ]
