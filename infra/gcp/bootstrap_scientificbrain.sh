#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${SCIBRAIN_GCP_PROJECT_ID:-}"
REGION="${SCIBRAIN_GCP_REGION:-us-central1}"
BUCKET="${SCIBRAIN_GCP_ARTIFACT_BUCKET:-}"
REPOSITORY="${SCIBRAIN_GCP_ARTIFACT_REPOSITORY:-scientificbrain-solvers}"
JOB_SA_NAME="${SCIBRAIN_GCP_JOB_SA_NAME:-scibrain-batch-job}"
JOB_SA_EMAIL="${JOB_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if [[ -z "${PROJECT_ID}" ]]; then
  echo "SCIBRAIN_GCP_PROJECT_ID is required" >&2
  exit 2
fi
if [[ -z "${BUCKET}" ]]; then
  echo "SCIBRAIN_GCP_ARTIFACT_BUCKET is required" >&2
  exit 2
fi

gcloud config set project "${PROJECT_ID}"

gcloud services enable   batch.googleapis.com   compute.googleapis.com   artifactregistry.googleapis.com   storage.googleapis.com   iam.googleapis.com   logging.googleapis.com   cloudbuild.googleapis.com   --project "${PROJECT_ID}"

if ! gcloud iam service-accounts describe "${JOB_SA_EMAIL}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${JOB_SA_NAME}"     --display-name="ScientificBrain Batch Job"     --project "${PROJECT_ID}"
fi

if ! gcloud storage buckets describe "gs://${BUCKET}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET}"     --project "${PROJECT_ID}"     --location "${REGION}"     --default-storage-class STANDARD     --uniform-bucket-level-access     --public-access-prevention
else
  gcloud storage buckets update "gs://${BUCKET}"     --uniform-bucket-level-access     --public-access-prevention
fi

if ! gcloud artifacts repositories describe "${REPOSITORY}"   --location "${REGION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPOSITORY}"     --repository-format docker     --location "${REGION}"     --description="ScientificBrain solver images"     --project "${PROJECT_ID}"
fi

gcloud projects add-iam-policy-binding "${PROJECT_ID}"   --member="serviceAccount:${JOB_SA_EMAIL}"   --role="roles/batch.agentReporter" >/dev/null

gcloud projects add-iam-policy-binding "${PROJECT_ID}"   --member="serviceAccount:${JOB_SA_EMAIL}"   --role="roles/logging.logWriter" >/dev/null

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}"   --member="serviceAccount:${JOB_SA_EMAIL}"   --role="roles/storage.objectUser" >/dev/null

gcloud artifacts repositories add-iam-policy-binding "${REPOSITORY}"   --location "${REGION}"   --project "${PROJECT_ID}"   --member="serviceAccount:${JOB_SA_EMAIL}"   --role="roles/artifactregistry.reader" >/dev/null

cat <<EOF

ScientificBrain Google Cloud base infrastructure is ready.

SCIBRAIN_GCP_PROJECT_ID=${PROJECT_ID}
SCIBRAIN_GCP_REGION=${REGION}
SCIBRAIN_GCP_ARTIFACT_BUCKET=${BUCKET}
SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT=${JOB_SA_EMAIL}
SCIBRAIN_GCP_ARTIFACT_REPOSITORY=${REPOSITORY}

The identity that submits Batch jobs still needs roles/batch.jobsEditor
and roles/iam.serviceAccountUser on the job service account.

Next: build solver images, push them to Artifact Registry, fill
SCIBRAIN_GCP_BATCH_PROFILES_JSON, and enable SCIBRAIN_GCP_BATCH_ENABLED=true.
EOF
