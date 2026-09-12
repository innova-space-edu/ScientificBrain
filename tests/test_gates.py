from scientific_brain.gates import evidence_gate, provenance_gate, reproducibility_gate
from scientific_brain.models import Claim, Evidence, PaperAnalysis, PaperKind


def _analysis():
    evidence = Evidence(
        evidence_id="e1",
        paper_id="doi:test",
        text="Measured current peaks at 10 A.",
        section="Results",
        page=3,
    )
    claim = Claim(
        claim_id="c1",
        paper_id="doi:test",
        text="Peak current is 10 A.",
        claim_type="result",
        evidence_ids=["e1"],
        confidence=0.95,
    )
    return PaperAnalysis(
        paper_id="doi:test",
        physical_model=["circuit-plasma coupling"],
        assumptions=["axisymmetric approximation"],
        experimental_parameters={"charging_voltage": "1 kV"},
        diagnostics=["current probe"],
        uncertainty=["5% current calibration"],
        reproducibility=["probe model and acquisition rate reported"],
        evidence=[evidence],
        claims=[claim],
    )


def test_evidence_and_provenance_gates_pass():
    analysis = _analysis()
    assert evidence_gate(analysis).passed
    assert provenance_gate(analysis).passed


def test_evidence_gate_rejects_dangling_claim():
    analysis = _analysis()
    analysis.claims[0].evidence_ids = ["missing"]
    result = evidence_gate(analysis)
    assert not result.passed
    assert result.blockers


def test_reproducibility_gate_is_kind_aware():
    analysis = _analysis()
    result = reproducibility_gate(analysis, PaperKind.EXPERIMENTAL)
    assert result.passed
    assert result.score >= 0.7
