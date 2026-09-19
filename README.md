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

The dedicated workspace is available at:

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

Planned extensions preserved in the toolkit roadmap are **PIC/hybrid routing, additional diagnostics, distributed simulation/training, active learning, and direct ScientificBrain orchestration**.

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
