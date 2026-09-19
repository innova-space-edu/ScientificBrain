# Google Cloud bootstrap for ScientificBrain

This setup creates the Google Cloud resources behind the four primary production variables.

Required values:
- SCIBRAIN_GCP_PROJECT_ID: the Google Cloud project ID.
- SCIBRAIN_GCP_ARTIFACT_BUCKET: a globally unique private Cloud Storage bucket.
- SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT: the dedicated service account attached to Batch VMs.
- SCIBRAIN_GCP_BATCH_PROFILES_JSON: the server-only solver/image/machine mapping created after solver images exist.

Run from Cloud Shell or another machine with gcloud authenticated:

    export SCIBRAIN_GCP_PROJECT_ID="your-project-id"
    export SCIBRAIN_GCP_REGION="us-central1"
    export SCIBRAIN_GCP_ARTIFACT_BUCKET="globally-unique-scientificbrain-bucket"
    bash infra/gcp/bootstrap_scientificbrain.sh

The bootstrap enables Batch, Compute Engine, Artifact Registry, Cloud Storage, IAM, Logging and Cloud Build APIs. It creates:
- a private Cloud Storage bucket with uniform bucket-level access and public access prevention;
- a private Docker repository named scientificbrain-solvers;
- a dedicated service account named scibrain-batch-job.

The Batch job service account receives:
- roles/batch.agentReporter on the project;
- roles/logging.logWriter on the project;
- roles/storage.objectUser on the scientific bucket;
- roles/artifactregistry.reader on the private solver repository.

The identity that submits jobs is separate. It needs Batch Job Editor and permission to use the selected job service account.

FLASH can run on Google Cloud Batch. It must use a private image built from an authorized FLASH source checkout. Do not commit FLASH source, the FLASH TAR archive, or a public Docker context containing FLASH to GitHub.

Use infra/gcp/batch-profiles.template.json after solver images are pushed. The L4/G2 entries are examples only: verify actual machine/GPU availability and quota in the selected region before production use.

After these values are configured, the next phase is to build and push the real WarpX, PIConGPU, EDIPIC-2D, Geant4, PhysicsNeMo and private FLASH images, run one cheap smoke benchmark per solver, then launch the first cross-fidelity plasma benchmark from ScientificBrain.


## Vercel production authentication

ScientificBrain production uses Workload Identity Federation instead of a service-account JSON key.

Verified identity:
- issuer: https://oidc.vercel.com/innova-space-edu
- audience: https://vercel.com/innova-space-edu
- subject: owner:innova-space-edu:project:scientific-brain:environment:production
- pool: vercel
- provider: scientificbrain
- dispatcher: scibrain-vercel-dispatcher@scientificbrain-compute.iam.gserviceaccount.com

See `VERCEL_GCP_WIF.md` for the runtime STS and service-account impersonation flow.
