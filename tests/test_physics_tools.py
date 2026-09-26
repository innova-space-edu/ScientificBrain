import json

import pytest

from scientific_brain.physics_tools import (
    monte_carlo_samples,
    physics_toolkit_manifest,
    physics_worker_status,
    route_physics_model,
    route_plasma_model,
    submit_physics_job,
    validate_physics_observables,
)


def test_manifest_has_44_source_grounded_skills():
    manifest = physics_toolkit_manifest()
    assert len(manifest["skills"]) == 44
    assert manifest["source_grounded"] is True
    assert "PIC/hybrid routing" in manifest["implemented_extensions"]
    assert "Monte Carlo / MCC / DSMC" in manifest["implemented_extensions"]
    assert "physics-model-router" in manifest["skills"]
    assert "physics-validator" in manifest["skills"]
    assert "simulation-orchestrator" in manifest["skills"]
    assert "workflow-skill-creator" in manifest["skills"]
    assert "physics-literature" in manifest["skills"]
    assert manifest["version"] == "0.3.0"


def test_router_keeps_fluid_baseline_and_can_escalate_to_pic():
    result = route_plasma_model({
        "ne": 1e18,
        "B": 0.02,
        "Te_ev": 20,
        "Ti_ev": 5,
        "L": 1e-4,
        "U": 1e5,
        "A": 1,
        "Z": 1,
        "needs_electron_kinetics": True,
    })
    models = [item["model"] for item in result["candidate_hierarchy"]]
    assert "FLASH MHD / Extended-MHD" in models
    assert "WarpX full PIC" in models
    assert "PIConGPU full PIC" in models


def test_router_can_select_geant4_transport_branch():
    result = route_plasma_model({
        "ne": 1e20,
        "B": 1,
        "Te_ev": 10,
        "Ti_ev": 10,
        "L": 0.1,
        "U": 1e4,
        "particle_through_matter": True,
    })
    assert result["candidate_hierarchy"][0]["model"] == "Geant4"


def test_monte_carlo_sampling_is_reproducible():
    payload = {
        "n": 3,
        "seed": 42,
        "distributions": {
            "B": {"dist": "normal", "mean": 2.0, "sd": 0.1},
            "Te": {"dist": "uniform", "low": 8.0, "high": 12.0},
        },
    }
    assert monte_carlo_samples(payload)["samples"] == monte_carlo_samples(payload)["samples"]


def test_monte_carlo_sample_limit():
    with pytest.raises(ValueError):
        monte_carlo_samples({
            "n": 5001,
            "distributions": {"x": {"dist": "fixed", "value": 1}},
        })


def test_worker_status_hides_endpoint_and_token_env(monkeypatch):
    monkeypatch.setenv(
        "SCIBRAIN_PHYSICS_WORKERS_JSON",
        json.dumps({
            "gpu": {
                "endpoint": "https://worker.example.invalid",
                "solvers": ["warpx", "picongpu"],
                "token_env": "SECRET_WORKER_TOKEN",
            }
        }),
    )
    rendered = json.dumps(physics_worker_status())
    assert "worker.example.invalid" not in rendered
    assert "SECRET_WORKER_TOKEN" not in rendered
    assert "warpx" in rendered


def test_worker_rejects_unlisted_solver(monkeypatch):
    monkeypatch.setenv(
        "SCIBRAIN_PHYSICS_WORKERS_JSON",
        json.dumps({
            "gpu": {
                "endpoint": "https://worker.example.invalid",
                "solvers": ["warpx"],
            }
        }),
    )
    with pytest.raises(ValueError):
        submit_physics_job("gpu", {"solver": "geant4"})


def test_high_level_physics_router_delegates_plasma_screening():
    result = route_physics_model({
        "domain": "plasma",
        "observable": "shock speed",
        "acceptance_criterion": "grid-converged shock speed within 5%",
        "ne": 1e18,
        "B": 0.02,
        "Te_ev": 20,
        "Ti_ev": 5,
        "L": 1e-4,
        "U": 1e5,
        "requires_electron_kinetics": True,
    })
    assert result["decision_state"] == "screened"
    assert result["next_skill"] == "simulation-orchestrator"
    assert "plasma-model-router" in result["required_skills"]
    assert result["plasma_screening"] is not None
    models = [item["model"] for item in result["plasma_screening"]["candidate_hierarchy"]]
    assert "WarpX full PIC" in models


def test_high_level_router_blocks_when_scientific_target_is_underspecified():
    result = route_physics_model({"domain": "plasma"})
    assert result["decision_state"] == "blocked"
    assert "target observable" in result["unresolved"]
    assert "acceptance criterion" in result["unresolved"]
    assert result["next_skill"] is None


def test_high_level_router_selects_transport_without_plasma_inputs():
    result = route_physics_model({
        "domain": "particle-transport",
        "observable": "absorbed dose",
        "acceptance_criterion": "dose uncertainty below 3%",
        "particle_through_matter": True,
    })
    assert result["decision_state"] == "screened"
    assert result["candidate_hierarchy"][0]["solver_or_skill"] == "geant4-particle-transport"
    assert result["plasma_screening"] is None


def test_high_level_router_rejects_surrogate_first_workflow():
    result = route_physics_model({
        "domain": "theory",
        "observable": "field amplitude",
        "acceptance_criterion": "relative error below 2%",
        "use_surrogate": True,
        "has_validated_baseline": False,
    })
    rejected = [item["family"] for item in result["rejected_or_deferred"]]
    assert "surrogate-first workflow" in rejected


def test_physics_validation_accepts_complete_explicit_evidence():
    result = validate_physics_observables({
        "observables": [{
            "name": "shock_speed",
            "required_checks": ["dimensions", "convergence", "benchmark"],
            "checks": {
                "dimensions": {"status": "pass", "evidence": "SI audit"},
                "convergence": {"status": "pass", "evidence": "three-grid study"},
                "benchmark": {"status": "pass", "evidence": "reference case"},
            },
            "claim_scope": "shock speed in the stated parameter range",
        }]
    })
    assert result["results"][0]["decision"] == "accepted"
    assert result["summary"]["accepted"] == 1
    assert result["global_validity_claim"] is False


def test_physics_validation_blocks_missing_required_evidence():
    result = validate_physics_observables({
        "observables": [{
            "name": "compression",
            "required_checks": ["dimensions", "convergence"],
            "checks": {
                "dimensions": {"status": "pass", "evidence": "SI audit"},
            },
        }]
    })
    assert result["results"][0]["decision"] == "blocked"
    assert result["results"][0]["missing_required_checks"] == ["convergence"]


def test_physics_validation_rejects_failed_required_check():
    result = validate_physics_observables({
        "observables": [{
            "name": "energy_balance",
            "required_checks": ["conservation"],
            "checks": {
                "conservation": {"status": "fail", "evidence": "drift exceeds project criterion"},
            },
        }]
    })
    assert result["results"][0]["decision"] == "rejected"


def test_physics_validation_rejects_unknown_status():
    with pytest.raises(ValueError):
        validate_physics_observables({
            "observables": [{
                "name": "shock_speed",
                "required_checks": ["benchmark"],
                "checks": {"benchmark": {"status": "looks_good"}},
            }]
        })
