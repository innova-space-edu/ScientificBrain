from __future__ import annotations

import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


SolverName = Literal["flash", "warpx", "picongpu", "edipic2d", "geant4", "physicsnemo"]
ActionName = Literal["validate", "run", "sweep", "train", "infer", "analyze"]

_FORBIDDEN_KEYS = {
    "command",
    "cmd",
    "shell",
    "executable",
    "endpoint",
    "url",
    "token",
    "api_key",
    "secret",
    "authorization",
}

_ACTIONS: dict[str, set[str]] = {
    "flash": {"validate", "run"},
    "warpx": {"validate", "run"},
    "picongpu": {"validate", "run"},
    "edipic2d": {"validate", "run"},
    "geant4": {"validate", "run"},
    "physicsnemo": {"validate", "train", "infer", "analyze"},
}

_FLASH_SETUP_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\/-]{0,159}$")
_GEANT4_PHYSICS_LISTS = {
    "FTFP_BERT",
    "FTFP_BERT_EMZ",
    "QGSP_BERT",
    "QGSP_BIC",
    "Shielding",
}


def physics_model_catalog() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "solvers": {
            "flash": {
                "label": "FLASH",
                "default_model": "hall-mhd",
                "actions": sorted(_ACTIONS["flash"]),
                "models": [
                    {"id": "hydro", "label": "Hydrodynamics", "description": "Baseline hydrodynamics without magnetic-field evolution."},
                    {"id": "ideal-mhd", "label": "Ideal MHD", "description": "Ideal magnetohydrodynamic baseline."},
                    {"id": "resistive-mhd", "label": "Resistive MHD", "description": "MHD with finite magnetic resistivity."},
                    {"id": "hall-mhd", "label": "Hall MHD", "description": "Extended fluid model including Hall physics."},
                    {"id": "extended-mhd", "label": "Extended MHD", "description": "Hall/transport extensions such as Biermann, Nernst, Seebeck and cross-field terms when enabled by the FLASH setup."},
                ],
            },
            "warpx": {
                "label": "WarpX",
                "default_model": "hybrid-pic",
                "actions": sorted(_ACTIONS["warpx"]),
                "models": [
                    {"id": "hybrid-pic", "label": "Hybrid-PIC", "description": "Kinetic ions with fluid electrons."},
                    {"id": "full-pic-em", "label": "Full PIC · electromagnetic", "description": "Kinetic particles with electromagnetic field evolution."},
                    {"id": "full-pic-es", "label": "Full PIC · electrostatic", "description": "Electrostatic PIC configuration when appropriate."},
                    {"id": "pic-mcc", "label": "PIC + MCC", "description": "PIC with Monte Carlo collisions against a background gas."},
                    {"id": "pic-dsmc", "label": "PIC + DSMC", "description": "PIC with direct-simulation Monte Carlo collision modeling."},
                ],
            },
            "picongpu": {
                "label": "PIConGPU",
                "default_model": "electromagnetic-pic",
                "actions": sorted(_ACTIONS["picongpu"]),
                "models": [
                    {"id": "electromagnetic-pic", "label": "Electromagnetic full PIC", "description": "GPU/HPC electromagnetic particle-in-cell simulation."},
                    {"id": "picmi-electromagnetic", "label": "PICMI electromagnetic", "description": "Electromagnetic setup generated through the PIConGPU PICMI interface."},
                    {"id": "ionization-pic", "label": "PIC + ionization", "description": "Full PIC configuration including supported ionization interactions."},
                ],
            },
            "edipic2d": {
                "label": "EDIPIC-2D",
                "default_model": "electrostatic-pic-2d",
                "actions": sorted(_ACTIONS["edipic2d"]),
                "models": [
                    {"id": "electrostatic-pic-2d", "label": "Electrostatic PIC 2D", "description": "Two-dimensional PIC model for low-temperature plasma applications."},
                    {"id": "low-temperature-discharge-2d", "label": "Low-temperature discharge 2D", "description": "EDIPIC-2D configuration for bounded/discharge plasma studies."},
                ],
            },
            "geant4": {
                "label": "Geant4",
                "default_model": "electromagnetic-transport",
                "actions": sorted(_ACTIONS["geant4"]),
                "models": [
                    {"id": "electromagnetic-transport", "label": "Electromagnetic transport", "description": "Particle transport using an electromagnetic physics-list configuration."},
                    {"id": "hadronic-transport", "label": "Hadronic transport", "description": "Particle transport using an appropriate hadronic physics list."},
                    {"id": "optical-photon-transport", "label": "Optical photon transport", "description": "Optical processes and photon transport."},
                    {"id": "custom-physics-list", "label": "Custom physics list", "description": "Explicit application-owned Geant4 physics-list configuration."},
                ],
            },
            "physicsnemo": {
                "label": "PhysicsNeMo",
                "default_model": "fno",
                "actions": sorted(_ACTIONS["physicsnemo"]),
                "models": [
                    {"id": "fno", "label": "FNO", "description": "Fourier Neural Operator surrogate."},
                    {"id": "pino", "label": "PINO", "description": "Physics-Informed Neural Operator."},
                    {"id": "meshgraphnet", "label": "MeshGraphNet", "description": "Graph neural network for mesh-based physical systems."},
                    {"id": "pinn", "label": "PINN", "description": "Physics-informed neural network."},
                    {"id": "transolver", "label": "Transolver", "description": "Transformer-style architecture for scientific fields."},
                    {"id": "diffusion-surrogate", "label": "Diffusion surrogate", "description": "Diffusion-model-based scientific surrogate."},
                ],
            },
        },
        "note": "Model entries are ScientificBrain execution presets. Solver-specific input artifacts still define the complete physical/numerical setup.",
    }


class ResourceRequest(BaseModel):
    nodes: int = Field(default=1, ge=1, le=256)
    cpus: int = Field(default=4, ge=1, le=4096)
    gpus: int = Field(default=0, ge=0, le=512)
    memory_gb: float = Field(default=8.0, gt=0, le=32768)
    wall_minutes: int = Field(default=60, ge=1, le=10080)
    mpi_ranks: int | None = Field(default=None, ge=1, le=8192)

    @model_validator(mode="after")
    def validate_layout(self):
        if self.mpi_ranks is not None and self.mpi_ranks < self.nodes:
            raise ValueError("mpi_ranks cannot be smaller than nodes")
        return self


class PhysicsJob(BaseModel):
    schema_version: str = "0.1"
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    solver: SolverName
    action: ActionName
    model: str = Field(min_length=1, max_length=160)
    input_artifact: str = Field(min_length=1, max_length=500)
    parameters: dict[str, Any] = Field(default_factory=dict)
    resources: ResourceRequest = Field(default_factory=ResourceRequest)
    outputs: list[str] = Field(default_factory=list, max_length=50)
    validation: list[str] = Field(default_factory=list, max_length=50)
    random_seed: int | None = None
    source_version: str | None = Field(default=None, max_length=160)
    skill: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input_artifact")
    @classmethod
    def artifact_not_a_url(cls, value: str) -> str:
        if "://" in value:
            raise ValueError("input_artifact must be an artifact/path identifier, not a URL")
        if value.startswith("/") or value.startswith("~"):
            raise ValueError("input_artifact must be worker-relative or artifact-store relative")
        return value

    @field_validator("outputs", "validation")
    @classmethod
    def clean_string_list(cls, values: list[str]) -> list[str]:
        result = []
        for value in values:
            item = str(value).strip()
            if not item:
                continue
            if len(item) > 240:
                raise ValueError("output/validation entries must be <= 240 characters")
            result.append(item)
        return result

    @model_validator(mode="after")
    def validate_job(self):
        if self.action not in _ACTIONS[self.solver]:
            raise ValueError(f"action {self.action} is not allowed for solver {self.solver}")
        _assert_safe_mapping(self.parameters, "parameters")
        _assert_safe_mapping(self.metadata, "metadata")
        if self.solver == "flash" and self.action == "run":
            setup = str(self.parameters.get("flash_setup") or "").strip()
            if not setup:
                raise ValueError("FLASH run requires parameters.flash_setup")
            if not _FLASH_SETUP_RE.fullmatch(setup) or any(part == ".." for part in setup.split("/")):
                raise ValueError("parameters.flash_setup must be a relative FLASH setup name")
        if (
            self.solver == "physicsnemo"
            and self.action in {"train", "infer", "analyze"}
            and self.model != "fno"
        ):
            raise ValueError(
                "The executable PhysicsNeMo adapter currently supports model=fno "
                "for train/infer/analyze"
            )
        if self.solver == "geant4" and self.action == "run" and self.model == "custom-physics-list":
            physics_list = str(self.parameters.get("physics_list") or "").strip()
            if physics_list not in _GEANT4_PHYSICS_LISTS:
                raise ValueError(
                    "custom-physics-list requires parameters.physics_list from "
                    "the ScientificBrain allowlist"
                )
        return self


def _assert_safe_mapping(value: dict[str, Any], label: str) -> None:
    if len(value) > 100:
        raise ValueError(f"{label} contains too many keys")
    for key, item in value.items():
        normalized = re.sub(r"[^a-z0-9_]", "", str(key).lower())
        if normalized in _FORBIDDEN_KEYS:
            raise ValueError(f"{label}.{key} is controlled by the worker/server and is not accepted")
        if isinstance(item, dict):
            _assert_safe_mapping(item, f"{label}.{key}")
        elif isinstance(item, list) and len(item) > 10000:
            raise ValueError(f"{label}.{key} list is too large for a job request")


def physics_execution_profiles() -> dict[str, Any]:
    model_catalog = physics_model_catalog()["solvers"]
    return {
        "schema_version": "0.1",
        "profiles": {
            "flash": {
                "models": model_catalog["flash"]["models"],
                "default_model": model_catalog["flash"]["default_model"],
                "role": "fluid plasma / MHD / Extended-MHD",
                "input_contract": "FLASH object/run configuration or parameter artifact",
                "native_outputs": ["FLASH HDF5 plotfiles", "checkpoints", "log"],
                "canonical_adapter": "yt -> ScientificBrain canonical plasma data",
                "recommended_validation": ["benchmark", "resolution convergence", "div(B)", "observable convergence"],
            },
            "warpx": {
                "models": model_catalog["warpx"]["models"],
                "default_model": model_catalog["warpx"]["default_model"],
                "role": "Hybrid-PIC / full PIC / MCC / DSMC",
                "input_contract": "WarpX input deck or approved PICMI artifact",
                "native_outputs": ["plot/openPMD diagnostics", "checkpoints", "run metadata"],
                "canonical_adapter": "openPMD",
                "recommended_validation": ["charge conservation", "energy balance", "mesh/time/particle convergence"],
            },
            "picongpu": {
                "models": model_catalog["picongpu"]["models"],
                "default_model": model_catalog["picongpu"]["default_model"],
                "role": "GPU/HPC full kinetic PIC",
                "input_contract": "approved PIConGPU parameter/template artifact",
                "native_outputs": ["openPMD", "plugins", "checkpoints"],
                "canonical_adapter": "openPMD",
                "recommended_validation": ["charge conservation", "energy diagnostics", "particle convergence", "scaling separation"],
            },
            "edipic2d": {
                "models": model_catalog["edipic2d"]["models"],
                "default_model": model_catalog["edipic2d"]["default_model"],
                "role": "2D low-temperature plasma PIC",
                "input_contract": "complete EDIPIC-2D input directory artifact",
                "native_outputs": ["EDIPIC diagnostic/output files"],
                "canonical_adapter": "EDIPIC-2D explicit adapter",
                "recommended_validation": ["particle noise", "field convergence", "current/energy balance"],
            },
            "geant4": {
                "models": model_catalog["geant4"]["models"],
                "default_model": model_catalog["geant4"]["default_model"],
                "role": "Monte Carlo particle transport through matter",
                "input_contract": "built application + macro/geometry/material artifact",
                "native_outputs": ["scoring/statistical outputs"],
                "canonical_adapter": "Geant4 scoring adapter",
                "recommended_validation": ["physics-list justification", "sample convergence", "benchmark/data comparison"],
            },
            "physicsnemo": {
                "models": model_catalog["physicsnemo"]["models"],
                "default_model": model_catalog["physicsnemo"]["default_model"],
                "role": "scientific ML / surrogate / PINO / active learning",
                "input_contract": "versioned dataset + training/inference config artifact",
                "native_outputs": ["checkpoints", "metrics", "predictions"],
                "canonical_adapter": "ScientificBrain dataset contract",
                "recommended_validation": ["held-out solver runs", "physics residuals", "rollout error", "domain-of-validity"],
            },
        },
        "security": "Executable paths, endpoints, scheduler templates and credentials are resolved only by the worker/server.",
    }


def prepare_physics_job(payload: dict[str, Any]) -> dict[str, Any]:
    job = PhysicsJob.model_validate(payload)
    profile = physics_execution_profiles()["profiles"][job.solver]
    data = job.model_dump(mode="json")
    data["execution_profile"] = profile
    data["dispatch_state"] = "prepared"
    data["execution_state"] = "prepared"
    required_checks = list(job.validation) or list(profile["recommended_validation"])
    data["validation"] = required_checks
    data["scientific_validation"] = {
        "state": "not_evaluated",
        "required_checks": required_checks,
        "note": "Preparing or finishing a solver job does not by itself validate the scientific result.",
    }
    data["reproducibility"] = {
        "source_version": job.source_version,
        "input_artifact": job.input_artifact,
        "random_seed": job.random_seed,
        "solver": job.solver,
        "model": job.model,
    }
    data["dispatch_note"] = (
        "Prepared only. ScientificBrain must submit this manifest to a server-configured "
        "worker; the client cannot supply commands, endpoints or credentials."
    )
    return data
