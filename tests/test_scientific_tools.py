import pytest

from scientific_brain.google_batch import normalize_google_batch_state
from scientific_brain.nvidia_provider import physics_toolkit_manifest
from scientific_brain.physics_jobs import physics_model_catalog, prepare_physics_job
from scientific_brain.physics_tools import route_physics_model, validate_physics_observables


def test_scientific_tools_manifest_exposes_expanded_physics_stack():
    manifest = physics_toolkit_manifest()
    assert manifest["repository"].endswith("scientificbrain-physics-skills")
    assert manifest["version"] == "0.3.0"
    assert len(manifest["skills"]) == 44
    assert "flash-physicsnemo-pipeline" in manifest["skills"]
    assert "scientificbrain-orchestration" in manifest["skills"]
    assert "physics-model-router" in manifest["skills"]
    assert "physics-literature" in manifest["skills"]
    assert "physics-validator" in manifest["skills"]
    assert "simulation-orchestrator" in manifest["skills"]
    assert "workflow-skill-creator" in manifest["skills"]
    assert "distributed simulation/training" in manifest["implemented_extensions"]
    assert "unit/workflow/capability evaluation contracts" in manifest["implemented_extensions"]
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


def test_scientific_tools_high_level_router_contract():
    result = route_physics_model({
        "domain": "particle-transport",
        "observable": "energy deposition",
        "acceptance_criterion": "uncertainty below 5%",
        "particle_through_matter": True,
    })
    assert result["schema_version"] == "0.3"
    assert result["next_skill"] == "simulation-orchestrator"


def test_scientific_tools_validation_contract_never_claims_global_validity():
    result = validate_physics_observables({
        "observables": [{
            "name": "dose",
            "required_checks": ["benchmark"],
            "checks": {"benchmark": {"status": "pass", "evidence": "validated reference"}},
        }]
    })
    assert result["global_validity_claim"] is False
    assert result["skill"] == "physics-validator"
