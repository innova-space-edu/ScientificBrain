from __future__ import annotations

import json
import os
from typing import Any

from .google_wif import vercel_wif_from_env


def google_cloud_setup_plan() -> dict[str, Any]:
    project_id = os.getenv("SCIBRAIN_GCP_PROJECT_ID", "").strip()
    region = os.getenv("SCIBRAIN_GCP_REGION", "us-central1").strip() or "us-central1"
    bucket = os.getenv("SCIBRAIN_GCP_ARTIFACT_BUCKET", "").strip()
    service_account = os.getenv("SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT", "").strip()
    raw_profiles = os.getenv("SCIBRAIN_GCP_BATCH_PROFILES_JSON", "").strip()
    try:
        profiles = json.loads(raw_profiles) if raw_profiles else {}
        profiles_valid = isinstance(profiles, dict)
    except json.JSONDecodeError:
        profiles = {}
        profiles_valid = False

    variables = [
        {
            "name": "SCIBRAIN_GCP_PROJECT_ID",
            "configured": bool(project_id),
            "value": project_id or None,
            "description": "Google Cloud project ID for Batch, Compute Engine, Artifact Registry and Storage.",
        },
        {
            "name": "SCIBRAIN_GCP_ARTIFACT_BUCKET",
            "configured": bool(bucket),
            "value": bucket or None,
            "description": "Private Cloud Storage bucket for simulation inputs, outputs and checkpoints.",
        },
        {
            "name": "SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT",
            "configured": bool(service_account),
            "value": service_account or None,
            "description": "Least-privilege service account attached to Batch VMs.",
        },
        {
            "name": "SCIBRAIN_GCP_BATCH_PROFILES_JSON",
            "configured": bool(raw_profiles and profiles_valid and profiles),
            "value": None,
            "description": "Server-only solver to private image and machine/GPU mapping.",
        },
    ]
    wif = vercel_wif_from_env()
    wif_fields = {
        "project_number": bool(wif.project_number),
        "pool_id": bool(wif.pool_id),
        "provider_id": bool(wif.provider_id),
        "dispatcher_service_account": bool(wif.dispatcher_service_account),
        "vercel_oidc_token": bool(wif.subject_token),
    }

    return {
        "region": region,
        "ready": all(item["configured"] for item in variables),
        "variables": variables,
        "profiles_valid_json": profiles_valid,
        "configured_profile_names": sorted(profiles) if profiles_valid else [],
        "workload_identity": {
            "configured": all(
                wif_fields[key]
                for key in (
                    "project_number",
                    "pool_id",
                    "provider_id",
                    "dispatcher_service_account",
                )
            ),
            "available": all(wif_fields.values()),
            "fields": wif_fields,
            "token_source": wif.subject_token_source,
            "expected_vercel_subject": (
                f"owner:{os.getenv('SCIBRAIN_VERCEL_TEAM', '').strip()}:"
                f"project:{os.getenv('SCIBRAIN_VERCEL_PROJECT', '').strip()}:"
                "environment:production"
                if os.getenv("SCIBRAIN_VERCEL_TEAM", "").strip()
                and os.getenv("SCIBRAIN_VERCEL_PROJECT", "").strip()
                else None
            ),
        },
        "recommended_resources": {
            "artifact_registry_repository": os.getenv(
                "SCIBRAIN_GCP_ARTIFACT_REPOSITORY", "scientificbrain-solvers"
            ),
            "job_service_account_name": "scibrain-batch-job",
        },
        "notes": [
            "FLASH can run on Google Cloud Batch using a private image built from an authorized source checkout.",
            "FLASH source and FLASH container images must not be redistributed publicly.",
            "GPU machine and accelerator availability must be verified in the selected region.",
        ],
    }
