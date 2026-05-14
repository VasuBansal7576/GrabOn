# ARCHITECTURE.md — GrabOn Coder Agent

## System Shape

GrabOn Coder is a single-agent coding system over a pinned `httpx` checkout.

The high-level flow is:

1. build or load a cached codebase index
2. plan the task
3. retrieve code, tests, and conventions
4. generate a patch
5. verify it with three layers
6. retry up to five iterations or return failure/impossible

## Core Components

### Indexer

- `src/indexer/ast_parser.py`
- `src/indexer/tree_index.py`
- `src/indexer/vector_store.py`

The indexer extracts structural units from Python files, builds a module/unit
graph, links tests heuristically, chunks markdown docs, chunks code units, and
persists code chunks into a local SQLite vector database using deterministic
code-semantic embeddings.

### Retrieval

- `src/retrieval/tools.py`
- `src/retrieval/registry.py`
- `src/retrieval/navigator.py`

Retrieval is tree-first:

1. rank likely units structurally
2. inspect likely modules
3. fetch concrete functions/classes
4. follow reference/import edges
5. fetch tests
6. use vector fallback when ranking is weak or the task is broad

In live mode, the navigator can also ask a cheap model to rerank top structural
candidates for `Stage.CONTEXT_RANKING`.

### Agent Loop

- `src/agent/loop.py`
- `src/agent/generator.py`
- `src/agent/router.py`

The loop is explicit:

`PLAN -> ACT -> OBSERVE -> DECIDE`

Important behaviors:

- max 5 iterations
- budget stop
- Plan-phase impossible detection
- failure classification and retrieval-strategy adjustment
- retry-time refactoring stage in live mode after a failed attempt
- deterministic guard requiring behavioral source patches to include focused tests
- live-mode model hooks for planning, impossible detection, context ranking,
  error parsing, test analysis, generation, and review

### Verification

- `src/verification/static.py`
- `src/verification/test_runner.py`
- `src/verification/reviewer.py`

Three layers must all pass:

1. static analysis in a temp sandbox
2. pytest in a temp sandbox
3. deterministic or LLM review depending on mode

### Queue and Dashboard

- `src/queue/task_queue.py`
- `src/queue/dashboard.py`

The queue is still local-process oriented, but it now persists task snapshots to
disk so status/results survive restart. This is not a distributed job system,
but it is no longer purely memory-only.

## Routing

The router is stage-based.

Cheap-model stages:

- `context_ranking`
- `error_parsing`
- `test_analysis`
- `llm_review`

Stronger-model stages:

- `planning`
- `impossible_detect`
- `code_generation`
- `refactoring`

Current configured combos in code:

- `a`: Gemini Flash-Lite route via `GEMINI_MODEL`
- `b`: Haiku-class cheap stages + Sonnet-class heavy stages
- `groq`: small Groq model for cheap stages + larger Groq model for generation
- `nvidia`: NVIDIA hosted NIM route via `NVIDIA_MODEL`

Groq and NVIDIA are both supported live second-provider routes. Groq is the
preferred coding-provider route because it gives separate cheap and capable
models; NVIDIA remains useful for free-tier proof. The Mistral-small NIM route
and the Groq route both have green task-03 live coding artifacts. NVIDIA
Mistral also has a green task-08 multi-file live artifact; older NVIDIA/Groq
multi-file attempts remain preserved as failed regression history.

## Failure Recovery

The retry path is no longer a blind rerun.

When verification fails, the loop now:

1. classifies the failure into hints like `imports`, `typing`, `tests`, `logic`
2. extracts file hints from errors
3. optionally runs live test-analysis/error-parsing stages
4. expands preferred files
5. changes the next retrieval strategy
6. invokes the live `refactoring` stage on retry attempts before verification

That makes iteration meaningfully different from the previous attempt.

## Current Reality

- Offline benchmark path is strong and reproducible.
- Retrieval is hybrid now, not pure tree-only: tree traversal is primary, and a
  local SQLite vector database is fallback.
- Live provider support now has green Gemini + NVIDIA smoke evidence, green
  NVIDIA and Groq stage-smoke evidence, one real Gemini end-to-end coding smoke
  artifact, real NVIDIA plus Groq task-03 coding artifacts, and a real NVIDIA
  Mistral task-08 multi-file coding artifact.
- The deep multi-file story is now mixed rather than red: the current NVIDIA
  Mistral task-08 artifact passes in 2 iterations, while older NVIDIA Llama,
  older NVIDIA task-08, Groq task-08, and Gemini quota-limited task-08 attempts
  remain preserved as failed history instead of being counted as passes.
