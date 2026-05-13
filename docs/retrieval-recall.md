# Retrieval Recall Report

Command:

```bash
LOG_LEVEL=ERROR python3 -m src retrieval-eval --path target/httpx --output eval/results/retrieval_recall.json
```

Aggregate result:

| Method | Avg Precision | Avg Recall | Wins |
|---|---:|---:|---:|
| Tree index navigator | 0.5250 | 0.9500 | 10/10 |
| Grep-style baseline | 0.1250 | 0.2367 | 0/10 |

Per-query result:

| Query | Tree Precision | Tree Recall | Grep Precision | Grep Recall |
|---|---:|---:|---:|---:|
| How does Client send a request? | 0.5000 | 1.0000 | 0.2500 | 0.5000 |
| Where are request headers merged? | 0.2500 | 1.0000 | 0.0000 | 0.0000 |
| Where is timeout configuration normalized? | 0.5000 | 1.0000 | 0.3750 | 0.7500 |
| Where are response status helpers defined? | 0.7500 | 1.0000 | 0.1250 | 0.1667 |
| Where are event hooks called? | 0.3750 | 1.0000 | 0.1250 | 0.3333 |
| Where are sync and async clients different? | 0.5000 | 0.6667 | 0.0000 | 0.0000 |
| Where is response content read and decoded? | 0.6250 | 1.0000 | 0.1250 | 0.2000 |
| Where are transport abstractions defined? | 0.5000 | 1.0000 | 0.1250 | 0.2500 |
| Where are auth flows implemented? | 0.6250 | 0.8333 | 0.1250 | 0.1667 |
| Where are URL mutation helpers defined? | 0.6250 | 1.0000 | 0.0000 | 0.0000 |

Interpretation:

- The tree navigator beats the grep-style baseline on all 10 manually labeled
  `httpx` queries.
- The navigator combines structural scoring with a small explicit `httpx`
  intent lexicon documented in `RETRIEVAL.md`; the result is transparent
  prototype tuning, not an untuned universal benchmark.
- The lowest tree recall is the sync-versus-async comparison query. Under the
  top-8 unit budget it retrieves concrete send and transport methods before both
  base transport classes, so the result is useful but not fully exhaustive.
- These numbers justify tree-first retrieval for this assignment. They are a
  bounded local benchmark, not a broad claim about every codebase.
