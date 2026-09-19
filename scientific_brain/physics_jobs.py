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
    "flash": {"validate", "run", "sweep", "analyze"},
    "warpx": {"validate", "run", "sweep", "analyze"},
    "picongpu": {"validate", "run", "sweep", "analyze"},
    "edipic2d": {"validate", "run", "sweep", "analyze"},
    "geant4": {"validate", "run", "sweep", "analyze"},
    "physicsnemo": {"validate", "train", "infer", "analyze"},
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
    return {
        "schema_version": "0.1",
        "profiles": {
            "flash": {
                "role": "fluid plasma / MHD / Extended-MHD",
                "input_contract": "FLASH object/run configuration or parameter artifact",
                "native_outputs": ["FLASH HDF5 plotfiles", "checkpoints", "log"],
                "canonical_adapter": "yt -> ScientificBrain canonical plasma data",
                "recommended_validation": ["benchmark", "resolution convergence", "div(B)", "observable convergence"],
            },
            "warpx": {
                "role": "Hybrid-PIC / full PIC / MCC / DSMC",
                "input_contract": "WarpX input deck or approved PICMI artifact",
                "native_outputs": ["plot/openPMD diagnostics", "checkpoints", "run metadata"],
                "canonical_adapter": "openPMD",
                "recommended_validation": ["charge conservation", "energy balance", "mesh/time/particle convergence"],
            },
            "picongpu": {
                "role": "GPU/HPC full kinetic PIC",
                "input_contract": "approved PIConGPU parameter/template artifact",
                "native_outputs": ["openPMD", "plugins", "checkpoints"],
                "canonical_adapter": "openPMD",
                "recommended_validation": ["charge conservation", "energy diagnostics", "particle convergence", "scaling separation"],
            },
            "edipic2d": {
                "role": "2D low-temperature plasma PIC",
                "input_contract": "complete EDIPIC-2D input directory artifact",
                "native_outputs": ["EDIPIC diagnostic/output files"],
                "canonical_adapter": "EDIPIC-2D explicit adapter",
                "recommended_validation": ["particle noise", "field convergence", "current/energy balance"],
            },
            "geant4": {
                "role": "Monte Carlo particle transport through matter",
                "input_contract": "built application + macro/geometry/material artifact",
                "native_outputs": ["scoring/statistical outputs"],
                "canonical_adapter": "Geant4 scoring adapter",
                "recommended_validation": ["physics-list justification", "sample convergence", "benchmark/data comparison"],
            },
            "physicsnemo": {
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
    data["dispatch_note"] = (
        "Prepared only. ScientificBrain must submit this manifest to a server-configured "
        "worker; the client cannot supply commands, endpoints or credentials."
    )
    return data
