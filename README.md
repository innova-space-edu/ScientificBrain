# ScientificBrain

ScientificBrain is a research-oriented scientific memory and reasoning system focused initially on plasma physics. It is designed to ingest literature, preserve provenance, retrieve evidence, critique experiments/theory/simulations, detect contradictions, and generate evidence-bounded research hypotheses.

## Core principles

- **Evidence before fluency:** every scientific claim should remain traceable to a source and, when possible, to a passage/equation/figure context.
- **Layered memory:** bibliographic, semantic, evidence, episodic and frontier/open-question memory are stored separately.
- **Plasma-aware critique:** experimental, theoretical and computational work is evaluated with domain-specific checks rather than a generic paper summary.
- **Hybrid retrieval:** lexical retrieval is available locally; vector retrieval can be added without changing the scientific data model.
- **No silent certainty:** disagreements, missing evidence, assumptions and speculative extrapolations are explicit.

## 100-paper initial corpus

ScientificBrain v0 must perform deep analysis on **100 scientific papers**. Literature discovery can retrieve a much larger candidate set, but the first validated corpus is reduced to 100 non-duplicate, high-value papers using the policy in `config/corpus_policy.yaml`.

The corpus must not be dominated by one subfield or one type of evidence. It intentionally combines experimental work, theory, simulations, reviews/roadmaps, foundational papers and recent work. Each selected paper is expected to receive a structured paper card, claim/evidence extraction and plasma-aware criticism before it is treated as part of the trusted scientific memory.

## Initial architecture

1. Literature discovery (OpenAlex, arXiv, Crossref)
2. Canonicalization and deduplication (DOI/arXiv/OpenAlex IDs)
3. Selection of the 100-paper validated corpus
4. Scientific paper cards (regime, model, assumptions, equations, diagnostics, numerics, uncertainty, limitations)
5. Claim/evidence graph
6. Hybrid retrieval
7. Paper, Critic, Synthesizer and Frontier agents
8. Corpus refresh and evaluation

The first implementation is built in Python and uses SQLite/FTS5 as a transparent local memory baseline.
