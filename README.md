# ScientificBrain

ScientificBrain is a research-oriented scientific memory and reasoning system focused initially on plasma physics. It ingests scientific literature, preserves provenance, extracts claims and evidence, runs independent specialist criticism, rejects unsupported synthesis, and maintains a persistent `ResearchState`.

## Core principles

- **Evidence before fluency:** scientific claims must remain traceable to evidence and, when available, to section/page/equation/figure.
- **Provider-independent scientific state:** the research state and scientific memory do not belong to an LLM provider.
- **Online inference first:** the default inference path mirrors EDUAI's current cloud-provider strategy; local models are optional.
- **Independent criticism:** theory, experiment, simulation, adversarial and reproducibility reviewers are separated from the main extractor.
- **Hard evidence/provenance gates:** papers with unsupported claims or poor provenance are excluded from cross-paper synthesis.
- **No silent certainty:** missing information, uncertainty, contradictions, regime mismatch and speculation remain explicit.
- **Human-auditable state:** every research session persists its stage transitions, accepted papers, alternatives, reviewer verdict and audit log.

## 100-paper initial corpus

ScientificBrain v0 must perform deep analysis on **100 scientific papers**. Discovery can retrieve a much larger candidate set, but the first validated corpus is reduced to 100 non-duplicate, high-value papers using `config/corpus_policy.yaml`.

The corpus policy includes method, time and domain targets. `scientific-brain corpus-audit` verifies both the 100-paper target and the number of papers that have actually reached `full_text_reviewed`; metadata-only records do not count as deep analysis.

## Scientific workflow

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

The final writer is instructed to cite evidence IDs such as `[e12]`, not merely a paper title. The final reviewer can block the session if important statements cannot be traced to supplied evidence.

## Online inference: EDUAI-compatible routing

ScientificBrain 0.3 uses cloud inference by default. Its task router follows the same provider families and ordering variables used by EDUAI:

| Task | Default provider order |
| --- | --- |
| research | Google/Gemini -> Groq -> OpenRouter |
| text | Google/Gemini -> Vertex Model Cloud -> Groq -> OpenRouter -> Cerebras -> Together |
| structured | Google/Gemini -> Vertex Model Cloud -> Groq -> OpenRouter -> Cerebras -> Together |
| long context | Google/Gemini -> Vertex Model Cloud -> OpenRouter -> Groq -> Cerebras -> Together |
| retrieval | Google/Gemini |
| code | Google/Gemini -> Vertex Model Cloud -> Groq -> Cerebras -> OpenRouter -> Together |

Providers without credentials are skipped automatically. `vertex-model-cloud` remains reserved for compatibility with EDUAI and is skipped until its ScientificBrain endpoint implementation is explicitly enabled. API keys are never returned by `provider-status` or `/api/health`.

### Current model defaults inherited from EDUAI

- Google primary text: `gemini-3.6-flash`
- Google lightweight text: `gemini-3.5-flash-lite`
- Groq text: `llama-3.3-70b-versatile`
- Groq research: `groq/compound`
- OpenRouter text/structured: `openrouter/auto`
- Cerebras: `gpt-oss-120b`
- Together: `Qwen/Qwen3.5-9B`

All model IDs are environment-configurable; changing a model does not change ScientificBrain's memory schema.

## Vercel environment variables

Copy the variables you need from `.env.example` into **Vercel -> Project -> Environment Variables**. Do not commit real keys and do not use `NEXT_PUBLIC_` prefixes for provider secrets.

Recommended cloud-first configuration:

```env
SCIBRAIN_INFERENCE_MODE=cloud
SCIBRAIN_ENABLE_LOCAL_FALLBACK=false
SCIBRAIN_DEFAULT_TASK=research

GEMINI_API_KEY=
GOOGLE_TEXT_MODEL_PRIMARY=gemini-3.6-flash
GOOGLE_TEXT_MODEL_LITE=gemini-3.5-flash-lite

GROQ_API_KEY=
GROQ_TEXT_MODEL=llama-3.3-70b-versatile
GROQ_RESEARCH_MODEL=groq/compound

OPENROUTER_API_KEY=
OPENROUTER_TEXT_MODEL=openrouter/auto
OPENROUTER_STRUCTURED_MODEL=openrouter/auto
OPENROUTER_PROVIDER_SORT=price
OPENROUTER_ALLOW_DATA_COLLECTION=false
OPENROUTER_ZDR_ONLY=false
OPENROUTER_APP_TITLE=ScientificBrain

CEREBRAS_API_KEY=
CEREBRAS_TEXT_MODEL=gpt-oss-120b

TOGETHER_API_KEY=
TOGETHER_TEXT_MODEL=Qwen/Qwen3.5-9B

EDUAI_AI_PROVIDER_TIMEOUT_MS=60000
EDUAI_AI_PROVIDER_ORDER_RESEARCH=google,groq,openrouter
EDUAI_AI_PROVIDER_ORDER_TEXT=google,vertex-model-cloud,groq,openrouter,cerebras,together
EDUAI_AI_PROVIDER_ORDER_STRUCTURED=google,vertex-model-cloud,groq,openrouter,cerebras,together
EDUAI_AI_PROVIDER_ORDER_LONG_CONTEXT=google,vertex-model-cloud,openrouter,groq,cerebras,together
EDUAI_AI_PROVIDER_ORDER_RETRIEVAL=google
EDUAI_AI_PROVIDER_ORDER_CODE=google,vertex-model-cloud,groq,cerebras,openrouter,together
```

OpenRouter and Together also support `_1`, `_2`, `_3` API-key variables. ScientificBrain treats those as failover keys.

## Optional local inference

Local inference is no longer the default. To use Ollama explicitly:

```env
SCIBRAIN_INFERENCE_MODE=ollama
SCIBRAIN_OLLAMA_MODEL=qwen3:8b
SCIBRAIN_OLLAMA_URL=http://127.0.0.1:11434
```

To keep cloud inference primary and use Ollama only after all configured online providers fail:

```env
SCIBRAIN_INFERENCE_MODE=cloud
SCIBRAIN_ENABLE_LOCAL_FALLBACK=true
```

Do not configure `SCIBRAIN_OLLAMA_URL=http://127.0.0.1:11434` on Vercel unless a reachable remote Ollama service is intentionally exposed; Vercel cannot reach an Ollama server running on a user's personal computer through its own localhost.

## Safe deployment health check

Vercel can expose:

```text
/api/health
```

It reports the ScientificBrain version, active inference mode, provider order and which providers are configured, but never exposes API keys.

## CLI

Initialize memory:

```bash
scientific-brain init-db
```

Check provider routing safely:

```bash
scientific-brain provider-status --task research
```

Discover candidate literature:

```bash
scientific-brain discover --max-results 100
```

Audit the 100-paper corpus:

```bash
scientific-brain corpus-audit
```

Review one paper using the default cloud router:

```bash
scientific-brain review-paper 'doi:10.xxxx/example' paper.txt
```

Create a research session:

```bash
scientific-brain start-research \
  "What observables discriminate competing explanations of the measured plasma impulse?"
```

Run evidence-gated synthesis:

```bash
scientific-brain synthesize 'research:<session-id>'
```

## Scientific memory and Vercel

SQLite/FTS5 remains the transparent local development baseline. Vercel serverless storage must **not** be treated as the final durable ScientificBrain memory. The production web deployment should use a persistent database backend for papers, evidence, claims and `ResearchState`; this is intentionally separate from inference-provider configuration.

## Scientific gates

`evidence` is a hard gate: every extracted claim must reference evidence that exists in the same structured analysis.

`provenance` is a hard gate for synthesis: evidence must belong to the paper and at least 80% of evidence records must carry a source pointer such as section, page, equation or figure.

`reproducibility` is a coverage gate. Missing reporting lowers the score and is made explicit; it is not automatically interpreted as proof that the underlying paper is invalid.

## Development

```bash
python -m pytest -q
```

ScientificBrain 0.3 adds EDUAI-compatible cloud routing, model-specific task routing, optional local fallback, safe provider diagnostics and a Vercel health endpoint.
