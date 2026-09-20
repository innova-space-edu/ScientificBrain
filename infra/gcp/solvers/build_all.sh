#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ID="${SCIBRAIN_GCP_PROJECT_ID:-scientificbrain-compute}"
REGION="${SCIBRAIN_GCP_REGION:-us-central1}"
REPOSITORY="${SCIBRAIN_GCP_ARTIFACT_REPOSITORY:-scientificbrain-solvers}"
FLASH_ARCHIVE="${SCIBRAIN_FLASH_ARCHIVE:-}"
SKIP_FLASH=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --flash-archive) FLASH_ARCHIVE="$2"; shift 2;;
    --skip-flash) SKIP_FLASH=1; shift;;
    -h|--help) echo "Usage: $0 [--flash-archive /path/to/FLASH4.8.tar] [--skip-flash]"; exit 0;;
    *) echo "Unknown option: $1" >&2; exit 2;;
  esac
done
export SCIBRAIN_GCP_PROJECT_ID="${PROJECT_ID}" SCIBRAIN_GCP_REGION="${REGION}" SCIBRAIN_GCP_ARTIFACT_REPOSITORY="${REPOSITORY}"
bash "${DIR}/bootstrap_image_builder.sh"
image_uri(){ echo "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/$1:$2"; }
build_public(){
  local solver="$1" tag="$2" image
  image="$(image_uri "${solver}" "${tag}")"
  echo "=== Building ${solver} -> ${image} ==="
  gcloud builds submit "${DIR}" --project "${PROJECT_ID}" --config "${DIR}/cloudbuild.docker.yaml" --substitutions="_DOCKERFILE=${solver}/Dockerfile,_IMAGE=${image}"
}
build_public warpx 26.09-cuda12.8
build_public picongpu 0.8.0-cuda12.4
build_public edipic2d a32863ad-petsc3.14.6
build_public geant4 11.4.2
PHYSICSNEMO_IMAGE="$(image_uri physicsnemo 26.08)"
echo "=== Mirroring/extending PhysicsNeMo -> ${PHYSICSNEMO_IMAGE} ==="
gcloud builds submit "${DIR}" --project "${PROJECT_ID}" --config "${DIR}/cloudbuild.physicsnemo.yaml" --substitutions="_IMAGE=${PHYSICSNEMO_IMAGE}"
if [[ "${SKIP_FLASH}" == 0 ]]; then
  if [[ -z "${FLASH_ARCHIVE}" || ! -f "${FLASH_ARCHIVE}" ]]; then
    echo "FLASH archive not supplied; FLASH remains pending." >&2
  else
    trap 'rm -f "${DIR}/flash-private/FLASH4.8.tar"' EXIT
    cp "${FLASH_ARCHIVE}" "${DIR}/flash-private/FLASH4.8.tar"
    FLASH_IMAGE="$(image_uri flash 4.8-private)"
    gcloud builds submit "${DIR}" --project "${PROJECT_ID}" --config "${DIR}/cloudbuild.docker.yaml" --substitutions="_DOCKERFILE=flash-private/Dockerfile,_IMAGE=${FLASH_IMAGE}"
    rm -f "${DIR}/flash-private/FLASH4.8.tar"; trap - EXIT
  fi
fi
echo "Build submissions complete. Run: bash infra/gcp/solvers/verify_images.sh"
