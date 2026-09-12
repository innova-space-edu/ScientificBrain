# ScientificBrain

ScientificBrain is an evidence-grounded scientific research operating system. Its first domain is plasma physics, but the architecture is intentionally independent of any single AI provider or model.

The central design rule is simple: **scientific progress is represented by defined state, evidence, artifacts, uncertainty, gates and reproducible decisions — not by fluent prose.**

## v0.4: everything important is explicit

ScientificBrain v0.4 introduces strict contracts for the research project itself. A project cannot begin as an undefined chat. It must define:

- scientific question, gap and rationale;
- domain of validity;
- objectives, observables, expected outputs and success criteria;
- variables, units, roles, operational definitions and uncertainty definitions;
- falsifiable hypotheses, mechanisms, predictions and rejection criteria;
- theoretical models, governing equations, closures, approximations and limiting cases;
- experimental design, controls, repetitions and acceptance criteria when applicable;
- diagnostics, calibration, resolution, bandwidth, bias and limits of detection/quantification;
- simulation model, solver, resolution, time integration, initial/boundary conditions, convergence and validation when applicable;
- uncertainty sources and propagation;
- explicit in-scope / out-of-scope boundaries;
- required scientific outputs.

`ResearchProjectDefinition` rejects cross-references to variables, hypotheses or diagnostics that were never defined.

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

Each stage declares required artifacts, gates and a completion rule. A stage does not advance because an LLM produced a convincing response.

## Defined agents

`config/agent_registry.yaml` defines specialized agents rather than one generic scientist:

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

Every agent has one primary responsibility, explicit inputs, explicit outputs, required checks, an inference task and a `can_block` policy.

Agents read structured `ResearchState` + latest research artifacts. They do not simply inherit the prose of the previous agent.

## Self-critique and independent review

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

When multiple cloud providers are configured, ScientificBrain rotates the provider order so the independent review attempts a different provider first. If only one provider exists, the review still runs as a separate role but does not claim provider independence.

## Epistemic status

`config/epistemic_policy.yaml` defines:

- observed
- measured
- derived
- inferred
- supported
- hypothesis
- speculative
- contradicted
- unresolved

Forbidden silent rewrites include:

```text
inferred     -> measured
speculative  -> observed
hypothesis   -> measured
```

A confidence score never substitutes for epistemic status or evidence.

## Scientific artifacts

Research outputs are versioned artifacts rather than loose chat messages. Examples:

```text
project_definition
literature_map
contradiction_map
evidence_records
theory_review
regime_map
competing_hypotheses
experiment_design
diagnostic_plan
uncertainty_budget
simulation_plan
raw_data_or_run_outputs
processing_log
statistical_results
interpretation
alternative_explanations
adversarial_review
reproducibility_report
draft
review_verdict
```

Artifacts record producer, stage, revision, evidence IDs and whether they passed independent review.

## 100-paper plasma corpus

The first ScientificBrain memory target is **100 full-text, deeply reviewed plasma-physics papers**.

Metadata discovery or abstract review does **not** count toward the 100.

`config/corpus_blueprint.yaml` defines 100 exclusive primary slots:

| Primary area | Papers |
| --- | ---: |
| Fundamental kinetic theory | 10 |
| MHD / resistive / Hall / extended-MHD | 10 |
| Plasma shocks | 8 |
| Magnetic reconnection | 8 |
| Plasma focus and pinch | 8 |
| Electric propulsion and PPT | 8 |
| Diagnostics and metrology | 10 |
| PIC/Vlasov/kinetic simulation | 8 |
| Fluid/MHD simulation and verification | 6 |
| Turbulence and transport | 6 |
| Confinement and gyrokinetics | 6 |
| Space and solar plasma | 4 |
| Laser and high-energy-density plasma | 4 |
| Low-temperature/discharge physics | 2 |
| Uncertainty, validation and reproducibility | 2 |
| **Total** | **100** |

Every deeply reviewed paper must preserve the physical regime, equations/model, assumptions, methods, diagnostics, numerical conditions when applicable, uncertainty, results, claim-to-evidence links, limitations, alternatives, reproducibility information and unresolved questions.

## Literature pipeline

ScientificBrain can now run the corpus as incremental jobs suitable for serverless infrastructure:

```text
discover_literature
        ↓
metadata candidates
        ↓
enqueue_selected_reviews
        ↓
review_paper × N
        ↓
PDF full text
        ↓
structured extraction
        ↓
general critic
        ↓
specialist reviews
        ↓
evidence / provenance / reproducibility gates
        ↓
full_text_reviewed
```

Full text can be resolved from arXiv or Unpaywall, or a `review_paper` job can receive an explicit PDF URL. A failed PDF resolution or failed analysis stays failed and is never counted as deep review.

## Cloud-first inference from EDUAI

Cloud models are the default inference path. Local inference is optional.

Default routing:

| Task | Provider order |
| --- | --- |
| research | Google/Gemini → Groq → OpenRouter |
| text | Google/Gemini → Vertex placeholder → Groq → OpenRouter → Cerebras → Together |
| structured | Google/Gemini → Vertex placeholder → Groq → OpenRouter → Cerebras → Together |
| long context | Google/Gemini → Vertex placeholder → OpenRouter → Groq → Cerebras → Together |
| retrieval | Google/Gemini |
| code | Google/Gemini → Vertex placeholder → Groq → Cerebras → OpenRouter → Together |

Providers without credentials are skipped.

Current model defaults are configurable through environment variables; the scientific memory schema does not depend on model IDs.

## Persistent production state

SQLite/FTS5 remains the transparent local development baseline. It is not considered durable storage on Vercel.

For Vercel production use:

```env
SCIBRAIN_STORAGE_BACKEND=supabase
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

Run `migrations/supabase.sql` in the Supabase SQL editor first.

The migration creates persistent tables for:

- projects;
- research states;
- papers;
- evidence;
- research artifacts;
- incremental jobs.

RLS is enabled and no public write policies are created. `SUPABASE_SERVICE_ROLE_KEY` is server-side only.

## API security

A public deployment should enable:

```env
SCIBRAIN_REQUIRE_API_TOKEN=true
SCIBRAIN_API_TOKEN=<strong random secret>
```

Protected project/session/agent/artifact/job endpoints then require:

```http
Authorization: Bearer <token>
```

The web console stores a supplied access token only in browser `sessionStorage` for the current tab. This is an administrative protection layer; a future multi-user deployment should replace it with user authentication and per-project authorization.

## Literature services

Recommended:

```env
OPENALEX_MAILTO=research@example.org
UNPAYWALL_EMAIL=research@example.org
```

Open-access PDF ingestion preserves page markers (`[[PAGE N]]`) so extracted evidence can retain page-level provenance.

## Vercel web console

The repository now contains a static research console at `/` plus Python serverless endpoints under `/api`.

The console exposes:

- system/provider/storage/security health;
- canonical project-definition editor + validator;
- persistent project creation;
- active research state;
- stage-specific agents;
- one-agent-at-a-time execution for serverless safety;
- explicit stage validation;
- human/instrument artifacts;
- literature discovery jobs;
- incremental full-paper review jobs;
- protocol and agent registry;
- persistent project list.

Useful endpoints:

```text
GET  /api/health
GET  /api/manifest
GET  /api/project_schema
GET  /api/project_template
POST /api/validate_project
GET/POST /api/projects
GET  /api/session?session_id=...
POST /api/run_agent
POST /api/validate_stage
POST /api/artifact
GET/POST /api/jobs
POST /api/run_job
```

## Vercel environment variables

Start from `.env.example`. At minimum for a persistent online deployment configure:

```env
SCIBRAIN_INFERENCE_MODE=cloud
SCIBRAIN_STORAGE_BACKEND=supabase
SCIBRAIN_REQUIRE_API_TOKEN=true
SCIBRAIN_API_TOKEN=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...

GEMINI_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...

OPENALEX_MAILTO=...
UNPAYWALL_EMAIL=...
```

Cerebras, Together and additional OpenRouter/Together keys are optional fallbacks.

## Local inference

Ollama remains optional:

```env
SCIBRAIN_INFERENCE_MODE=ollama
SCIBRAIN_OLLAMA_MODEL=qwen3:8b
SCIBRAIN_OLLAMA_URL=http://127.0.0.1:11434
```

or as cloud fallback:

```env
SCIBRAIN_INFERENCE_MODE=cloud
SCIBRAIN_ENABLE_LOCAL_FALLBACK=true
```

Do not point Vercel at `127.0.0.1` expecting it to reach a user's computer.

## Local CLI

```bash
scientific-brain init-db
scientific-brain provider-status --task research
scientific-brain discover --max-results 100
scientific-brain corpus-audit
scientific-brain review-paper 'doi:10.xxxx/example' paper.txt
```

## Tests

```bash
python -m pytest -q
```

GitHub Actions runs tests on `main`, `feat/**` and pull requests to `main`.

## Current scientific boundary

ScientificBrain is a research-assistance and research-orchestration system. Its gates, agent reviews and memory improve traceability and criticism; they do not turn model output into experimental evidence. Claims become scientific evidence only through the defined source, derivation, simulation or measurement chain represented in the project state.
