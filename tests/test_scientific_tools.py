import pytest

from scientific_brain.google_batch import normalize_google_batch_state
from scientific_brain.nvidia_provider import physics_toolkit_manifest
from scientific_brain.physics_jobs import physics_model_catalog, prepare_physics_job


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


def test_flash_run_requires_explicit_setup_and_keeps_validation_separate():
    payload = {
        "solver": "flash",
        "action": "run",
        "model": "ideal-mhd",
        "input_artifact": "benchmarks/mhd-shock",
        "parameters": {},
    }
    with pytest.raises(ValueError, match="flash_setup"):
        prepare_physics_job(payload)

    payload["parameters"] = {"flash_setup": "MagnetoHD/BrioWu"}
    prepared = prepare_physics_job(payload)
    assert prepared["execution_state"] == "prepared"
    assert prepared["scientific_validation"]["state"] == "not_evaluated"
    assert "benchmark" in prepared["scientific_validation"]["required_checks"]


def test_google_batch_lifecycle_is_normalized_without_fake_percentage():
    running = normalize_google_batch_state({"state": "RUNNING"})
    assert running == {
        "batch_state": "RUNNING",
        "execution_state": "running",
        "terminal": False,
        "success": False,
        "progress_source": "google_batch_state",
    }
    finished = normalize_google_batch_state({"state": "SUCCEEDED"})
    assert finished["execution_state"] == "finished"
    assert finished["terminal"] is True
    assert finished["success"] is True
