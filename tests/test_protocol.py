from scientific_brain.epistemics import transition_allowed
from scientific_brain.models import GateResult
from scientific_brain.protocol_engine import ResearchProtocolEngine


def test_protocol_blocks_missing_artifacts_and_gates():
    engine = ResearchProtocolEngine()
    decision = engine.validate_stage("definition", artifacts={}, gate_results=[])
    assert not decision.passed
    assert "project_definition" in decision.missing_artifacts
    assert "research_definition" in decision.failed_gates


def test_protocol_passes_when_definition_is_complete():
    engine = ResearchProtocolEngine()
    decision = engine.validate_stage(
        "definition",
        artifacts={"project_definition": {"project_id": "p1"}},
        gate_results=[GateResult(name="research_definition", passed=True, score=1.0)],
    )
    assert decision.passed
    assert engine.next_stage("definition") == "literature"


def test_inferred_cannot_be_silently_rewritten_as_measured():
    allowed, reasons = transition_allowed("inferred", "measured", set())
    assert not allowed
    assert reasons


def test_hypothesis_promotion_requires_discriminating_evidence():
    allowed, reasons = transition_allowed(
        "hypothesis",
        "supported",
        {"uncertainty_accounted", "viable_alternatives_considered"},
    )
    assert not allowed
    assert any("discriminating_evidence" in reason for reason in reasons)
