from scientific_brain.nvidia_provider import physics_toolkit_manifest


def test_scientific_tools_manifest_exposes_expanded_physics_stack():
    manifest = physics_toolkit_manifest()
    assert manifest["repository"].endswith("scientificbrain-physics-skills")
    assert len(manifest["skills"]) == 39
    assert "flash-physicsnemo-pipeline" in manifest["skills"]
    assert "scientificbrain-orchestration" in manifest["skills"]
    assert "distributed simulation/training" in manifest["implemented_extensions"]
    assert manifest["source_grounded"] is True
