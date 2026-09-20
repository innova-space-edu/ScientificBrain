# ScientificBrain

ScientificBrain is an evidence-grounded scientific research operating system. Its first scientific domain is plasma physics, but its memory, agents, workflow and inference router are designed to remain independent of any single AI model or provider.

The core rule is:

> Scientific progress is represented by defined state, evidence, artifacts, uncertainty, gates and reproducible decisions — not by fluent prose alone.

## v0.6

ScientificBrain 0.6 adds the multi-user research workspace required for production use:

- Supabase Auth accounts;
- Row Level Security per authenticated user;
- editable research folders and nested folders;
- year, research line and area metadata;
- an independent paper corpus for each folder;
- a configurable paper target, defaulting to 100;
- private PDF storage in Supabase Storage;
- strict folder-scoped scientific context;
- paper deduplication by canonical ID, DOI and normalized title;
- attachment of a manually obtained PDF to an existing metadata record;
- Research Agent discovery across OpenAlex, arXiv, Crossref and optional general-web providers;
- DOI/source preservation when full text is not available automatically;
- incremental full-text review jobs suitable for Vercel;
- Spanish as the default web-interface language;
- English, Portuguese and French UI translations;
- versioned acceptance of platform use, AI use, data processing, cybersecurity and scientific responsibility;
- © 2026 Innova Space Edu SpA. All rights reserved.

## User research workspace

Each signed-in user owns an isolated hierarchy:

```text
User
├── Research folder
│   ├── year
│   ├── research line
│   ├── area
│   ├── target paper count
│   ├── nested folders
│   ├── project(s)
│   └── paper corpus
│       ├── uploaded PDFs
│       ├── discovered papers
│       ├── DOI / source links
│       └── deep-review state
├── research sessions
├── scientific artifacts
├── Research Agent searches
└── analysis jobs
```

The active folder is the scientific context boundary:

```text
agent context = project + active folder + active folder corpus
```

A session cannot silently switch to another folder. If the folder corpus changes, the active session corpus is synchronized to the current folder.

## Authentication, privacy and consent

Supabase Auth is the primary identity layer. The browser uses the Supabase publishable key plus the authenticated user's JWT. User-owned tables and the private paper bucket are protected by RLS policies using `auth.uid()`.

ScientificBrain records acceptance by consent-policy version. The current consent covers:

- use of the ScientificBrain platform;
- use of configured AI providers;
- processing and storage of user research data;
- cybersecurity acknowledgement;
- scientific responsibility for verifying AI-generated output;
- confirmation that the user has sufficient rights or authorization to upload/process documents.

The login and registration interface displays a detailed consent modal. The platform can require a new acceptance when the consent version changes.

Do not put a Supabase secret/service-role key in browser code. Browser access uses only the publishable key and user JWT.

## Multilingual web interface

The website defaults to **Spanish**. Users can switch the interface to:

- Spanish (`es`)
- English (`en`)
- Portuguese (`pt`)
- French (`fr`)

The language preference is stored locally in the browser and applies only to the ScientificBrain web interface. Scientific source documents are not automatically rewritten by this UI-language setting.

## Defined scientific project

A project cannot begin as an undefined chat. `ResearchProjectDefinition` requires explicit scientific structure, including:

- scientific question, gap and rationale;
- domain of validity;
- objectives, observables and expected outputs;
- variables, units and operational definitions;
- falsifiable hypotheses and rejection criteria;
- theoretical models and governing equations;
- experimental design and diagnostics when applicable;
- numerical/simulation definition when applicable;
- uncertainty sources and propagation;
- explicit in-scope / out-of-scope boundaries;
- required scientific outputs.

Undefined scientific references are rejected by the definition gate.

## Scientific protocol

The canonical protocol is defined in `config/research_protocol.yaml`:

1. definition
2. literature
3. theory
4. hypothesis
5. design
6. execution
7. analysis
8. interpretation
9. criticism
10. reproducibility
11. writing
12. review

Each stage declares required artifacts, gates and a completion rule.

## Specialized agents

`config/agent_registry.yaml` defines specialized roles including:

- Research Director
- Literature
- Evidence
- Theory
- Hypothesis
- Experiment
- Diagnostics
- Metrology
- Simulation
- Data
- Statistics
- Interpretation
- Alternative Explanations
- Adversarial Critic
- Reproducibility
- Writer
- Reviewer

Agents read structured `ResearchState` plus accepted research artifacts. They do not simply inherit the prose of the previous agent.

Configured agents run through:

```text
primary draft
    ↓
self-critique
    ↓
revision
    ↓
independent reviewer
    ↓
accepted artifact / blocked artifact
```

## Epistemic state

ScientificBrain distinguishes states such as:

- observed
- measured
- derived
- inferred
- supported
- hypothesis
- speculative
- contradicted
- unresolved

Silent rewrites such as `inferred -> measured` or `speculative -> observed` are forbidden.

## Research Agent

The Research Agent can discover scientific information from:

```text
OpenAlex
arXiv
Crossref
Unpaywall / open-access resolution
optional Tavily general-web search
optional Brave general-web search
```

For each candidate source it preserves available metadata such as title, authors, year, journal, DOI, arXiv ID, source URL, abstract and PDF URL.

If full text cannot be resolved automatically, the record remains explicit:

```text
access_status = manual_download / unavailable
manual_lookup_required = true
DOI = preserved when available
source_url = preserved when available
```

The user can later obtain the paper through authorized means and attach the PDF to that same record instead of creating a duplicate.

## Folder-scoped 100-paper corpus

The original plasma corpus target remains 100 deeply reviewed full-text papers, but v0.6 generalizes the concept to **each user's own research folder**.

A user may have, for example:

```text
PF-PPT / CubeSat         target 100
Magnetized shocks        target 120
Magnetic reconnection    target 80
Gyrokinetics             target 100
```

Metadata discovery and abstract review do **not** count as full-text deep review.

Deep review preserves:

- physical regime;
- equations and model;
- assumptions;
- methods;
- diagnostics;
- numerical conditions where relevant;
- uncertainty;
- claim-to-evidence links;
- limitations;
- competing explanations;
- reproducibility information;
- unresolved questions.

## Incremental review pipeline

Vercel-friendly processing is job-based:

```text
folder corpus
    ↓
enqueue_selected_reviews
    ↓
review_paper × N
    ↓
PDF/full text
    ↓
structured extraction
    ↓
general critic
    ↓
specialist reviewers
    ↓
evidence / provenance / reproducibility gates
    ↓
full_text_reviewed
```

The web interface can run one paper at a time or process the pending queue sequentially while the page remains active.

## Cloud-first inference from EDUAI

Online inference is the default. Local models are optional.

Typical routing:

| Task | Default order |
| --- | --- |
| research | Google/Gemini → Groq → OpenRouter |
| text | Google/Gemini → Groq → OpenRouter → Cerebras → Together |
| structured | Google/Gemini → Groq → OpenRouter → Cerebras → Together |
| long context | Google/Gemini → OpenRouter → Groq → Cerebras → Together |
| retrieval | Google/Gemini |
| code | Google/Gemini → Groq → Cerebras → OpenRouter → Together |

Providers without configured credentials are skipped.

## Production persistence

The production Supabase project is configured through environment variables:

```env
SCIBRAIN_STORAGE_BACKEND=supabase
SUPABASE_URL=https://cwbnvukerekgcedcyydd.supabase.co
SUPABASE_PUBLISHABLE_KEY=...
```

A server-only secret key may be used for trusted maintenance jobs if needed, but it must never be exposed in browser code.

Database migrations create and secure:

- profiles;
- research folders;
- projects;
- research states;
- user folder papers;
- research searches;
- artifacts;
- jobs;
- versioned consent records;
- private `scibrain-papers` storage.

## Vercel API layout

To avoid excessive Python Functions, the deployment uses four physical gateways:

```text
/api/meta.py
/api/workspace.py
/api/research.py
/api/science.py
```

Public route names are preserved through `vercel.json` rewrites.


## Scientific Tools and NVIDIA provider — v0.23

ScientificBrain now separates scientific capabilities from the general inference router.

The deployed application is:

https://scientific-brain.vercel.app

The dedicated Scientific Tools workspace is:

https://scientific-brain.vercel.app/scientific-tools

Local/development route:

```text
/scientific-tools
```

The Scientific Tools page centralizes:

- NVIDIA hosted API/NIM status;
- ScientificBrain Physics Skills;
- FLASH high-fidelity solver integration;
- NVIDIA PhysicsNeMo;
- NVIDIA BioNeMo/custom scientific NIM capabilities;
- FLASH → HDF5/yt → PhysicsNeMo → 2D/3D surrogate → physical validation.

Credentials remain server-side. `NVIDIA_API_KEY` is used for hosted NVIDIA API Catalog inference; `NGC_API_KEY` is kept separate for NGC/NIM container/model access when required. Custom scientific endpoints are registered by the server through `SCIBRAIN_NVIDIA_CAPABILITIES_JSON`; the browser cannot supply arbitrary endpoint URLs.

Physics skills live in the separate repository:

https://github.com/innova-space-edu/scientificbrain-physics-skills

The physics-skills repository documents this ScientificBrain integration in `references/SCIENTIFICBRAIN_INTEGRATION.md`.

Planned extensions preserved in the toolkit roadmap are **PIC/hybrid routing, additional diagnostics, distributed simulation/training, active learning, and direct ScientificBrain orchestration**.


## Physics orchestration — v0.24

The Scientific Tools workspace now exposes source-grounded physics tooling independent of the NVIDIA credential:

- a local plasma model router using Debye length, electron/ion skin depths, gyro-radii, plasma beta and Alfvén Mach;
- reproducible Monte Carlo parameter sampling;
- the 39-skill ScientificBrain Physics Toolkit;
- source-grounded solver maps for FLASH, WarpX, PIConGPU, EDIPIC-2D, Geant4, PhysicsNeMo and openPMD;
- a server-only physics worker registry for heavy solver/HPC jobs;
- centralized NVIDIA/BioNeMo/PhysicsNeMo capabilities when the NVIDIA credential is available.

Heavy simulations are never executed synchronously inside the browser or Vercel function. ScientificBrain submits immutable jobs only to workers configured in `SCIBRAIN_PHYSICS_WORKERS_JSON`. Browser requests cannot provide arbitrary worker URLs or worker tokens.

## Public Scientific Tools page

The physics stack described below is exposed through the authenticated ScientificBrain interface at:

https://scientific-brain.vercel.app/scientific-tools

This page is the user-facing entry point for the plasma model router, Monte Carlo utilities, solver/HPC status, NVIDIA/NIM capabilities, PhysicsNeMo/BioNeMo status and reproducible physics-job preparation.

## Reproducible physics jobs — v0.25

ScientificBrain now prepares typed physics job manifests for FLASH, WarpX, PIConGPU, EDIPIC-2D, Geant4 and PhysicsNeMo. A browser may specify scientific parameters and resource requests, but cannot inject executable paths, shell commands, endpoint URLs, API keys, worker tokens or scheduler commands.

Each prepared job includes solver/action/model identity, input artifact reference, resource request, expected outputs/validation requirements and an execution profile. Heavy execution remains delegated to a server-configured worker/HPC endpoint.

## What ScientificBrain can generate

ScientificBrain is not only a chat/reasoning layer. It can produce traceable scientific artifacts across the full research-compute loop:

- literature/evidence graphs, contradictions, hypotheses and research plans;
- physical-regime calculations and solver/model hierarchies;
- reproducible jobs for FLASH, WarpX, PIConGPU, EDIPIC-2D, Geant4 and PhysicsNeMo;
- native simulation data (HDF5, openPMD and solver-specific outputs);
- derived field/particle/shock/energy diagnostics;
- Monte Carlo campaigns and uncertainty distributions;
- canonical and multi-fidelity scientific datasets;
- PhysicsNeMo/FNO/PINO surrogate checkpoints and predictions;
- active-learning query sets for choosing the next expensive simulation;
- manifests, checkpoints, validation matrices and provenance for reproducibility.

Public explanation page:

https://scientific-brain.vercel.app/scientific-capabilities

The solver outputs are synthetic scientific data produced by explicit physical/numerical models. ScientificBrain does not relabel model output as experimental measurement and does not accept a surrogate outside its validated domain by default.

## Google Cloud Batch / GPU execution — v0.26

ScientificBrain can now translate a validated Physics Job into a Google Cloud Batch job. Google Batch can provision Compute Engine CPU or GPU resources, execute a **server-approved solver container**, stream logs to Cloud Logging and use Cloud Storage for input/output artifacts.

The browser cannot specify container images, shell commands, machine types, service-account identities or Google credentials. These are stored in server configuration. GPU profiles can be configured for WarpX, PIConGPU and PhysicsNeMo; CPU profiles can be used for FLASH, EDIPIC-2D and Geant4 as appropriate.

Authentication uses Google Application Default Credentials where possible. For production on Google Cloud, an attached least-privilege service account is preferred; from external hosting, Workload Identity Federation is preferred over long-lived service-account keys.

See `docs/GOOGLE_CLOUD_BATCH.md` and `docs/SCIENTIFIC_COMPUTE.md`.

## Google Cloud result ingestion — v0.27

ScientificBrain can now complete the cloud simulation loop by reading only the output prefix assigned to a known scientific job. Solver containers are expected to write `scientificbrain-output.json` plus native outputs beneath:

```text
gs://<artifact-bucket>/scientificbrain/jobs/<scientific-job-id>/
```

The authenticated API can list files under that fixed prefix and retrieve the fixed manifest object. It does not expose arbitrary Cloud Storage browsing paths supplied by the browser.

The Scientific Tools workspace can therefore perform:

```text
prepare job
→ preview/submit Google Batch
→ monitor Batch
→ solver writes HDF5/openPMD/native output
→ list output artifacts
→ read scientificbrain-output.json
→ diagnostics / validation / UQ / multi-fidelity / PhysicsNeMo
```

## Google Cloud bootstrap and private FLASH — v0.28

ScientificBrain now includes an idempotent Google Cloud bootstrap under `infra/gcp/`. It creates the private artifact bucket, a private Artifact Registry Docker repository and a dedicated Batch job service account, then grants the runtime roles needed for Batch state reporting, Cloud Logging, Cloud Storage objects and private image pulls.

The four primary production variables are:

```text
SCIBRAIN_GCP_PROJECT_ID
SCIBRAIN_GCP_ARTIFACT_BUCKET
SCIBRAIN_GCP_JOB_SERVICE_ACCOUNT
SCIBRAIN_GCP_BATCH_PROFILES_JSON
```

FLASH is supported as a Google Cloud Batch solver. Its image must be built privately from an authorized FLASH checkout and must never be published through this repository.

See `docs/GOOGLE_CLOUD_BOOTSTRAP.md`.

## Vercel OIDC → Google Workload Identity Federation — v0.29

Production Google authentication now uses the Vercel-issued `VERCEL_OIDC_TOKEN` and the verified provider `projects/260133939682/locations/global/workloadIdentityPools/vercel/providers/scientificbrain`.

ScientificBrain exchanges that OIDC token through Google Security Token Service and then impersonates `scibrain-vercel-dispatcher@scientificbrain-compute.iam.gserviceaccount.com` through IAM Credentials. The resulting OAuth token is short-lived and cached only in process memory.

An authenticated `gcp_auth_probe` operation verifies the complete Vercel → STS → service-account impersonation flow without returning credentials.

See `docs/VERCEL_GCP_WIF.md`.

## Provider startup hardening — v0.30

Scientific Tools now loads each provider status independently. An incomplete NVIDIA capability configuration can no longer prevent Google Cloud, physics skills, workers or Monte Carlo tools from loading.

NVIDIA status ignores invalid placeholder capability endpoints and reports non-secret configuration warnings instead.

On Vercel, Google authentication no longer silently falls back to Application Default Credentials. If the Workload Identity variables or `VERCEL_OIDC_TOKEN` are missing, the authenticated WIF probe returns an explicit non-secret diagnostic. ADC remains available for local or Google-hosted development where appropriate.

Google Batch preview is disabled until at least one solver execution profile exists.

## Scientific Tools sidebar workspace — v0.31

The Scientific Tools interface now uses a fixed navigation sidebar with one focused workspace visible at a time:

- Summary;
- Physics Router;
- Monte Carlo / UQ;
- NVIDIA;
- Prepare Simulation;
- Solvers;
- Google Cloud;
- Results;
- Physics Skills;
- Diagnostics.

Provider warnings and raw technical output are no longer mixed into the normal workflow. Google Cloud setup is isolated in its own view, simulator cards distinguish scientific readiness from cloud-image readiness, and result JSON is shown only when a tool is executed.

Vercel OIDC retrieval also checks both the standard `VERCEL_OIDC_TOKEN` runtime variable and the Python `vercel.functions.get_env()` system-environment accessor before reporting a missing token.

## Development

```bash
pip install -e ".[dev]"
pytest -q
node --check assets/i18n.js
node --check assets/app.js
node --check assets/app_plus.js
```

CI executes Python tests and JavaScript syntax checks for all three frontend scripts.

---

© 2026 Innova Space Edu SpA. Todos los derechos reservados.
