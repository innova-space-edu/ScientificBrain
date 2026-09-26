from __future__ import annotations

import base64
import json
import math
import os
import re
from dataclasses import dataclass
from urllib.parse import quote
from typing import Any

import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
import httpx

from .physics_jobs import PhysicsJob
from .google_wif import vercel_wif_from_env
from .solver_registry import DEFAULT_ARTIFACT_REPOSITORY, default_batch_profiles


BATCH_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
BATCH_API_ROOT = "https://batch.googleapis.com/v1"
STORAGE_API_ROOT = "https://storage.googleapis.com/storage/v1"
_JOB_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_SCIENTIFIC_JOB_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _json_env(name: str) -> dict[str, Any]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{name} must be a JSON object")
    return data


def normalize_google_batch_state(status: dict[str, Any] | None) -> dict[str, Any]:
    raw_state = str((status or {}).get("state") or "STATE_UNSPECIFIED").upper()
    mapping = {
        "STATE_UNSPECIFIED": ("unknown", False, False),
        "QUEUED": ("queued", False, False),
        "SCHEDULED": ("preparing", False, False),
        "RUNNING": ("running", False, False),
        "SUCCEEDED": ("finished", True, True),
        "FAILED": ("failed", True, False),
        "DELETION_IN_PROGRESS": ("canceling", False, False),
    }
    execution_state, terminal, success = mapping.get(raw_state, ("unknown", False, False))
    return {
        "batch_state": raw_state,
        "execution_state": execution_state,
        "terminal": terminal,
        "success": success,
        "progress_source": "google_batch_state",
    }


@dataclass(frozen=True)
class GoogleBatchProfile:
    name: str
    image_uri: str
    machine_type: str
    gpu_type: str | None = None
    install_gpu_drivers: bool = False
    max_gpus_per_node: int | None = None
    block_external_network: bool = False
    supports_multi_node: bool = False
    max_retry_count: int = 1
    spot: bool = False

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "GoogleBatchProfile":
        image_uri = str(data.get("image_uri") or "").strip()
        machine_type = str(data.get("machine_type") or "").strip()
        if not image_uri or not machine_type:
            raise ValueError(f"Google Batch profile {name} requires image_uri and machine_type")
        max_gpus = data.get("max_gpus_per_node")
        return cls(
            name=name,
            image_uri=image_uri,
            machine_type=machine_type,
            gpu_type=str(data.get("gpu_type") or "").strip() or None,
            install_gpu_drivers=bool(data.get("install_gpu_drivers", bool(data.get("gpu_type")))),
            max_gpus_per_node=int(max_gpus) if max_gpus not in (None, "") else None,
            block_external_network=bool(data.get("block_external_network", False)),
            supports_multi_node=bool(data.get("supports_multi_node", False)),
            max_retry_count=max(0, min(10, int(data.get("max_retry_count", 1)))),
            spot=bool(data.get("spot", False)),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "machine_type": self.machine_type,
            "gpu_type": self.gpu_type,
            "max_gpus_per_node": self.max_gpus_per_node,
            "supports_multi_node": self.supports_multi_node,
            "spot": self.spot,
        }


@dataclass
class GoogleCloudBatch:
    project_id: str
    region: str
    artifact_bucket: str
    job_service_account: str | None
    profiles: dict[str, GoogleBatchProfile]
    enabled: bool = False
    timeout: float = 30.0
    vercel_oidc_token: str = ""
    vercel_oidc_token_source: str | None = None
    profile_source: str = "environment"

    @classmethod
    def from_env(
        cls,
        *,
        vercel_oidc_token: str | None = None,
        vercel_oidc_token_source: str | None = None,
    ) -> "GoogleCloudBatch":
        project_id = os.getenv("SCIBRAIN_GCP_PROJECT_ID", "").strip()
        region = os.getenv("SCIBRAIN_GCP_REGION", "us-central1").strip() or "us-central1"
        repository = (
            os.getenv("SCIBRAIN_GCP_ARTIFACT_REPOSITORY", DEFAULT_ARTIFACT_REPOSITORY).strip()
            or DEFAULT_ARTIFACT_REPOSITORY
        )
        raw_profiles = _json_env("SCIBRAIN_GCP_BATCH_PROFILES_JSON")
        profile_source = "environment"
        if (
            not raw_profiles
            and project_id
            and _truthy("SCIBRAIN_GCP_BATCH_AUTOCONFIGURE", True)
        ):
            raw_profiles = default_batch_profiles(
                project_id,
                region=region,
                repository=repository,
            )
            profile_source = "solver_registry"
        profiles = {
            str(name): GoogleBatchProfile.from_dict(str(name), spec)
            for name, spec in raw_profiles.items()
            if isinstance(spec, dict)
        }
        return cls(
            project_id=project_id,
            region=region,
            artifact_bucket=os.getenv("SCIBRAIN_GCP_ARTIFACT_BUCKET", "").strip(),
            job_service_account=os.getenv("SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT", "").strip() or None,
            profiles=profiles,
            enabled=_truthy("SCIBRAIN_GCP_BATCH_ENABLED", False),
            timeout=max(5.0, float(os.getenv("SCIBRAIN_GCP_BATCH_TIMEOUT_SECONDS", "30"))),
            vercel_oidc_token=str(vercel_oidc_token or "").strip(),
            vercel_oidc_token_source=vercel_oidc_token_source,
            profile_source=profile_source,
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled
            and self.project_id
            and self.region
            and self.artifact_bucket
            and self.profiles
        )

    def _wif(self):
        return vercel_wif_from_env(
            subject_token=self.vercel_oidc_token or None,
            subject_token_source=self.vercel_oidc_token_source,
        )

    def auth_mode(self) -> str:
        wif = self._wif()
        on_vercel = os.getenv("VERCEL", "").strip() == "1"
        if wif.available:
            return "vercel_oidc_wif"
        if wif.configured:
            return "vercel_oidc_wif_missing_token"
        if on_vercel:
            return "vercel_oidc_wif_not_configured"
        if os.getenv("SCIBRAIN_GCP_SERVICE_ACCOUNT_JSON", "").strip():
            return "service_account_json"
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip():
            return "adc_credentials_file"
        return "application_default_credentials"

    def status(self) -> dict[str, Any]:
        return {
            "provider": "google_cloud_batch",
            "enabled": self.enabled,
            "configured": self.configured,
            "project_configured": bool(self.project_id),
            "region": self.region,
            "artifact_bucket_configured": bool(self.artifact_bucket),
            "job_service_account_configured": bool(self.job_service_account),
            "auth_mode": self.auth_mode(),
            "workload_identity": self._wif().public_status(),
            "profiles": [profile.public_dict() for profile in self.profiles.values()],
            "profile_source": self.profile_source,
            "notes": [
                "Profile configuration does not prove that the referenced Artifact Registry image exists.",
                "Google Cloud Batch provisions Compute Engine resources for submitted jobs.",
                "GPU jobs require a server-configured compatible machine/GPU profile.",
                "Credentials, container images and service accounts are server-owned.",
            ],
        }

    def _credentials(self):
        wif = self._wif()
        on_vercel = os.getenv("VERCEL", "").strip() == "1"
        if wif.available:
            return wif.credentials()
        if wif.configured and on_vercel:
            raise RuntimeError(
                "Google WIF is configured but VERCEL_OIDC_TOKEN / x-vercel-oidc-token is unavailable. "
                "Enable Secure Backend Access with OIDC Federation and ensure the function request "
                "contains x-vercel-oidc-token, then redeploy production."
            )
        if on_vercel and not wif.configured:
            missing = ", ".join(wif.missing_configuration())
            raise RuntimeError(
                "Google WIF is not configured in the Vercel runtime. Missing: "
                f"{missing}. Add the SCIBRAIN_GCP_WIF_* variables to Production and redeploy."
            )

        raw = os.getenv("SCIBRAIN_GCP_SERVICE_ACCOUNT_JSON", "").strip()
        if raw:
            info = json.loads(raw)
            if not isinstance(info, dict):
                raise ValueError("SCIBRAIN_GCP_SERVICE_ACCOUNT_JSON must be a JSON object")
            credentials = service_account.Credentials.from_service_account_info(
                info, scopes=[BATCH_SCOPE]
            )
        else:
            credentials, _ = google.auth.default(scopes=[BATCH_SCOPE])
        if not credentials.valid:
            credentials.refresh(GoogleAuthRequest())
        return credentials

    def _profile_for(self, solver: str) -> GoogleBatchProfile:
        profile = self.profiles.get(solver)
        if profile is None:
            raise ValueError(f"No Google Batch execution profile configured for solver {solver}")
        return profile

    def _uris(self, job: PhysicsJob) -> tuple[str, str]:
        if not self.artifact_bucket:
            raise ValueError("SCIBRAIN_GCP_ARTIFACT_BUCKET is not configured")
        bucket = self.artifact_bucket.removeprefix("gs://").rstrip("/")
        input_uri = f"gs://{bucket}/{job.input_artifact.lstrip('/')}"
        output_uri = f"gs://{bucket}/scientificbrain/jobs/{job.job_id}/"
        return input_uri, output_uri

    @staticmethod
    def _batch_job_id(job: PhysicsJob) -> str:
        raw = f"scibrain-{job.solver}-{job.job_id[:12]}".lower()
        value = re.sub(r"[^a-z0-9-]", "-", raw).strip("-")
        if not value or not value[0].isalpha():
            value = "scibrain-" + value
        return value[:63].rstrip("-")

    def build_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        job = PhysicsJob.model_validate(payload)
        profile = self._profile_for(job.solver)
        input_uri, output_uri = self._uris(job)

        nodes = job.resources.nodes
        if nodes < 1:
            raise ValueError("nodes must be >= 1")
        if nodes > 1 and not profile.supports_multi_node:
            raise ValueError(
                f"Google Batch profile {profile.name} is single-node; "
                "use a dedicated validated cross-VM MPI profile"
            )
        if profile.gpu_type and job.resources.gpus < 1:
            raise ValueError(f"Google Batch profile {profile.name} requires at least one GPU")
        if job.resources.gpus and not profile.gpu_type:
            raise ValueError(f"Google Batch profile {profile.name} has no gpu_type")
        if job.resources.gpus % nodes != 0:
            raise ValueError("gpus must be divisible by nodes for Google Batch")
        gpus_per_node = job.resources.gpus // nodes
        if profile.max_gpus_per_node is not None and gpus_per_node > profile.max_gpus_per_node:
            raise ValueError(
                f"Requested {gpus_per_node} GPUs/node exceeds profile limit "
                f"{profile.max_gpus_per_node}"
            )

        cpus_per_node = max(1, math.ceil(job.resources.cpus / nodes))
        memory_mib_per_node = max(16, math.ceil(job.resources.memory_gb * 1024 / nodes))

        encoded = base64.b64encode(
            json.dumps(job.model_dump(mode="json"), separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
        environment = {
            "SCIBRAIN_JOB_JSON_B64": encoded,
            "SCIBRAIN_INPUT_URI": input_uri,
            "SCIBRAIN_OUTPUT_URI": output_uri,
            "SCIBRAIN_SOLVER": job.solver,
            "SCIBRAIN_ACTION": job.action,
            "SCIBRAIN_MODEL": job.model,
            "SCIBRAIN_JOB_ID": job.job_id,
            "SCIBRAIN_MPI_RANKS": str(job.resources.mpi_ranks or nodes),
        }

        container: dict[str, Any] = {"imageUri": profile.image_uri}
        if profile.block_external_network:
            container["blockExternalNetwork"] = True

        task_spec: dict[str, Any] = {
            "runnables": [{"container": container}],
            "environment": {"variables": environment},
            "computeResource": {
                "cpuMilli": cpus_per_node * 1000,
                "memoryMib": memory_mib_per_node,
            },
            "maxRetryCount": profile.max_retry_count,
            "maxRunDuration": f"{job.resources.wall_minutes * 60}s",
        }

        task_group: dict[str, Any] = {
            "taskSpec": task_spec,
            "taskCount": nodes,
            "parallelism": nodes,
        }
        if nodes > 1:
            task_group.update({
                "taskCountPerNode": 1,
                "requireHostsFile": True,
                "permissiveSsh": True,
            })

        policy: dict[str, Any] = {"machineType": profile.machine_type}
        if gpus_per_node:
            policy["accelerators"] = [{
                "type": profile.gpu_type,
                "count": gpus_per_node,
            }]
        if profile.spot:
            policy["provisioningModel"] = "SPOT"

        instance: dict[str, Any] = {"policy": policy}
        if gpus_per_node:
            instance["installGpuDrivers"] = profile.install_gpu_drivers

        allocation: dict[str, Any] = {"instances": [instance]}
        if self.job_service_account:
            allocation["serviceAccount"] = {"email": self.job_service_account}

        result = {
            "batch_job_id": self._batch_job_id(job),
            "parent": f"projects/{self.project_id}/locations/{self.region}",
            "job": {
                "taskGroups": [task_group],
                "allocationPolicy": allocation,
                "logsPolicy": {"destination": "CLOUD_LOGGING"},
                "labels": {
                    "app": "scientificbrain",
                    "solver": job.solver,
                    "action": job.action,
                },
            },
            "scientificbrain": {
                "job_id": job.job_id,
                "input_uri": input_uri,
                "output_uri": output_uri,
                "solver": job.solver,
                "profile": profile.public_dict(),
                "multi_node": nodes > 1,
            },
        }
        return result

    def _headers(self) -> dict[str, str]:
        credentials = self._credentials()
        return {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
        }

    def auth_probe(self) -> dict[str, Any]:
        try:
            credentials = self._credentials()
            return {
                "provider": "google_cloud",
                "authenticated": bool(getattr(credentials, "token", "")),
                "auth_mode": self.auth_mode(),
                "workload_identity": self._wif().public_status(),
            }
        except Exception as exc:
            return {
                "provider": "google_cloud",
                "authenticated": False,
                "auth_mode": self.auth_mode(),
                "workload_identity": self._wif().public_status(),
                "error": type(exc).__name__,
                "detail": str(exc),
            }

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("Google Cloud Batch is not fully configured")
        built = self.build_job(payload)
        url = f"{BATCH_API_ROOT}/{built['parent']}/jobs"
        response = httpx.post(
            url,
            params={"job_id": built["batch_job_id"]},
            headers=self._headers(),
            json=built["job"],
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        lifecycle = normalize_google_batch_state(result.get("status"))
        return {
            "provider": "google_cloud_batch",
            "submitted": True,
            "batch_job_id": built["batch_job_id"],
            "name": result.get("name"),
            "uid": result.get("uid"),
            "status": result.get("status"),
            **lifecycle,
            "scientificbrain": built["scientificbrain"],
        }

    def get(self, job_id: str) -> dict[str, Any]:
        if not self.project_id:
            raise RuntimeError("SCIBRAIN_GCP_PROJECT_ID is not configured")
        if not _JOB_ID_RE.fullmatch(job_id):
            raise ValueError("Invalid Google Batch job_id")
        url = (
            f"{BATCH_API_ROOT}/projects/{self.project_id}/locations/"
            f"{self.region}/jobs/{job_id}"
        )
        response = httpx.get(url, headers=self._headers(), timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        status = result.get("status") or {}
        lifecycle = normalize_google_batch_state(status)
        return {
            "provider": "google_cloud_batch",
            "job_id": job_id,
            "name": result.get("name"),
            "uid": result.get("uid"),
            "status": status,
            **lifecycle,
            "status_events": status.get("statusEvents") or [],
            "create_time": result.get("createTime"),
            "update_time": result.get("updateTime"),
            "task_groups": result.get("taskGroups"),
        }

    def delete(self, job_id: str) -> dict[str, Any]:
        if not self.project_id:
            raise RuntimeError("SCIBRAIN_GCP_PROJECT_ID is not configured")
        if not _JOB_ID_RE.fullmatch(job_id):
            raise ValueError("Invalid Google Batch job_id")
        url = (
            f"{BATCH_API_ROOT}/projects/{self.project_id}/locations/"
            f"{self.region}/jobs/{job_id}"
        )
        response = httpx.delete(url, headers=self._headers(), timeout=self.timeout)
        response.raise_for_status()
        return {"provider": "google_cloud_batch", "job_id": job_id, "delete_requested": True}

    def _scientific_output_prefix(self, scientific_job_id: str) -> tuple[str, str]:
        if not self.artifact_bucket:
            raise RuntimeError("SCIBRAIN_GCP_ARTIFACT_BUCKET is not configured")
        if not _SCIENTIFIC_JOB_ID_RE.fullmatch(scientific_job_id):
            raise ValueError("Invalid ScientificBrain job_id")
        bucket = self.artifact_bucket.removeprefix("gs://").rstrip("/")
        prefix = f"scientificbrain/jobs/{scientific_job_id}/"
        return bucket, prefix

    def list_outputs(self, scientific_job_id: str) -> dict[str, Any]:
        bucket, prefix = self._scientific_output_prefix(scientific_job_id)
        url = f"{STORAGE_API_ROOT}/b/{quote(bucket, safe='')}/o"
        response = httpx.get(
            url,
            params={"prefix": prefix},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        items = []
        for item in payload.get("items") or []:
            name = str(item.get("name") or "")
            if not name.startswith(prefix):
                continue
            items.append({
                "name": name,
                "relative_name": name[len(prefix):],
                "size": item.get("size"),
                "content_type": item.get("contentType"),
                "updated": item.get("updated"),
                "generation": item.get("generation"),
            })
        return {
            "provider": "google_cloud_storage",
            "scientific_job_id": scientific_job_id,
            "prefix": f"gs://{bucket}/{prefix}",
            "count": len(items),
            "items": items,
        }

    def output_manifest(self, scientific_job_id: str) -> dict[str, Any]:
        bucket, prefix = self._scientific_output_prefix(scientific_job_id)
        object_name = prefix + "scientificbrain-output.json"
        url = (
            f"{STORAGE_API_ROOT}/b/{quote(bucket, safe='')}/o/"
            f"{quote(object_name, safe='')}"
        )
        response = httpx.get(
            url,
            params={"alt": "media"},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("scientificbrain-output.json must contain a JSON object")
        return {
            "provider": "google_cloud_storage",
            "scientific_job_id": scientific_job_id,
            "object": f"gs://{bucket}/{object_name}",
            "manifest": payload,
        }


def google_batch_from_env(
    *,
    vercel_oidc_token: str | None = None,
    vercel_oidc_token_source: str | None = None,
) -> GoogleCloudBatch:
    return GoogleCloudBatch.from_env(
        vercel_oidc_token=vercel_oidc_token,
        vercel_oidc_token_source=vercel_oidc_token_source,
    )
