#!/usr/bin/env bash
set -euo pipefail
PROJECT_ID="${SCIBRAIN_GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${SCIBRAIN_GCP_REGION:-us-central1}"
REPOSITORY="${SCIBRAIN_GCP_ARTIFACT_REPOSITORY:-scientificbrain-solvers}"
BUILDER_NAME=scibrain-image-builder
BUILDER_SA="${BUILDER_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
[[ -n "${PROJECT_ID}" ]] || { echo "SCIBRAIN_GCP_PROJECT_ID is required" >&2; exit 2; }
gcloud config set project "${PROJECT_ID}" >/dev/null
gcloud services enable cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com iam.googleapis.com logging.googleapis.com storage.googleapis.com --project "${PROJECT_ID}"
if ! gcloud iam service-accounts describe "${BUILDER_SA}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${BUILDER_NAME}" --display-name="ScientificBrain Solver Image Builder" --project "${PROJECT_ID}"
fi
for role in roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${BUILDER_SA}" --role="${role}" >/dev/null
done
CALLER="$(gcloud config get-value account 2>/dev/null)"
if [[ -n "${CALLER}" ]]; then
  gcloud iam service-accounts add-iam-policy-binding "${BUILDER_SA}" --member="user:${CALLER}" --role=roles/iam.serviceAccountUser --project "${PROJECT_ID}" >/dev/null
fi
if ! gcloud secrets describe scibrain-ngc-api-key --project "${PROJECT_ID}" >/dev/null 2>&1; then
  if [[ -z "${NGC_API_KEY:-}" ]]; then
    read -r -s -p "NGC API key (stored in Google Secret Manager; hidden): " NGC_API_KEY
    echo
  fi
  printf '%s' "${NGC_API_KEY}" | gcloud secrets create scibrain-ngc-api-key --replication-policy=automatic --data-file=- --project "${PROJECT_ID}"
elif [[ "${SCIBRAIN_UPDATE_NGC_SECRET:-0}" == 1 && -n "${NGC_API_KEY:-}" ]]; then
  printf '%s' "${NGC_API_KEY}" | gcloud secrets versions add scibrain-ngc-api-key --data-file=- --project "${PROJECT_ID}"
fi
gcloud secrets add-iam-policy-binding scibrain-ngc-api-key --member="serviceAccount:${BUILDER_SA}" --role=roles/secretmanager.secretAccessor --project "${PROJECT_ID}" >/dev/null
echo "Image builder ready: ${BUILDER_SA}"
