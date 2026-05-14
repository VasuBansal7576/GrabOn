# LOOM_DEMO_GUIDE.md - What To Say And What To Run

Use this as the recording script. The goal is to make the project feel like a
working coding-agent system, not a vague RAG prototype.

## 0. The Core Pitch

"I built a coding agent for a real pinned `httpx` checkout. It takes a natural
language code-change task, retrieves the relevant code and tests, generates a
patch, verifies it in sandboxes with static checks and pytest, runs a reviewer,
and records cost, time, iterations, and provider models. The key design choice
is that retrieval is tree-first: code is structured, so I start from modules,
symbols, imports, references, and tests, then use vector search as fallback."

## 1. Why I Did Not Solve This As Traditional RAG

Traditional RAG is strong when the goal is answer synthesis from external
knowledge: split files into chunks, embed them, search a vector store, put the
top chunks in the prompt, and generate an answer. That is the right shape for
many knowledge-base and support-document systems.

This assignment is different. The output is not an answer. The output is a
patch that has to compile, pass tests, follow project conventions, and survive
multi-file interactions.

So I did not make vector similarity the control plane. I used:

- structural indexing for modules, classes, functions, imports, references,
  tests, docs, and code chunks
- typed retrieval tools so the agent can inspect exact code units
- vector fallback for broad or weakly ranked tasks
- an explicit generate-test-fix loop with max 5 iterations
- three verification gates before reporting success
- per-stage model routing and cost accounting

The short answer:

"I did not reject RAG. I narrowed it to where it helps. A plain RAG system can
retrieve plausible snippets, but a coding agent needs to know ownership,
dependencies, tests, and whether the patch actually works."

## 2. Research Basis For That Choice

| Source | What It Supports | How It Maps To This Repo |
|---|---|---|
| [Lewis et al., RAG, NeurIPS 2020](https://arxiv.org/abs/2005.11401) | RAG combines a generator with non-parametric retrieved memory, originally using a dense vector index for knowledge-intensive generation. | Good baseline idea for grounding, but the original target is knowledge generation, not patch verification. |
| [OpenAI Retrieval guide](https://platform.openai.com/docs/guides/retrieval) | Semantic search is powered by vector stores; files are chunked, embedded, and indexed. | This repo includes a chunk/embed/store/query path, but keeps it behind structural retrieval for code edits. |
| [Tree-sitter docs](https://tree-sitter.github.io/tree-sitter/) | Source code can be parsed into concrete syntax trees and updated efficiently. | This supports the decision to treat code as structured units instead of anonymous text chunks. |
| [RepoCoder paper](https://arxiv.org/abs/2303.12570) | Repository-level coding needs broader repo context and benefits from iterative retrieval-generation. | This repo follows an iterative retrieve -> generate -> verify -> repair shape instead of one-shot retrieval. |
| [SWE-bench paper](https://arxiv.org/abs/2310.06770) | Real software tasks require editing a codebase and often coordinating changes across functions, classes, and files with execution environments. | This justifies static checks, pytest, reviewer gates, and the task-08 multi-file live evidence. |

## 3. Demo Storyline

### Screen 1: Repo And Visual Architecture

Say:

"Before showing the terminal, this is the system design. Input comes from CLI or
queue, the repo is indexed structurally, retrieval uses typed tools, generation
runs through a loop, and success only happens after static analysis, pytest, and
review pass."

Open:

```bash
open SYSTEM_DESIGN.md
```

If recording through GitHub, open:

```bash
open https://github.com/VasuBansal7576/GrabOn/blob/main/SYSTEM_DESIGN.md
```

### Screen 2: Fresh Indexing Proof

Say:

"This is a real `httpx` checkout, not a toy project. The index builds modules,
units, imports, tests, docs, and vector fallback data."

Run:

```bash
cd /Users/vasu/Desktop/GrabOn
uv run python -m src index --path target/httpx
```

Expected proof to point at:

- number of modules indexed
- number of units indexed
- the command exits cleanly

### Screen 3: Retrieval Quality Evidence

Say:

"I measured retrieval separately, because if retrieval is weak, generation will
look smart but edit the wrong place. The tree-first path beats the grep-style
baseline on the labeled retrieval set."

Run:

```bash
jq '{query_count, avg_tree_precision, avg_tree_recall, avg_grep_precision, avg_grep_recall, tree_wins}' reports/retrieval_recall.json
```

Expected proof:

- `query_count`: 18
- `avg_tree_recall`: 0.8444
- `avg_grep_recall`: 0.3185
- `tree_wins`: 18

### Screen 4: Live Provider Routing Smoke

Say:

"The fixture benchmark is for reproducibility. For live proof, I call real
providers. This smoke checks that routed stages are actually hitting Groq."

Run:

```bash
uv run python -m src provider-smoke \
  --combos groq \
  --stages planning,context_ranking,error_parsing,test_analysis,llm_review \
  --output reports/loom_provider_stage_smoke_groq.json
```

Summarize:

```bash
jq '{successful_count, results: [.results[] | {stage, model, status, cost_usd, latency_ms}]}' reports/loom_provider_stage_smoke_groq.json
```

### Screen 5: Live Coding Run

Say:

"Now this is the main demo: live mode disables deterministic templates, calls
Groq for generation/review, retrieves context, creates tests, verifies, and
writes a report."

Run:

```bash
uv run python -m src eval \
  --combo groq \
  --live \
  --tasks task_03_url_copy_with_tests \
  --path target/httpx \
  --output reports/loom_groq_live_task03.json
```

While it runs, point at terminal events:

- `plan`: target files and strategy
- `act_retrieve`: selected units, tests, tool calls
- `act_generate`: generated diff
- `observe_verify`: static, pytest, reviewer result

Summarize:

```bash
jq '{combo, run_mode, provider_models, pass_rate, total_cost_usd, avg_time_seconds, tasks: [.tasks[] | {task_id, passed, iterations_used, static_passed, tests_passed, review_passed, cost_usd, failure_reason}]}' reports/loom_groq_live_task03.json
```

Expected proof:

- `run_mode`: `live`
- `provider_models`: Groq models
- `pass_rate`: `1/1`
- `static_passed`: true
- `tests_passed`: true
- `review_passed`: true
- non-zero cost

### Screen 6: Multi-File Stress Evidence

Say:

"I will not rerun the slow multi-file stress path in the short demo unless you
want to wait. I preserved the live artifact here. It passed task 08 in two
iterations with all three gates true."

Run:

```bash
jq '{submission_status, combo, run_mode, provider_models, pass_rate, avg_time_seconds, tasks: [.tasks[] | {task_id, passed, iterations_used, static_passed, tests_passed, review_passed, failure_reason}]}' reports/combo_nvidia_mistral_live_task08_multifile.json
```

Optional full rerun, API-key required and slower:

```bash
make live-stress LIVE_STRESS_COMBO=nvidia LIVE_STRESS_TASK=task_08_cache_transport
```

### Screen 7: Queue / Dashboard UI

Say:

"The queue is local, not distributed infrastructure, but it gives an evaluator
the expected workflow: submit, status, diff, verification, cost, and latency."

Run one of these:

```bash
uv run python -m src dashboard "Add a timeout_seconds property to Request class" --path target/httpx
```

For a live provider-backed dashboard task:

```bash
uv run python -m src dashboard \
  "Write pytest tests for URL.copy_with covering scheme, host, path, query params, and combined changes" \
  --combo groq \
  --live \
  --path target/httpx
```

## 4. What To Say If They Ask About Fixture Mode

"Fixture mode is an honest regression harness. It lets a fresh clone verify the
indexer, retrieval tools, patch application, verification gates, impossible-task
detection, cost fields, and report format without API keys. I do not count the
12/12 fixture result as 12 live model solves. The live evidence is separate and
named in `reports/`."

## 5. What To Say If They Ask About The Vector DB Requirement

"I did implement chunking, local embeddings, and SQLite vector storage. The
difference is control flow. Traditional RAG usually asks vector search to pick
top chunks first. I use vector search as fallback because code edits are usually
owned by symbols and tests. That lets the agent explain why it touched a file
and verify that the change actually works."

## 6. What To Show, In Order

1. `SYSTEM_DESIGN.md` visual diagram.
2. `README.md` requirement checklist.
3. `uv run python -m src index --path target/httpx`.
4. `reports/retrieval_recall.json` summary.
5. Groq provider smoke or existing `reports/provider_stage_smoke_groq.json`.
6. Groq live task-03 eval.
7. JSON summary proving live pass + static + pytest + review + cost.
8. Existing NVIDIA task-08 multi-file artifact.
9. Dashboard only if there is time.

## 7. What Not To Overclaim

- Do not say the fixture `12/12` is a live LLM benchmark.
- Do not say this is a distributed production queue.
- Do not say the vector layer is a hosted vector database.
- Do not hide failed live attempts. Say they are preserved as honest evidence
  and not counted as passes.
- Do not expose `.env` or API keys in the recording.

## 8. Closing Script

"The reason I chose this approach is that coding agents fail less from not
having enough random text and more from touching the wrong symbol or skipping
verification. So I built the system around a structural code map, typed
retrieval tools, a vector fallback, live model routing, and a strict verification
loop. The result is not just a generated answer. It is an auditable patch
workflow with costs, iterations, tests, and preserved evidence."

