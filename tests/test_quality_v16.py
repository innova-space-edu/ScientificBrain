import json

from scientific_brain.quality_control import select_repair_sections
from scientific_brain.telemetry_provider import estimate_cost_usd


def test_provider_reported_cost_has_priority(monkeypatch):
    monkeypatch.setenv(
        "SCIBRAIN_MODEL_PRICING_JSON",
        json.dumps({"google:model-x": {"input_per_million": 99, "output_per_million": 99}}),
    )
    cost, source = estimate_cost_usd("google", "model-x", 1000, 500, reported_cost=0.0123)
    assert cost == 0.0123
    assert source == "provider_reported"


def test_configured_cost_uses_exact_recorded_tokens(monkeypatch):
    monkeypatch.setenv(
        "SCIBRAIN_MODEL_PRICING_JSON",
        json.dumps({"google:model-x": {"input_per_million": 1.0, "output_per_million": 2.0}}),
    )
    cost, source = estimate_cost_usd("google", "model-x", 1_000_000, 500_000)
    assert cost == 2.0
    assert source == "configured_rate"


def test_repair_selection_never_selects_user_edited_sections():
    sections = {
        "analysis": {"text": "AI text", "user_edited": False},
        "conclusion": {"text": "Human text", "user_edited": True},
        "abstract": {"text": "OK", "user_edited": False},
    }
    gates = {
        "analysis": {"passed": False},
        "conclusion": {"passed": False},
        "abstract": {"passed": True},
    }
    benchmark = {
        "analysis": {"contradicted": 0, "insufficient": 1},
        "conclusion": {"contradicted": 1, "insufficient": 0},
        "abstract": {"contradicted": 0, "insufficient": 0},
    }
    repair, blocked = select_repair_sections(sections, gates, benchmark, 4)
    assert repair == ["analysis"]
    assert blocked == ["conclusion"]
