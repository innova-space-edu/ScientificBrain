import json
from pathlib import Path
import py_compile

import pytest
from pydantic import ValidationError

from scientific_brain.google_batch import GoogleCloudBatch
from scientific_brain.physics_jobs import prepare_physics_job
from scientific_brain.solver_registry import (
    SOLVER_RUNTIME_SPECS,
    default_batch_profiles,
)


ROOT = Path(__file__).resolve().parents[1]
SOLVERS = ROOT / "infra" / "gcp" / "solvers"


def test_runtime_registry_covers_all_six_solvers_and_fails_closed_on_multinode():
    assert set(SOLVER_RUNTIME_SPECS) == {
        "flash", "warpx", "picongpu", "edipic2d", "geant4", "physicsnemo"
    }
    assert all(spec["supports_multi_node"] is False for spec in SOLVER_RUNTIME_SPECS.values())


def test_default_profiles_are_generated_from_one_registry():
    profiles = default_batch_profiles(
        "scientificbrain-compute",
        region="us-central1",
        repository="scientificbrain-solvers",
    )
    assert profiles["flash"]["image_uri"].endswith("/flash:4.8-private")
    assert profiles["physicsnemo"]["image_uri"].endswith("/physicsnemo:26.08")
    assert profiles["warpx"]["gpu_type"] == "nvidia-l4"
    assert profiles["geant4"]["supports_multi_node"] is False


def _base_env(monkeypatch):
    monkeypatch.setenv("SCIBRAIN_GCP_PROJECT_ID", "science-project")
    monkeypatch.setenv("SCIBRAIN_GCP_REGION", "us-central1")
    monkeypatch.setenv("SCIBRAIN_GCP_ARTIFACT_BUCKET", "science-artifacts")
    monkeypatch.setenv("SCIBRAIN_GCP_BATCH_ENABLED", "true")
    monkeypatch.delenv("SCIBRAIN_GCP_BATCH_PROFILES_JSON", raising=False)


def test_google_batch_autoconfigures_profiles_from_registry(monkeypatch):
    _base_env(monkeypatch)
    provider = GoogleCloudBatch.from_env()
    assert provider.profile_source == "solver_registry"
    assert set(provider.profiles) == set(SOLVER_RUNTIME_SPECS)
    assert provider.profiles["physicsnemo"].image_uri.endswith("/physicsnemo:26.08")


def test_default_batch_profile_rejects_multinode(monkeypatch):
    _base_env(monkeypatch)
    job = {
        "solver": "warpx",
        "action": "run",
        "model": "full-pic-em",
        "input_artifact": "inputs/warpx",
        "resources": {
            "nodes": 2,
            "cpus": 16,
            "gpus": 2,
            "memory_gb": 64,
            "wall_minutes": 60,
        },
    }
    with pytest.raises(ValueError, match="single-node"):
        GoogleCloudBatch.from_env().build_job(job)


def test_gpu_profile_requires_gpu(monkeypatch):
    _base_env(monkeypatch)
    job = {
        "solver": "physicsnemo",
        "action": "train",
        "model": "fno",
        "input_artifact": "datasets/fno",
        "resources": {
            "nodes": 1,
            "cpus": 8,
            "gpus": 0,
            "memory_gb": 32,
            "wall_minutes": 60,
        },
    }
    with pytest.raises(ValueError, match="requires at least one GPU"):
        GoogleCloudBatch.from_env().build_job(job)


def test_physicsnemo_execution_fails_closed_for_unimplemented_model():
    with pytest.raises(ValidationError, match="model=fno"):
        prepare_physics_job({
            "solver": "physicsnemo",
            "action": "train",
            "model": "meshgraphnet",
            "input_artifact": "datasets/mgn",
        })


def test_geant4_custom_physics_list_is_allowlisted():
    with pytest.raises(ValidationError, match="allowlist"):
        prepare_physics_job({
            "solver": "geant4",
            "action": "run",
            "model": "custom-physics-list",
            "input_artifact": "geant4/run",
            "parameters": {"physics_list": "TotallyCustom"},
        })
    prepared = prepare_physics_job({
        "solver": "geant4",
        "action": "run",
        "model": "custom-physics-list",
        "input_artifact": "geant4/run",
        "parameters": {"physics_list": "FTFP_BERT_EMZ"},
    })
    assert prepared["dispatch_state"] == "prepared"


def test_runner_has_failure_manifest_and_no_user_shell_execution():
    text = (SOLVERS / "common" / "scibrain_runner.py").read_text()
    assert "execution-error.txt" in text
    assert 'state="failed"' in text
    assert "BATCH_TASK_COUNT" in text
    assert "/control/shell" in text
    assert "shell=True" not in text


def test_physicsnemo_adapter_is_safe_and_compiles():
    path = SOLVERS / "physicsnemo" / "scibrain_physicsnemo.py"
    py_compile.compile(str(path), doraise=True)
    text = path.read_text()
    assert "FNO(" in text
    assert "allow_pickle=False" in text
    assert "subprocess" not in text


def test_static_batch_template_matches_runtime_registry():
    template = json.loads(
        (ROOT / "infra" / "gcp" / "batch-profiles.template.json").read_text()
    )
    profiles = default_batch_profiles("PROJECT_ID", region="REGION")
    assert set(template) == set(profiles)
    for solver in template:
        assert template[solver]["image_uri"] == profiles[solver]["image_uri"]


def test_warpx_image_keeps_rz_linear_algebra_dependencies():
    text = (SOLVERS / "warpx" / "Dockerfile").read_text()
    assert "libblaspp-dev" in text
    assert "liblapackpp-dev" in text
    assert '-DWarpX_DIMS="1;2;3;RZ"' in text


def test_picongpu_image_matches_cuda_openmpi_runtime_contract():
    text = (SOLVERS / "picongpu" / "Dockerfile").read_text()
    assert "CUDA_IMAGE=nvidia/cuda:12.4.1-devel-ubuntu22.04" in text
    assert "OMPI_MCA_mpi_leave_pinned=0" in text
    assert "libboost-program-options-dev" in text
    assert "libboost-atomic-dev" in text
    assert "zlib1g-dev" in text
    assert 'pic-build -j "$(nproc)" -b "cuda:${CUDA_ARCH}"' in text


def test_flash_private_archive_uses_root_setup_script():
    text = (SOLVERS / "flash-private" / "Dockerfile").read_text()
    assert "chmod 0555 /opt/flash/setup" in text
    assert "test -f /opt/flash/setup" in text
    assert "'./setup \"$setup_name\" -auto \"$@\"'" in text
    assert "/opt/flash/bin/setup" not in text


def test_physicsnemo_image_does_not_require_cuda_driver_during_build():
    text = (SOLVERS / "physicsnemo" / "Dockerfile").read_text()
    assert "importlib.metadata" in text
    assert "import physicsnemo" not in text
    assert "from physicsnemo" not in text
    assert "py_compile" in text


def test_edipic_fortran_build_is_serial():
    text = (SOLVERS / "edipic2d" / "Dockerfile").read_text()
    assert "cd src && make &&" in text
    assert 'cd src && make -j' not in text
