# Vercel OIDC to Google Workload Identity Federation

ScientificBrain production uses short-lived credentials. No Google service-account JSON key is required.

## Verified production identity

- Vercel team issuer: `https://oidc.vercel.com/innova-space-edu`
- Vercel audience: `https://vercel.com/innova-space-edu`
- Vercel subject: `owner:innova-space-edu:project:scientific-brain:environment:production`
- Google project number: `260133939682`
- Workload Identity Pool: `vercel`
- Provider: `scientificbrain`
- Dispatcher service account: `scibrain-vercel-dispatcher@scientificbrain-compute.iam.gserviceaccount.com`

## Runtime flow

```text
VERCEL_OIDC_TOKEN
  ↓
Google Security Token Service
  audience = //iam.googleapis.com/projects/260133939682/locations/global/workloadIdentityPools/vercel/providers/scientificbrain
  ↓
federated access token
  ↓
IAM Credentials generateAccessToken
  ↓
short-lived token for scibrain-vercel-dispatcher
  ↓
Google Batch / Cloud Storage
```

ScientificBrain caches the short-lived impersonated token only in process memory and refreshes it before expiration. Tokens are never returned by status or probe endpoints.

## Vercel environment variables

Configure these values for the ScientificBrain project:

```env
SCIBRAIN_GCP_PROJECT_ID=scientificbrain-compute
SCIBRAIN_GCP_PROJECT_NUMBER=260133939682
SCIBRAIN_GCP_REGION=us-central1
SCIBRAIN_GCP_ARTIFACT_BUCKET=scientificbrain-compute-artifacts-260133939682
SCIBRAIN_GCP_ARTIFACT_REPOSITORY=scientificbrain-solvers
SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT=scibrain-batch-job@scientificbrain-compute.iam.gserviceaccount.com
SCIBRAIN_GCP_DISPATCHER_SERVICE_ACCOUNT=scibrain-vercel-dispatcher@scientificbrain-compute.iam.gserviceaccount.com
SCIBRAIN_GCP_WIF_POOL_ID=vercel
SCIBRAIN_GCP_WIF_PROVIDER_ID=scientificbrain
SCIBRAIN_VERCEL_TEAM=innova-space-edu
SCIBRAIN_VERCEL_PROJECT=scientific-brain
```

Do not manually create `VERCEL_OIDC_TOKEN`. Vercel supplies it at runtime when Secure Backend Access with OIDC Federation is enabled.

`SCIBRAIN_GCP_BATCH_ENABLED` and `SCIBRAIN_GCP_BATCH_PROFILES_JSON` are enabled after the solver images are present in Artifact Registry.

## Safe verification

The authenticated endpoint:

```text
GET /api/science?op=gcp_auth_probe
```

performs the STS exchange and service-account impersonation, then returns only booleans and the authentication mode. It never returns the token.
