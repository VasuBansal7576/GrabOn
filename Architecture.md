# ARCHITECTURE.md — GrabOn Coder Agent

## What This Is

A single-agent coding system with tree-index retrieval, iterative repair,
and multi-model routing. The retrieval is the differentiator.
Everything else (loop, verification, routing) follows directly from it.

---

## Why This Retrieval, Not Vector RAG

Three independent pieces of evidence converge on the same conclusion:

**1. The unit problem (Blockify, 2025)**
Chunked text is structurally agnostic. It has no idea boundary, version context,
or semantic completeness. For code specifically: a chunk that bisects a function
body is useless. The embedding represents noise, not meaning.
Fix: embed structural units (functions, classes), not text windows.

**2. The density problem (Onyx EnterpriseRAG-Bench, 2026)**
Vector search accuracy drops from 90.7% at 5K docs to 50.6% at 500K docs.
Root cause: neighborhood density in embedding space. Related documents
cluster together, pushing the correct answer out of top-k.
Even at codebase scale (50 files, 500+ functions), utility functions,
auth helpers, and transport methods cluster identically. The correct function
gets displaced by topically similar but wrong ones.

**3. The tree approach (PageIndex, 2026)**
No vector DB. No chunking. No embeddings. Build a tree index and let the LLM
reason through it like a human reading a codebase. Hit 98.7% on financebench,
beating every vector RAG on the leaderboard.
For code: the AST IS a tree. Module → Class → Function → Test.
The index structure is free — tree-sitter gives it to us.

**Conclusion:** Tree index + reasoning traversal via tools.
The retrieval is structural, not probabilistic.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CLI / Task Queue                      │
│         submit task → get status → view result           │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                   Agent Loop                             │
│         PLAN → ACT → OBSERVE → DECIDE                   │
│         (max 5 iterations, JSONL logging)                │
└──────┬──────────────┬──────────────────┬────────────────┘
       │              │                  │
┌──────▼──────┐ ┌─────▼──────┐ ┌────────▼───────┐
│  Navigator  │ │ Generator  │ │  Verification  │
│  (Haiku)    │ │  (Sonnet)  │ │   3 Layers     │
│             │ │            │ │                │
│ Calls tools │ │ Generates  │ │ 1. ruff+mypy   │
│ to traverse │ │ code that  │ │ 2. pytest      │
│ tree index  │ │ fits repo  │ │ 3. LLM review  │
└──────┬──────┘ └────────────┘ └────────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│                    Tree Index                            │
│   module → class → function → test mapping              │
│   Built once from tree-sitter AST, cached as JSON       │
└──────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│                 httpx codebase                           │
│   Real library, 50+ files, full pytest test suite        │
└──────────────────────────────────────────────────────────┘
```

---

## Multi-Model Routing

Every model choice is a deliberate decision, not a default.

| Stage | Model | Why |
|-------|-------|-----|
| Context ranking | Haiku | Low-stakes ranking, cheap, fast |
| Error parsing | Regex first, Haiku if ambiguous | ruff/mypy output is deterministic |
| Code generation | Sonnet | Needs real reasoning, context-awareness |
| Refactoring | Sonnet | Same as generation |
| LLM-as-reviewer | Haiku | Pattern matching against known conventions |
| Impossible detection | Sonnet | Needs to reason about architectural constraints |
| Benchmark baseline | Gemini Flash | Free, fast, second provider |

**Red line:** Opus is not in this system. Opus-for-error-parsing is a cost bug.
The CLAUDE.md Rule 5 principle: if deterministic code can answer it, deterministic code answers it.

### Cost per task estimate (Combo B: Haiku + Sonnet)
- Retrieval (Haiku, ~2K tokens): ~$0.001
- Generation (Sonnet, ~4K tokens): ~$0.012
- Verification (ruff + mypy + pytest): $0.000
- Review (Haiku, ~1K tokens): ~$0.0005
- Per iteration total: ~$0.014
- Worst case (5 iterations): ~$0.07
- Budget ceiling: $0.50 per task (7x headroom)

---

## Agent Loop Detail

```
PLAN phase (Sonnet):
  - Understand the task
  - Identify which modules are likely involved
  - Detect if task is impossible (contradicts existing architecture)
  - Output: plan with target files + retrieval strategy

ACT phase (Navigator + Generator):
  - Navigator (Haiku) calls tools to build context
  - Generator (Sonnet) writes code given context + plan + prior errors
  - Tools called: ls_module, get_function, get_class, find_references,
                  get_imports, get_tests_for
  - Max 8 tool calls per retrieval pass

OBSERVE phase (Verification):
  - Layer 1: ruff + mypy on generated code (deterministic, <5s)
  - Layer 2: pytest on patched codebase in temp dir (<60s)
  - Layer 3: Haiku reviews against httpx conventions
  - All three must pass. First failure stops the chain.

DECIDE phase (Sonnet):
  - If all 3 layers pass: DONE
  - If layer 1 fails: re-generate with specific lint/type errors
  - If layer 2 fails: retrieve more context (specifically test files)
  - If layer 3 fails: re-generate with convention feedback
  - If iteration == 4 (last): decide DONE or REPORT_FAILURE
  - Output: decision enum + next retrieval hint
```

---

## Retrieval Detail

```
Tree Index structure:
{
  "modules": {
    "httpx/_client.py": {
      "classes": ["Client", "AsyncClient"],
      "functions": ["_merge_cookies", "_build_auth"]
    }
  },
  "units": {
    "httpx._client.Client.send": {
      "signature": "def send(self, request: Request, ...) -> Response",
      "body": "...",
      "imports": ["httpx._transports.base.BaseTransport", ...],
      "test_file": "tests/test_client.py",
      "line_start": 847,
      "line_end": 923
    }
  },
  "import_graph": {
    "httpx._client.Client.send": [
      "httpx._transports.base.BaseTransport.handle_request",
      "httpx._models.Response"
    ]
  },
  "test_map": {
    "httpx._client.Client.send": "tests/test_client.py::test_send"
  }
}
```

Navigator traversal for multi-file task:
1. Start with task description → identify entry point function
2. ls_module on likely file
3. get_function on entry point
4. follow import_graph edges (1 level deep)
5. get_tests_for to understand expected behavior
6. Stop when context is sufficient or 8 tool calls hit

---

## Recall Measurement (10 queries)

After indexing, run 10 fixed retrieval queries and measure:
- Precision: fraction of retrieved units that are relevant
- Recall: fraction of relevant units that were retrieved

Compare against naive baseline (grep-based, no tree structure).
Report in README. Tree index must outperform grep on multi-file tasks.

10 fixed queries:
1. "how does Client handle authentication"
2. "where is timeout enforced during request"
3. "how are redirects followed"
4. "where is the connection pool managed"
5. "how does async client differ from sync client"
6. "where are cookies stored and applied"
7. "how is the base URL resolved"
8. "where does response streaming happen"
9. "how are SSL certificates verified"
10. "where is request encoding handled"

---

## Failure Modes and Handling

| Failure | Detection | Response |
|---------|-----------|----------|
| Lint error (ruff) | Regex parse ruff output | Re-generate with specific error |
| Type error (mypy) | Regex parse mypy output | Re-generate + fetch type stubs |
| Test failure | pytest JSON report | Re-retrieve test file + dependencies |
| Review rejection | Haiku structured output | Re-generate with convention notes |
| Tool timeout (>5s) | asyncio.wait_for | Return empty result, log warning |
| Impossible task | Sonnet PLAN phase | Return TaskResult.impossible immediately |
| Budget exceeded | Cost tracker check | Halt + report cost so far |
| 5 iterations exhausted | Loop counter | Report all errors across iterations |

---

## Impossible Task Detection

Task 10: "Make all requests synchronous"
This contradicts httpx's async architecture at the transport layer.

Detection happens in PLAN phase (Sonnet), not after failed iterations.
System prompt for PLAN: "Before planning implementation, check if this task
contradicts the existing architecture. If yes, explain why it cannot be done
without a full rewrite and return IMPOSSIBLE."

Sonnet should identify:
- AsyncClient uses asyncio event loop at transport level
- Cannot make async transport sync without replacing entire transport layer
- Existing tests assume async behavior
- Return: IMPOSSIBLE + specific architectural reason

This is the stress-test answer: "submit an impossible task, does the agent detect it?"
Yes. In the PLAN phase. Before spending a single token on generation.

---

## What The Eval Report Contains

For each of 10 tasks:
```json
{
  "task_id": "task_04",
  "description": "Add retry_on_timeout to AsyncClient",
  "difficulty": "medium",
  "combo_a": {
    "model": "gemini-flash",
    "passed": true,
    "iterations": 3,
    "cost_usd": 0.008,
    "time_seconds": 47.2,
    "static_passed": true,
    "tests_passed": true,
    "review_passed": true
  },
  "combo_b": {
    "models": "haiku+sonnet",
    "passed": true,
    "iterations": 2,
    "cost_usd": 0.019,
    "time_seconds": 31.4,
    "static_passed": true,
    "tests_passed": true,
    "review_passed": true
  }
}
```

Aggregate:
```json
{
  "combo_a_pass_rate": "7/10",
  "combo_b_pass_rate": "8/10",
  "combo_a_avg_cost": 0.006,
  "combo_b_avg_cost": 0.021,
  "combo_a_avg_iterations": 2.8,
  "combo_b_avg_iterations": 1.9,
  "verdict": "Combo B costs 3.5x more but uses fewer iterations and passes 1 more hard task"
}
```