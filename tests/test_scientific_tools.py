from scientific_brain.nvidia_provider import physics_toolkit_manifest
from scientific_brain.physics_jobs import physics_model_catalog


def test_scientific_tools_manifest_exposes_expanded_physics_stack():
    manifest = physics_toolkit_manifest()
    assert manifest["repository"].endswith("scientificbrain-physics-skills")
    assert len(manifest["skills"]) == 39
    assert "flash-physicsnemo-pipeline" in manifest["skills"]
    assert "scientificbrain-orchestration" in manifest["skills"]
    assert "distributed simulation/training" in manifest["implemented_extensions"]
    assert manifest["source_grounded"] is True


def test_physics_model_catalog_has_multiple_models_per_stack():
    catalog = physics_model_catalog()["solvers"]
    assert catalog["flash"]["default_model"] == "hall-mhd"
    assert {x["id"] for x in catalog["flash"]["models"]} >= {"ideal-mhd", "resistive-mhd", "hall-mhd", "extended-mhd"}
    assert {x["id"] for x in catalog["warpx"]["models"]} >= {"hybrid-pic", "full-pic-em", "pic-mcc", "pic-dsmc"}
    assert {x["id"] for x in catalog["physicsnemo"]["models"]} >= {"fno", "pino", "meshgraphnet", "pinn", "transolver"}
