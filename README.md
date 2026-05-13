# GrabOn AI Labs - The Coder

GrabOn Coder is a coding agent for a pinned `httpx==0.28.1` checkout. I chose
Assignment 05 because it exercises the full agent-engineering loop: retrieval,
generation, verification, repair, queueing, eval design, and cost discipline.
The agent takes a natural-language change request, retrieves code and
convention context, generates a patch, verifies the patch in temp sandboxes,
and either returns a passing result or explains why the task is impossible.

## What Is Built

- Cached structural index over the target repo: modules, classes, functions,
  methods, reference graph, test map, doc chunks, and code chunks.
- Seven typed retrieval tools with a runtime registry and one deliberately
  unreliable tool for recovery testing.
- Tree-first navigator with a persisted SQLite vector database for code-semantic
  chunks and chunked markdown retrieval for `README.md` and `docs/**/*.md`.
- Agent loop with planning, retrieval, generation, verification, retry, budget
  stop, and Plan-phase impossible-task detection.
- Three verification layers: `ruff` + `mypy`, `pytest` in a temp sandbox, and
  LLM review.
- Background task queue with on-disk snapshot persistence plus a live Rich
  dashboard.
- Benchmark runner, retrieval recall suite, and paired benchmark comparison
  reports.
- Provider adapters for Anthropic, Gemini, Groq, and NVIDIA's hosted
  OpenAI-compatible endpoint.

## Retrieval Design

The core idea is still "map first, search second."

For code edits, the primary job is to find the unit that owns the behavior,
follow imports/references/tests around it, and only fall back to vector-style
search when structural ranking is weak or the task is broad.

That means:

1. structural tree traversal is primary
2. persisted SQLite vector search over local code-semantic embeddings is fallback
3. chunked markdown retrieval covers repo conventions

This is no longer a pure tree-only story, but it is also not conventional
RAG-first retrieval. The implementation is a hybrid that keeps code structure in
the lead.

## Architecture Diagram

```mermaid
flowchart LR
    A["Task queue / CLI"] --> B["PLAN"]
    B --> C["Tree index + hybrid vector fallback"]
    C --> D["Typed retrieval tools"]
    D --> E["Patch generator"]
    E --> F["Static sandbox"]
    F --> G["Pytest sandbox"]
    G --> H["Reviewer"]
    H --> I{"All pass?"}
    I -->|yes| J["Done + diff + cost"]
    I -->|no| K["Failure classifier + re-retrieve"]
    K --> C
```

## Module Decisions

| Area | Decision | Tradeoff |
|---|---|---|
| Indexing | structural AST/tree index plus persisted chunk store | more explainable than repo-wide blobs; cache schema must stay fresh |
| Retrieval | typed tool traversal before vector fallback | tighter code grounding; more bespoke navigator logic |
| Generation | live model path plus explicit fixture templates | reproducible local regression path; fixture results must never be sold as live |
| Verification | static + pytest + reviewer gates | slower runs; much stronger false-positive control |
| Queue | local threadpool with disk snapshots | demo-friendly and restart-tolerant; not a distributed worker system |

## Latest Verified Results

Benchmark and retrieval numbers below were rerun locally on May 13, 2026.
Live provider smoke and Gemini live-coding evidence were refreshed on May 13,
2026.

### Benchmark

| Combo | Run Mode | Pass Rate | Impossible Detected | Avg Iterations | Avg Time | Cost |
|---|---|---:|---:|---:|---:|---:|
| A | fixture | 12/12 | yes | 1.0000 | 2.566s | $0.00 |
| B | fixture | 12/12 | yes | 1.0000 | 2.567s | $0.00 |

### Paired Comparison

`reports/comparison_a_vs_b_fixture.json` compares the two fixture benchmark
reports with paired sign-test p-values. In the latest rerun:

- pass rate delta: `0.0`
- iteration delta: `0.0`
- time delta: `0.000999s` in favor of combo `A`
- paired time p-value: `0.387695`

### Retrieval Recall

| Method | Query Count | Avg Precision | Avg Recall | Wins |
|---|---:|---:|---:|---:|
| Tree navigator | 18 | 0.5741 | 0.8444 | 18/18 |
| Grep-style baseline | 18 | 0.1528 | 0.3185 | 0/18 |

### Total Explicit Eval Coverage

- 12 benchmark tasks
- 18 labeled retrieval recall queries
- 30 total explicit eval cases

Raw artifacts live in `reports/`.

## Submission Evidence Matrix

This table is the source of truth for what the submitted repo claims. A green
row counts as supporting evidence. A red row is preserved failure evidence, not
a success claim.

| Requirement / Claim | Status | Evidence | What It Counts As |
|---|---|---|---|
| Real target repo with tests | GREEN | `target/httpx` setup plus index/test commands below | Assignment minimum bar |
| Retrieval beats simple search | GREEN | `reports/retrieval_recall.json` | 18-query recall comparison |
| Full offline benchmark harness | GREEN FIXTURE | `reports/combo_a_full.json`, `reports/combo_b_full.json` | Reproducible loop/scoring proof, not live model proof |
| Two live provider routes | GREEN SMOKE | `reports/provider_stage_smoke_nvidia_mistral.json`, `reports/provider_stage_smoke_groq.json` | Stage routing proof |
| Live Gemini coding run | GREEN LIVE | `reports/combo_a_live_smoke.json` | One end-to-end live coding task |
| Live NVIDIA coding run | GREEN LIVE | `reports/combo_nvidia_mistral_live_task03.json` | One end-to-end live coding task |
| Live Groq coding run | GREEN LIVE | `reports/combo_groq_live_task03.json` | One end-to-end live coding task with non-zero tracked cost |
| Live 3+ file stress task | RED PRESERVED | `reports/combo_groq_live_task08_multifile.json` and NVIDIA/Gemini task-08 attempts | Known remaining failure, not counted as pass |
| Cost tracking | GREEN STRUCTURAL | `reports/submission_cost_summary.json` plus per-task JSON cost fields | Per-run cost accounting; fixture cost is correctly `$0.00` |
| Vector DB wording from PDF | PARTIAL / HONEST | `src/indexer/vector_store.py`, `src/indexer/semantic_embeddings.py` | Local SQLite vector fallback, not hosted dense-vector RAG |

See `reports/README.md` for the full artifact-by-artifact label table.

## Quickstart

```bash
uv sync
git clone --depth 1 --branch 0.28.1 https://github.com/encode/httpx target/httpx
uv run python -m src index --path target/httpx
```

## Environment

| Variable | Required | Purpose |
|---|---:|---|
| `ANTHROPIC_API_KEY` | optional | Claude live routing |
| `GOOGLE_API_KEY` | optional | Gemini live routing |
| `GROQ_API_KEY` | optional | Groq live routing |
| `NVIDIA_API_KEY` | optional | NVIDIA hosted OpenAI-compatible routing |
| `GEMINI_MODEL` | optional | defaults to `gemini-2.5-flash-lite` |
| `NVIDIA_MODEL` | optional | defaults to `mistralai/mistral-small-4-119b-2603` |
| `NVIDIA_INPUT_COST_PER_1K` | optional | defaults to `0.0` for free-tier NIM accounting |
| `NVIDIA_OUTPUT_COST_PER_1K` | optional | defaults to `0.0` for free-tier NIM accounting |
| `TARGET_CODEBASE_PATH` | optional | defaults to `./target/httpx` |
| `COST_BUDGET_PER_TASK_USD` | optional | task halt budget |
| `MAX_ITERATIONS` | optional | defaults to `5` |
| `INDEX_CACHE_ENABLED` | optional | enable/disable persisted index cache |

## CLI

```bash
uv run python -m src index --path target/httpx
uv run python -m src submit "Add a timeout_seconds property to Request class" --path target/httpx
uv run python -m src eval --combo a --path target/httpx --output reports/combo_a_full.json
uv run python -m src eval --combo b --path target/httpx --output reports/combo_b_full.json
uv run python -m src eval --combo a --live --tasks task_03_url_copy_with_tests --path target/httpx --output reports/combo_a_live_task03.json
NVIDIA_MODEL='mistralai/mistral-small-4-119b-2603' uv run python -m src eval --combo nvidia --live --tasks task_03_url_copy_with_tests --path target/httpx --output reports/combo_nvidia_mistral_live_task03.json
uv run python -m src eval --combo groq --live --tasks task_03_url_copy_with_tests --path target/httpx --output reports/combo_groq_live_task03.json
uv run python -m src eval --combo a --live --limit 1 --path target/httpx --output reports/combo_a_live_smoke.json
uv run python -m src retrieval-eval --path target/httpx --output reports/retrieval_recall.json
uv run python -m src compare-eval --left reports/combo_a_full.json --right reports/combo_b_full.json --output reports/comparison_a_vs_b_fixture.json
uv run python -m src compare-eval --left reports/combo_a_live_task03.json --right reports/combo_nvidia_live_task03.json --output reports/comparison_a_vs_nvidia_live_task03.json
uv run python -m src provider-smoke --combos a,nvidia --output reports/provider_smoke_live.json
uv run python -m src provider-smoke --combos a,nvidia --stages planning,context_ranking,error_parsing,test_analysis,llm_review --output reports/provider_stage_smoke_live.json
NVIDIA_MODEL='mistralai/mistral-small-4-119b-2603' uv run python -m src provider-smoke --combos nvidia --stages planning,context_ranking,error_parsing,test_analysis,llm_review --output reports/provider_stage_smoke_nvidia_mistral.json
uv run python -m src provider-smoke --combos groq --stages planning,context_ranking,error_parsing,test_analysis,llm_review --output reports/provider_stage_smoke_groq.json
uv run python -m src cost-report --reports-dir reports --output reports/submission_cost_summary.json
uv run python -m src dashboard "Add a timeout_seconds property to Request class"
```

## Repo Guide

- `ARCHITECTURE.md`: agent loop, routing, verification, queue, and system shape.
- `RETRIEVAL.md`: index schema, navigation behavior, fallback search, and recall
  protocol.
- `EVAL.md`: benchmark tasks, retrieval eval corpus, and report formats.
- `reports/`: latest benchmark, retrieval, comparison, and live smoke outputs.
- `src/`: implementation.
- `tests/`: repo test suite.

## Verified Locally

```bash
uv run python -m pytest -q
uv run ruff check src tests
uv run mypy src --ignore-missing-imports
uv run python -m src index --path target/httpx
uv run python -m src retrieval-eval --path target/httpx --output reports/retrieval_recall.json
uv run python -m src eval --combo a --path target/httpx --output reports/combo_a_full.json
uv run python -m src eval --combo b --path target/httpx --output reports/combo_b_full.json
uv run python -m src eval --combo a --live --limit 1 --path target/httpx --output reports/combo_a_live_smoke.json
NVIDIA_MODEL='mistralai/mistral-small-4-119b-2603' uv run python -m src eval --combo nvidia --live --tasks task_03_url_copy_with_tests --path target/httpx --output reports/combo_nvidia_mistral_live_task03.json
uv run python -m src eval --combo groq --live --tasks task_03_url_copy_with_tests --path target/httpx --output reports/combo_groq_live_task03.json
uv run python -m src compare-eval --left reports/combo_a_full.json --right reports/combo_b_full.json --output reports/comparison_a_vs_b_fixture.json
uv run python -m src provider-smoke --combos a,nvidia --output reports/provider_smoke_live.json
uv run python -m src provider-smoke --combos a,nvidia --stages planning,context_ranking,error_parsing,test_analysis,llm_review --output reports/provider_stage_smoke_live.json
NVIDIA_MODEL='mistralai/mistral-small-4-119b-2603' uv run python -m src provider-smoke --combos nvidia --stages planning,context_ranking,error_parsing,test_analysis,llm_review --output reports/provider_stage_smoke_nvidia_mistral.json
uv run python -m src provider-smoke --combos groq --stages planning,context_ranking,error_parsing,test_analysis,llm_review --output reports/provider_stage_smoke_groq.json
uv run python -m src cost-report --reports-dir reports --output reports/submission_cost_summary.json
```

## Honest Limits

- The reproducible benchmark path is still `fixture` by default. The generator
  uses deterministic task templates unless `--live` is enabled.
- Live provider routing has green smoke evidence for Gemini + NVIDIA in
  `reports/provider_smoke_live.json`, and green NVIDIA stage-smoke evidence
  across planning, context ranking, error parsing, test analysis, and review in
  `reports/provider_stage_smoke_nvidia_mistral.json`.
- `reports/combo_a_live_smoke.json` is a real Gemini live coding run that passed
  retrieval, patch generation, static checks, pytest, and reviewer checks.
- `reports/combo_nvidia_mistral_live_task03.json` is a real NVIDIA NIM live
  coding run that passed retrieval, patch generation, static checks, pytest, and
  NVIDIA reviewer checks.
- `reports/combo_groq_live_task03.json` is a real Groq live coding run that
  passed retrieval, patch generation, static checks, pytest, and Groq reviewer
  checks with non-zero tracked cost.
- The preserved multi-file live attempts are still red:
  `reports/combo_nvidia_llama70b_live_task07_multifile.json` timed out during
  generation, `reports/combo_nvidia_llama70b_live_task08_multifile.json`
  exhausted 5 iterations with corrupt provider diffs, and
  `reports/combo_groq_live_task08_multifile.json` still fails on the
  `httpx/__init__.py` export patch. They are kept as raw evidence, not marketed
  as success. Each red JSON report now also has a top-level
  `submission_status` field so it cannot be mistaken for a green artifact.
- Live retry paths now call the `refactoring` model stage after a failed
  generation attempt, and deterministic review rejects behavioral source diffs
  that do not add or update focused tests.
- Cost tracking is implemented per stage and per task. Fixture benchmark costs
  are still `$0.00`, while live reports and `submission_cost_summary.json`
  separate measured live spend from fixture runs.
- The vector layer is a local SQLite vector database over deterministic
  code-semantic embeddings. It is intentionally local/reproducible rather than
  a hosted vector database service.
- Groq is the recommended replacement second live coding provider if a
  `GROQ_API_KEY` is available. The Groq route already separates cheap-stage and
  capable generation models; NVIDIA remains supported because it is currently
  configured in this workspace.

## Cost Data

The repo tracks per-stage and per-task cost in `TaskResult` plus benchmark JSON.
Fixture reports correctly show `$0.00` because they do not spend provider tokens.
Live reports should be used for submission cost claims, not fixture reports.

Current committed cost/evidence files:

- `reports/combo_a_full.json`
- `reports/combo_b_full.json`
- `reports/combo_a_live_smoke.json`
- `reports/combo_a_live_task03.json`
- `reports/combo_nvidia_live_task03.json`
- `reports/combo_nvidia_mistral_live_task03.json`
- `reports/combo_groq_live_task03.json`
- `reports/combo_groq_live_task08_multifile.json`
- `reports/provider_stage_smoke_nvidia_mistral.json`
- `reports/provider_stage_smoke_groq.json`
- `reports/comparison_a_vs_b_fixture.json`
- `reports/comparison_a_vs_nvidia_live_task03.json`
- `reports/comparison_a_vs_nvidia_mistral_live_task03.json`
- `reports/comparison_nvidia_vs_groq_live_task03.json`
- `reports/provider_smoke_live.json`
- `reports/provider_stage_smoke_live.json`
- `reports/submission_cost_summary.json`

## What Broke First

The hardest bug was cache drift after the hybrid retrieval layer was added.
Legacy JSON caches still loaded successfully, but they lacked `code_chunks` and
`vector_store_path`, so normal cached runs silently lost the new vector fallback.
The fix rejects stale hybrid-incomplete caches and rebuilds them before use; the
regression test now covers that upgrade path.

## What I Would Change With 2 More Weeks

1. Try stronger dense embeddings while keeping tree-first traversal.
2. Add a durable worker queue and richer run history storage.
3. Get a green second-provider end-to-end coding artifact. Groq is preferred if
   a key is available; NVIDIA remains the fallback provider.
4. Add a secrets-enabled CI workflow for optional live provider smoke runs.
5. Generalize navigator priors beyond the pinned `httpx` assignment target.
