# Scientific compute in ScientificBrain

ScientificBrain's physics layer is designed to generate **traceable scientific artifacts**, not only text.

## What it can generate

### Literature/reasoning artifacts
- structured paper reviews;
- claim/evidence graphs;
- contradictions and open gaps;
- falsifiable hypotheses;
- equations, assumptions and domains of validity;
- simulation and experimental plans.

### Simulation artifacts
- typed physics job manifests;
- FLASH HDF5 outputs;
- WarpX / PIConGPU openPMD outputs;
- EDIPIC-2D native diagnostics;
- Geant4 scoring outputs;
- checkpoints and logs.

### Derived scientific data
- fields E/B/J/density/temperature;
- particle phase space and distributions;
- shock position, velocity, thickness and jumps;
- energy/conservation diagnostics;
- MCC/DSMC event statistics;
- Monte Carlo sample/result tables;
- uncertainty distributions and quantiles.

### Scientific ML
- canonical datasets;
- multi-fidelity datasets;
- PhysicsNeMo checkpoints;
- FNO/PINO/surrogate predictions;
- held-out validation metrics;
- uncertainty maps;
- active-learning query sets.

## Compute backends

ScientificBrain itself is the orchestrator. Execution can happen on:
- a local ScientificBrain worker;
- an institutional GPU server;
- a multi-node HPC cluster;
- Google Cloud Batch/Compute Engine;
- approved NVIDIA/NIM endpoints for supported AI capabilities.

Vercel hosts the web/API control plane; it is not used as the heavy simulation node.


## Physics Skills v0.3 runtime operations

ScientificBrain exposes two additional authenticated deterministic operations:

```text
POST /api/science?op=physics_model_route
POST /api/science?op=physics_validate
```

`physics_model_route` is the high-level Physics Skill router. It defines the target observable and acceptance criterion, selects the model family, delegates plasma scale screening to the existing `physics_route` path when the required plasma inputs are available, and returns unresolved information instead of silently inventing it.

`physics_validate` is an observable-level validation gate. It aggregates explicit checks such as dimensions, regime validity, convergence, conservation, benchmark evidence, uncertainty and provenance into `accepted`, `conditional`, `rejected` or `blocked`. Missing required evidence is always `blocked`.

The existing endpoint remains unchanged for backward compatibility:

```text
POST /api/science?op=physics_route
```

It continues to perform detailed plasma scale screening and fluid/hybrid/PIC candidate routing.
