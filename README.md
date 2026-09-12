# ScientificBrain

ScientificBrain is a research-oriented scientific memory and reasoning system focused initially on plasma physics. It is designed to ingest literature, preserve provenance, retrieve evidence, critique experiments/theory/simulations, detect contradictions, and generate evidence-bounded research hypotheses.

## Core principles

- **Evidence before fluency:** every scientific claim should remain traceable to a source and, when possible, to a passage/equation/figure context.
- **Layered memory:** bibliographic, semantic, evidence, episodic and frontier/open-question memory are stored separately.
- **Plasma-aware critique:** experimental, theoretical and computational work is evaluated with domain-specific checks rather than a generic paper summary.
- **Hybrid retrieval:** lexical retrieval is available locally; vector retrieval can be added without changing the scientific data model.
- **No silent certainty:** disagreements, missing evidence, assumptions and speculative extrapolations are explicit.

## Initial architecture

1. Literature discovery (OpenAlex, arXiv, Crossref)
2. Canonicalization and deduplication (DOI/arXiv/OpenAlex IDs)
3. Scientific paper cards (regime, model, assumptions, equations, diagnostics, numerics, uncertainty, limitations)
4. Claim/evidence graph
5. Hybrid retrieval
6. Paper, Critic, Synthesizer and Frontier agents
7. Corpus refresh and evaluation

The first implementation is built in Python and uses SQLite/FTS5 as a transparent local memory baseline.
