# AGENTS.md — GrabOn AI Labs | The Coder
# Codex Execution Instructions

## What You Are Building
A coding agent that takes a natural-language task, retrieves relevant context
from the httpx codebase using a tree-index (no vector DB, no embeddings),
generates code, runs 3-layer verification, and iterates up to 5 times.
If it cannot fix after 5 iterations, it explains why.

## Execution Order
Build in this exact sequence. Do not skip ahead.
Each phase must be complete and tested before moving to the next.

---

## PHASE 1 — Project Scaffolding

### 1.1 Dependencies
See `pyproject.toml` for full dependency list.

### 1.2 Environment Variables
See `.env.example` for all configuration.

### 1.3 Directory Structure
```
grabonai-coder/
├── AGENTS.md
├── ARCHITECTURE.md
├── RETRIEVAL.md
├── EVAL.md
├── README.md
├── pyproject.toml
├── .env.example
├── Makefile
├── src/
│   ├── __init__.py
│   ├── __main__.py              # CLI entry point (typer)
│   ├── config.py                # Pydantic Settings
│   ├── schemas.py               # All shared Pydantic models
│   ├── logging.py               # structlog + JSONL setup
│   ├── indexer/
│   │   ├── ast_parser.py        # tree-sitter parsing → structured units
│   │   ├── tree_index.py        # tree index builder + serializer
│   │   └── indexer.py           # main indexer entry point
│   ├── retrieval/
│   │   ├── tools.py             # 7 typed retrieval tools
│   │   ├── registry.py          # runtime tool discovery (not hardcoded)
│   │   └── navigator.py         # agent that traverses tree index via tools
│   ├── agent/
│   │   ├── loop.py              # Plan/Act/Observe/Decide loop
│   │   ├── generator.py         # code generation (Sonnet)
│   │   └── router.py            # multi-model router + cost tracker
│   ├── verification/
│   │   ├── static.py            # ruff + mypy runner
│   │   ├── test_runner.py       # pytest execution in subprocess
│   │   └── reviewer.py          # LLM-as-reviewer (Haiku)
│   ├── eval/
│   │   ├── benchmark.py         # runs all 12 tasks, produces report
│   │   ├── tasks.py             # 12 task definitions (see EVAL.md)
│   │   └── scorer.py            # pass/fail + iteration + cost scoring
│   └── queue/
│       ├── task_queue.py         # in-memory task queue
│       └── dashboard.py          # rich terminal UI
├── tests/                        # project tests
├── eval/tasks/                   # individual task YAML files
└── target/                       # httpx codebase (gitignored)
```

---

## PHASE 2 — Codebase Indexer

### `src/indexer/ast_parser.py`
Use tree-sitter to parse every `.py` file. Extract functions, classes, imports,
file-level docstrings. Output `ParsedUnit` Pydantic models (see `schemas.py`).

### `src/indexer/tree_index.py`
Build hierarchical `TreeIndex` from ParsedUnits. Serialize to JSON for caching.
If cache exists and codebase mtime unchanged, load from cache (Critical Rule 5).

### `src/indexer/indexer.py`
Entry point. Accepts codebase path, returns TreeIndex.
Rich progress bar: files parsed, units found, import edges built.

---

## PHASE 3 — Retrieval Tools

### `src/retrieval/registry.py`
Runtime tool registry. Tools discovered dynamically, not hardcoded imports.

### `src/retrieval/tools.py`
7 typed tools, each returning Pydantic models with 5s timeout:
1. `ls_module` — list classes/functions in a module
2. `get_function` — return full source of a function/method
3. `get_class` — return class definition + method signatures
4. `find_references` — find all units referencing a name
5. `get_imports` — return import graph for a file
6. `get_tests_for` — return test functions for a unit
7. `get_related_examples` — return related code examples (**UNRELIABLE: fails 30%**)

### `src/retrieval/navigator.py`
Navigator agent (Haiku) calls tools iteratively (max 8 calls) to build context.
Follows import chains. Logs every tool call with latency.

---

## PHASE 4 — Agent Loop

### `src/agent/router.py`
Multi-model router. Routes by stage (see ARCHITECTURE.md for routing table).
Cost tracker records per call: model, stage, tokens, cost_usd, latency.

### `src/agent/loop.py`
Core loop: PLAN → ACT → OBSERVE → DECIDE. Max 5 iterations.
Every phase logged to structured JSONL via `log_phase()`.

### `src/agent/generator.py`
Code generator (Sonnet). Includes httpx conventions in system prompt.
On iteration > 0: previous errors. On iteration > 2: full error history.

---

## PHASE 5 — Verification

### `src/verification/static.py`
ruff + mypy in temp directory. Parse output with regex, NOT LLM (Critical Rule 1).

### `src/verification/test_runner.py`
pytest in subprocess. Copy httpx to temp dir → apply patch → run → clean up.
CRITICAL: Always clean up temp dirs in try/finally (Critical Rule 3).

### `src/verification/reviewer.py`
LLM-as-reviewer (Haiku only). Checks style, security, logic, imports.

---

## PHASE 6 — Task Queue + Dashboard

### `src/queue/task_queue.py`
In-memory queue. submit → get_status → list_tasks → get_result.

### `src/queue/dashboard.py`
Rich terminal UI. Status badges, iteration count, live cost, verification status.

---

## PHASE 7 — Eval Benchmark

12 tasks (see EVAL.md): 3 easy, 3 medium, 3 hard, 1 impossible, 2 special.
Two model combos: A (Gemini Flash baseline) vs B (Haiku + Sonnet optimal).

---

## PHASE 8 — CLI Entry Points

```bash
python -m src index --path ./target/httpx
python -m src submit "Add a timeout_seconds property to Request class"
python -m src eval --combo a
python -m src eval --combo b
python -m src dashboard
```

---

## Failure Recovery Strategies

Three distinct strategies selected by error type:

1. **Retry with backoff** — For transient errors (rate limits, tool timeouts).
   Uses exponential backoff via tenacity. Max 3 retries.

2. **Re-plan with alternative tools** — For persistent errors (tool failure,
   blocked API). Navigator re-plans retrieval using different tools.
   The unreliable tool (get_related_examples) triggers this path.

3. **Graceful degradation** — When budget/time exceeded or max failures hit.
   Return partial results with clear report of what completed vs remaining.

---

## Critical Rules (Do Not Violate)

1. NEVER use Sonnet/Opus for error message parsing. Regex first, Haiku if ambiguous.
2. NEVER run generated code outside a temp directory sandbox.
3. ALWAYS clean up temp directories in try/finally blocks.
4. ALWAYS track cost per call, per stage, per task.
5. NEVER re-index if cache exists and codebase mtime unchanged.
6. Log every agent decision in structured JSONL. No print statements in core logic.
7. All inter-module data must be Pydantic models. No raw dicts between phases.
8. The impossible task (task 10) must be detected in PLAN phase, not after failed iterations.

---

## Build Order
Phase 2 (Indexer) → Phase 3 (Tools) → Phase 4 (Loop with mocked verification) →
Phase 5 (Verification) → Phase 6 (Queue + Dashboard) → Phase 7 (Eval) → Phase 8 (CLI).