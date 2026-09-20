# ScientificBrain solver images on Google Artifact Registry

Target registry:

```text
us-central1-docker.pkg.dev/scientificbrain-compute/scientificbrain-solvers/
```

Pinned inputs: WarpX 26.09; PIConGPU 0.8.0; EDIPIC-2D commit `a32863ad046eabe170037e9ef3b849b763d25053` with PETSc 3.14.6/HYPRE; Geant4 11.4.2; NVIDIA PhysicsNeMo 26.08; private FLASH 4.8.

FLASH source is never committed. The NGC key is stored in Google Secret Manager as `scibrain-ngc-api-key` and is only exposed to the dedicated image builder during the PhysicsNeMo build.

From Cloud Shell at the repository root:

```bash
git checkout feat-scientific-tools-ux-v031
git pull
export SCIBRAIN_GCP_PROJECT_ID=scientificbrain-compute
export SCIBRAIN_GCP_REGION=us-central1
export SCIBRAIN_GCP_ARTIFACT_REPOSITORY=scientificbrain-solvers

bash infra/gcp/solvers/build_all.sh --flash-archive /path/to/FLASH4.8.tar
```

If the FLASH archive is not yet in Cloud Shell:

```bash
bash infra/gcp/solvers/build_all.sh --skip-flash
```

Then verify:

```bash
bash infra/gcp/solvers/verify_images.sh
```

Verification refuses success until all six image tags exist and then prints the exact `SCIBRAIN_GCP_BATCH_PROFILES_JSON`.

The image entrypoint is the ScientificBrain runner. Google Batch supplies the job manifest and private Cloud Storage input/output URIs. WarpX, PIConGPU and EDIPIC-2D accept complete execution artifacts now. FLASH supports controlled full runs from the private image when the job supplies a validated `parameters.flash_setup` and the input artifact contains `flash.par` at its root; the container compiles the authorized setup internally and executes it with MPI. Geant4 and PhysicsNeMo remain controlled validation/smoke execution until application/training recipes are registered server-side. Solver completion and scientific validation are recorded as separate states.
