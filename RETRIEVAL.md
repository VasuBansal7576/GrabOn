# RETRIEVAL.md — Tree-First Hybrid Retrieval

## Retrieval Decision

Primary retrieval is structural.

The agent should first answer:

1. which module owns the behavior?
2. which function/class/method is the real edit point?
3. which imports, references, tests, and repo conventions constrain the patch?

Only after that does it use vector-style fallback.

This keeps the main code-edit path grounded in module/class/function/test
boundaries instead of flattening the codebase into anonymous text windows.

## Index Contents

`TreeIndex` currently stores:

- `modules`
- `units`
- `import_graph`
- `test_map`
- `doc_chunks`
- `code_chunks`
- `vector_store_path`
- `vector_store_kind`

The code chunks are embedded with `local-code-semantic-v1` and persisted into a
SQLite-backed local vector database, so the repo has a real
chunk/embed/store/query fallback path, not just in-memory similarity.

## Navigation Tools

Seven runtime tools are registered dynamically:

| Tool | Use |
|---|---|
| `ls_module(module_path)` | list classes/functions in a file |
| `get_function(unit_id)` | fetch a concrete function or method |
| `get_class(unit_id)` | fetch a class plus method signatures |
| `find_references(name)` | find units referencing a symbol |
| `get_imports(file_path)` | inspect import/imported-by edges |
| `get_tests_for(unit_id)` | fetch nearby tests and test source |
| `get_related_examples(query)` | unreliable pattern-finder with failure recovery |

## Navigator Behavior

The navigator flow is:

1. score units structurally
2. decide whether vector fallback is needed
3. optionally rerank top candidates with a cheap model in live mode
4. inspect likely modules with `ls_module`
5. inspect import edges with `get_imports`
6. fetch concrete units with `get_function` / `get_class`
7. fetch tests with `get_tests_for`
8. follow references with `find_references`
9. attach markdown doc chunks for repo conventions

The current navigator is still partly heuristic and includes a visible `httpx`
intent lexicon. That is deliberate prototype knowledge, not a claim of perfect
generality.

## Cache Strategy

- structural cache: `.cache/tree_index_{hash}.json`
- vector store: `.cache/tree_index_{hash}.sqlite3`

The hash covers `*.py` and `*.md` mtimes plus sizes in the target repo.

## Retrieval Eval

The retrieval suite now contains 18 labeled queries.

Latest local rerun:

| Method | Query Count | Avg Precision | Avg Recall | Wins |
|---|---:|---:|---:|---:|
| Tree navigator | 18 | 0.5741 | 0.8444 | 18/18 |
| Grep-style baseline | 18 | 0.1528 | 0.3185 | 0/18 |

This means the tree-first hybrid path still clearly beats the lexical baseline,
but the latest measured recall is lower than the older `0.95` number that was
previously committed in stale docs.

## Known Limits

- Reference edges are still heuristic and body-string based.
- Test mapping is still heuristic.
- The vector layer is local/reproducible; it is not an external hosted vector
  database service.
- The navigator is not fully general-purpose learned retrieval yet.
