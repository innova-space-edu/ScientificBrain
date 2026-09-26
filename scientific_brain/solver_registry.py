from __future__ import annotations

from typing import Any


DEFAULT_ARTIFACT_REPOSITORY = "scientificbrain-solvers"

SOLVER_RUNTIME_SPECS: dict[str, dict[str, Any]] = {
    "warpx": {
        "tag": "26.09-cuda12.8",
        "machine_type": "g2-standard-8",
        "gpu_type": "nvidia-l4",
        "max_gpus_per_node": 1,
        "install_gpu_drivers": True,
        "supports_multi_node": False,
        "runtime": "gpu",
        "actions": ["validate", "run"],
    },
    "picongpu": {
        "tag": "0.8.0-cuda12.4",
        "machine_type": "g2-standard-8",
        "gpu_type": "nvidia-l4",
        "max_gpus_per_node": 1,
        "install_gpu_drivers": True,
        "supports_multi_node": False,
        "runtime": "gpu",
        "actions": ["validate", "run"],
    },
    "edipic2d": {
        "tag": "a32863ad-petsc3.14.6",
        "machine_type": "c3-standard-8",
        "supports_multi_node": False,
        "runtime": "cpu-mpi",
        "actions": ["validate", "run"],
    },
    "geant4": {
        "tag": "11.4.2",
        "machine_type": "c3-standard-8",
        "supports_multi_node": False,
        "runtime": "cpu",
        "actions": ["validate", "run"],
    },
    "physicsnemo": {
        "tag": "26.08",
        "machine_type": "g2-standard-8",
        "gpu_type": "nvidia-l4",
        "max_gpus_per_node": 1,
        "install_gpu_drivers": True,
        "supports_multi_node": False,
        "runtime": "gpu",
        "actions": ["validate", "train", "infer", "analyze"],
    },
    "flash": {
        "tag": "4.8-private",
        "machine_type": "c3-standard-22",
        "supports_multi_node": False,
        "runtime": "cpu-mpi",
        "private_source": True,
        "actions": ["validate", "run"],
    },
}


def default_batch_profiles(
    project_id: str,
    *,
    region: str = "us-central1",
    repository: str = DEFAULT_ARTIFACT_REPOSITORY,
) -> dict[str, dict[str, Any]]:
    project_id = str(project_id or "").strip()
    region = str(region or "us-central1").strip() or "us-central1"
    repository = str(repository or DEFAULT_ARTIFACT_REPOSITORY).strip()
    if not project_id:
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    for solver, spec in SOLVER_RUNTIME_SPECS.items():
        profile: dict[str, Any] = {
            "image_uri": (
                f"{region}-docker.pkg.dev/{project_id}/{repository}/"
                f"{solver}:{spec['tag']}"
            ),
            "machine_type": spec["machine_type"],
            "max_retry_count": 1,
            "supports_multi_node": bool(spec.get("supports_multi_node", False)),
        }
        if spec.get("gpu_type"):
            profile.update(
                {
                    "gpu_type": spec["gpu_type"],
                    "max_gpus_per_node": spec["max_gpus_per_node"],
                    "install_gpu_drivers": bool(spec.get("install_gpu_drivers", True)),
                }
            )
        profiles[solver] = profile
    return profiles


def public_solver_runtime_registry() -> dict[str, Any]:
    solvers: dict[str, Any] = {}
    for name, spec in SOLVER_RUNTIME_SPECS.items():
        solvers[name] = {
            "tag": spec["tag"],
            "runtime": spec["runtime"],
            "actions": list(spec["actions"]),
            "gpu_required": bool(spec.get("gpu_type")),
            "supports_multi_node": bool(spec.get("supports_multi_node", False)),
            "private_source": bool(spec.get("private_source", False)),
        }
    return {
        "schema_version": "0.1",
        "solvers": solvers,
        "note": (
            "Image names and machine profiles are server-owned. Default profiles are "
            "single-node until a dedicated cross-VM MPI contract is validated."
        ),
    }
