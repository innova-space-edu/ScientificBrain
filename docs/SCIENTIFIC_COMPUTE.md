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
