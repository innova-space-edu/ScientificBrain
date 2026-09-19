from scientific_brain.nvidia_provider import physics_toolkit_manifest


def test_scientific_tools_manifest_exposes_physics_stack():
    manifest = physics_toolkit_manifest()
    assert manifest["repository"].endswith("scientificbrain-physics-skills")
    assert "flash-physicsnemo-pipeline" in manifest["skills"]
    assert "distributed simulation/training" in manifest["planned_extensions"]
