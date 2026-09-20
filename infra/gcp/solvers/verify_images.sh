#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ID="${SCIBRAIN_GCP_PROJECT_ID:-scientificbrain-compute}"
REGION="${SCIBRAIN_GCP_REGION:-us-central1}"
REPOSITORY="${SCIBRAIN_GCP_ARTIFACT_REPOSITORY:-scientificbrain-solvers}"
python3 - "${DIR}/solver-images.json" "${REGION}" "${PROJECT_ID}" "${REPOSITORY}" <<'PY'
import json, subprocess, sys
manifest,region,project,repo=sys.argv[1:]
data=json.load(open(manifest)); failed=[]
for solver,spec in data.items():
    uri=f"{region}-docker.pkg.dev/{project}/{repo}/{solver}:{spec['tag']}"
    p=subprocess.run(["gcloud","artifacts","docker","images","describe",uri,"--format=value(image_summary.digest)"],text=True,capture_output=True)
    if p.returncode:
        print(f"MISSING {solver}: {uri}"); failed.append(solver)
    else:
        print(f"READY   {solver}: {uri} {p.stdout.strip()}")
if failed:
    print("Missing images: "+", ".join(failed),file=sys.stderr); raise SystemExit(1)
PY
echo
echo "SCIBRAIN_GCP_BATCH_PROFILES_JSON="
python3 "${DIR}/render_batch_profiles.py" --project "${PROJECT_ID}" --region "${REGION}" --repository "${REPOSITORY}"
