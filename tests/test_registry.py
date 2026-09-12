from scientific_brain.registry import load_agent_registry, load_research_protocol, scientific_manifest


def test_agent_registry_is_explicit_and_unique():
    registry = load_agent_registry()
    ids = [agent["id"] for agent in registry["agents"]]
    assert len(ids) >= 16
    assert len(ids) == len(set(ids))
    assert "research_director" in ids
    assert "reviewer" in ids


def test_protocol_has_complete_stage_sequence():
    protocol = load_research_protocol()
    ids = [stage["id"] for stage in protocol["stages"]]
    assert ids[0] == "definition"
    assert ids[-1] == "review"
    assert "criticism" in ids
    assert "reproducibility" in ids


def test_manifest_exposes_hard_rules():
    manifest = scientific_manifest()
    assert manifest["agents"]
    assert manifest["stages"]
    assert "no_stage_passes_only_because_text_is_fluent" in manifest["hard_rules"]
