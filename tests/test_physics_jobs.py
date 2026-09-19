import pytest
from pydantic import ValidationError

from scientific_brain.physics_jobs import (
    physics_execution_profiles,
    prepare_physics_job,
)


def test_profiles_cover_all_execution_engines():
    profiles = physics_execution_profiles()["profiles"]
    assert set(profiles) == {
        "flash", "warpx", "picongpu", "edipic2d", "geant4", "physicsnemo"
    }


def test_prepare_warpx_job():
    job = prepare_physics_job({
        "solver": "warpx",
        "action": "run",
        "model": "hybrid-pic",
        "input_artifact": "campaigns/shock-01/inputs",
        "parameters": {"substeps": 10, "openpmd": True},
        "resources": {"nodes": 2, "cpus": 64, "gpus": 4, "memory_gb": 256, "wall_minutes": 120},
        "validation": ["charge conservation", "energy balance"],
    })
    assert job["dispatch_state"] == "prepared"
    assert job["solver"] == "warpx"
    assert job["execution_profile"]["canonical_adapter"] == "openPMD"


@pytest.mark.parametrize("key", ["command", "endpoint", "api_key", "secret", "token"])
def test_client_cannot_inject_execution_controls(key):
    with pytest.raises(ValidationError):
        prepare_physics_job({
            "solver": "flash",
            "action": "run",
            "model": "hall-mhd",
            "input_artifact": "runs/a",
            "parameters": {key: "malicious"},
        })


def test_url_input_artifact_rejected():
    with pytest.raises(ValidationError):
        prepare_physics_job({
            "solver": "geant4",
            "action": "run",
            "model": "shielding",
            "input_artifact": "https://attacker.invalid/payload",
        })


def test_solver_action_contract():
    with pytest.raises(ValidationError):
        prepare_physics_job({
            "solver": "flash",
            "action": "train",
            "model": "mhd",
            "input_artifact": "runs/a",
        })
