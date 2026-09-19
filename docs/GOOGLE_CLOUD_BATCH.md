# Google Cloud Batch integration

ScientificBrain can dispatch approved physics jobs to Google Cloud Batch. Batch provisions Compute Engine resources for each job, including GPU-backed VMs when the configured profile requests compatible NVIDIA accelerators.

## Architecture

ScientificBrain browser
→ authenticated ScientificBrain API
→ typed PhysicsJob
→ GoogleCloudBatch adapter
→ Google Batch jobs.create
→ Compute Engine CPU/GPU VM(s)
→ approved solver container
→ Cloud Storage artifacts + Cloud Logging

The browser never supplies container images, commands, Google credentials, machine types or service-account identities.

## Authentication

Preferred production authentication follows Google Application Default Credentials (ADC). On Google Cloud, attach a least-privilege user-managed service account to the service hosting the dispatcher. From outside Google Cloud, use Workload Identity Federation when possible.

A server-only `SCIBRAIN_GCP_SERVICE_ACCOUNT_JSON` fallback is supported for environments that cannot use ADC, but long-lived service-account keys carry additional security risk.

The identity creating jobs needs Batch job creation permissions and permission to use the service account attached to Batch-created VMs.

## Required environment

```env
SCIBRAIN_GCP_BATCH_ENABLED=true
SCIBRAIN_GCP_PROJECT_ID=
SCIBRAIN_GCP_REGION=us-central1
SCIBRAIN_GCP_ARTIFACT_BUCKET=
SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT=
SCIBRAIN_GCP_BATCH_PROFILES_JSON={}
```

Example server-only profiles:

```json
{
  "flash": {
    "image_uri": "REGION-docker.pkg.dev/PROJECT/scientificbrain/flash:4.8",
    "machine_type": "c3-standard-22"
  },
  "warpx": {
    "image_uri": "REGION-docker.pkg.dev/PROJECT/scientificbrain/warpx:VERSION",
    "machine_type": "g2-standard-8",
    "gpu_type": "nvidia-l4",
    "max_gpus_per_node": 1,
    "install_gpu_drivers": true
  },
  "picongpu": {
    "image_uri": "REGION-docker.pkg.dev/PROJECT/scientificbrain/picongpu:VERSION",
    "machine_type": "g2-standard-8",
    "gpu_type": "nvidia-l4",
    "max_gpus_per_node": 1,
    "install_gpu_drivers": true
  },
  "physicsnemo": {
    "image_uri": "REGION-docker.pkg.dev/PROJECT/scientificbrain/physicsnemo:2.2.2",
    "machine_type": "g2-standard-8",
    "gpu_type": "nvidia-l4",
    "max_gpus_per_node": 1,
    "install_gpu_drivers": true
  }
}
```

Machine/GPU compatibility and regional GPU availability must be verified when the profile is provisioned.

## Solver container contract

Each approved image must have its own safe default ENTRYPOINT. ScientificBrain does not pass shell commands.

The container receives:

- `SCIBRAIN_JOB_JSON_B64`: validated PhysicsJob manifest;
- `SCIBRAIN_INPUT_URI`: Cloud Storage input location;
- `SCIBRAIN_OUTPUT_URI`: Cloud Storage output prefix;
- `SCIBRAIN_SOLVER`, `SCIBRAIN_ACTION`, `SCIBRAIN_JOB_ID`;
- `SCIBRAIN_MPI_RANKS`;
- Google Batch variables such as `BATCH_TASK_INDEX`, and for multi-node jobs `BATCH_HOSTS_FILE`.

The solver image is responsible for downloading the authorized input artifact, executing the solver with its fixed wrapper, writing native outputs/checkpoints and uploading a machine-readable output manifest.

## GPU and MPI

GPU profiles translate requested GPUs into Batch accelerators and enable GPU driver installation when configured.

For jobs with more than one node, ScientificBrain requests one Batch task per node and enables `requireHostsFile` plus `permissiveSsh`. The solver image must contain the MPI runtime and its entrypoint must use the Batch hosts file appropriately.

## Output

A successful physics run should leave:

- native solver output;
- logs;
- checkpoints when applicable;
- `scientificbrain-output.json` manifest;
- canonical diagnostics or references to the native HDF5/openPMD data;
- validation status.

ScientificBrain then ingests those artifacts for diagnostics, UQ, multi-fidelity datasets, PhysicsNeMo training and active learning.
