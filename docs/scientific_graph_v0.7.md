# ScientificBrain v0.7 — Scientific Knowledge Graph

ScientificBrain v0.7 adds a folder-scoped scientific graph that converts deeply reviewed literature into explicit, queryable scientific structure.

## Canonical flow

```text
full-text reviewed paper
        ↓
PaperAnalysis
        ↓
Paper node
Claim nodes
Evidence nodes
Model nodes
Assumption nodes
Equation nodes
Diagnostic nodes
        ↓
provenance-preserving edges
        ↓
Contradiction Agent
        ↓
contradiction candidates
        ↓
Hypothesis Competition Agent
        ↓
competing falsifiable hypotheses
```

The deterministic graph builder never invents cross-paper relations. It only materializes relations already supported by stored paper analyses. Cross-paper contradictions and competing hypotheses are produced by dedicated agents and are stored with `candidate` status until scientifically reviewed.

## Core graph relations

- `asserted_in`
- `supported_by`
- `contradicted_by`
- `contains`
- `uses_model`
- `uses_assumption`
- `uses_equation`
- `uses_diagnostic`
- `measures`
- `depends_on`
- `extends`
- `replicates`
- `same_dataset`
- `shared_source`
- `discriminates`
- `tests`

## Epistemic states

Graph nodes preserve explicit epistemic state:

- observed
- measured
- derived
- inferred
- supported
- hypothesis
- speculative
- contradicted
- unresolved

A claim does not become a measurement merely because an LLM rewrites it fluently.

## Contradiction analysis

The contradiction agent must distinguish a true scientific incompatibility from an apparent contradiction caused by different regimes, geometry, diagnostics, assumptions, initial/boundary conditions, dimensionality, collisionality, magnetization, normalization or uncertainty.

Each contradiction candidate stores:

- exact graph claim IDs;
- contradiction type;
- scientific summary;
- relevant regime difference;
- plausible reconciliation/explanation;
- discriminating observables;
- required test;
- confidence;
- candidate/review status.

## Hypothesis competition

A contradiction can seed a set of competing hypotheses. Every candidate hypothesis must define:

- mechanism;
- claims it explains;
- supporting and contradicting evidence;
- falsifiable predictions;
- discriminating observables;
- discriminating experiment/simulation;
- regime of validity;
- explicit rejection criterion.

No winner is selected merely because one explanation sounds plausible.

## User isolation

All graph tables are scoped by:

```text
owner_id + folder_id
```

Supabase RLS enforces `owner_id = auth.uid()` for graph nodes, edges, contradictions, hypothesis competitions and evidence lineage.

## API operations

Authenticated requests use the existing `/api/science` gateway:

```text
POST /api/science?op=build_graph
POST /api/science?op=detect_contradictions
POST /api/science?op=generate_hypotheses
GET  /api/science?op=graph_summary&folder_id=...
GET  /api/science?op=graph_nodes&folder_id=...
GET  /api/science?op=graph_edges&folder_id=...
GET  /api/science?op=contradictions&folder_id=...
GET  /api/science?op=hypotheses&folder_id=...
```

The same operations are available as persistent ScientificBrain jobs:

- `build_scientific_graph`
- `detect_contradictions`
- `generate_competing_hypotheses`

This enables long-running research workflows to remain compatible with Vercel-style incremental execution.
