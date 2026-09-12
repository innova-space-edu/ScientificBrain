# ScientificBrain

ScientificBrain is a research-oriented scientific memory and reasoning system focused initially on plasma physics. It is designed to ingest literature, preserve provenance, extract claims and evidence, run independent specialist criticism, reject unsupported synthesis, and maintain a persistent local `ResearchState`.

## Core principles

- **Evidence before fluency:** scientific claims must remain traceable to evidence and, when available, to section/page/equation/figure.
- **Local-first scientific memory:** SQLite/FTS5 stores literature, evidence, claims, reviews, gates and research states independently of the selected LLM.
- **Provider-independent reasoning:** the same memory can be used with a local Ollama model or an OpenAI-compatible cloud endpoint.
- **Independent criticism:** theory, experiment, simulation, adversarial and reproducibility reviewers are separated from the main paper extractor.
- **Hard evidence/provenance gates:** papers with unsupported claims or poor provenance are excluded from cross-paper synthesis.
- **No silent certainty:** missing information, uncertainty, contradictions, regime mismatch and speculation remain explicit.
- **Human-auditable state:** every research session persists its stage transitions, accepted papers, alternatives, reviewer verdict and audit log.

## 100-paper initial corpus

ScientificBrain v0 must perform deep analysis on **100 scientific papers**. Literature discovery can retrieve a much larger candidate set, but the first validated corpus is reduced to 100 non-duplicate, high-value papers using `config/corpus_policy.yaml`.

The corpus policy includes method, time and domain targets. `scientific-brain corpus-audit` verifies both the 100-paper target and the number of papers that have actually reached `full_text_reviewed`; metadata-only records do not count as deep analysis.

## Implemented workflow

```text
Sources / papers / data
        |
        v
   Local ingestion
        |
        v
 ScientificMemory
        |
        v
   ResearchState
        |
        +------------------------------+
        |                              |
        v                              v
  Paper extraction              local retrieval
        |
        v
 General Critic
        |
        +--> Theory reviewer
        +--> Experiment reviewer
        +--> Simulation reviewer
        +--> Adversarial reviewer
        +--> Reproducibility reviewer
        |
        v
 Evidence + provenance + reproducibility gates
        |
        v
 Cross-paper synthesis
        |
        v
 Alternative explanations
        |
        v
 Cross-paper adversarial audit
        |
        v
 Reproducibility audit
        |
        v
 Evidence-linked writer
        |
        v
 Final reviewer
        |
    PASS / BLOCKED
```

The final writer is instructed to cite evidence IDs such as `[e12]`, not merely a paper title. The final reviewer can block the session if important statements cannot be traced to the supplied evidence.

## Memory layers in v0

SQLite stores:

- canonical papers and bibliographic metadata;
- FTS5 lexical index;
- evidence records with source pointers;
- claims and claim relations;
- full structured paper analyses;
- general critiques;
- specialist reviews by role;
- review depth (`metadata_verified`, `abstract_reviewed`, `full_text_reviewed`);
- persistent research states and stage audit logs;
- gate executions and scores.

The database stays local by default. Switching models does not replace or erase the scientific memory.

## LLM providers

### Local Ollama

```bash
export SCIBRAIN_OLLAMA_MODEL=qwen3:8b
export SCIBRAIN_OLLAMA_URL=http://127.0.0.1:11434
```

The default provider is `ollama`.

### OpenAI-compatible endpoint

```bash
export SCIBRAIN_API_BASE=https://provider.example/v1
export SCIBRAIN_MODEL=model-name
export SCIBRAIN_API_KEY=...
```

Then use `--provider openai-compatible`.

## CLI

Initialize local memory:

```bash
scientific-brain init-db
```

Discover candidate literature:

```bash
scientific-brain discover --max-results 100
```

Audit the 100-paper corpus:

```bash
scientific-brain corpus-audit
```

Review one paper after its text has been extracted to a UTF-8 file:

```bash
scientific-brain review-paper 'doi:10.xxxx/example' paper.txt --provider ollama
```

Create a persistent research session using local retrieval:

```bash
scientific-brain start-research \
  "What observables discriminate competing explanations of the measured plasma impulse?"
```

Run evidence-gated synthesis:

```bash
scientific-brain synthesize 'research:<session-id>' --provider ollama
```

## Scientific gate behavior

`evidence` is a hard gate: every extracted claim must reference evidence that exists in the same structured analysis.

`provenance` is a hard gate for synthesis: evidence must belong to the paper and at least 80% of evidence records must carry a source pointer such as section, page, equation or figure.

`reproducibility` is a coverage gate. Missing reporting lowers the score and is made explicit; it is not automatically interpreted as proof that the underlying paper is invalid.

## Development

```bash
python -m pytest -q
```

Current v0.2 implementation tests local memory round-trips, evidence/provenance gates, method-aware reproducibility checks and corpus auditing.
