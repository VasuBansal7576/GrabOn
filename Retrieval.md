# RETRIEVAL.md — Tree Index Design

## Tree Index Schema

```
TreeIndex
├── modules: dict[file_path → ModuleNode]
│   └── ModuleNode
│       ├── file_path, docstring, imports
│       ├── classes: list[str]       # class unit_ids
│       └── functions: list[str]     # function unit_ids
│
├── units: dict[unit_id → ParsedUnit]
│   └── ParsedUnit (see src/schemas.py for full definition)
│
├── import_graph: dict[unit_id → list[unit_id]]
│   # directed graph: A → B means A's body references B
│
└── test_map: dict[unit_id → list[str]]
    # unit_id → list of test function names
```

## Navigation Tools

7 tools. Each returns a Pydantic model. All have 5s timeout.
Registered in `src/retrieval/registry.py` at runtime.

| # | Tool | Use When |
|---|------|----------|
| 1 | `ls_module(module_path)` | Know the file but not the function |
| 2 | `get_function(unit_id)` | Know exactly what you need |
| 3 | `get_class(unit_id)` | Understand class structure before drilling in |
| 4 | `find_references(name)` | Find where a function is called |
| 5 | `get_imports(file_path)` | Understand dependency direction |
| 6 | `get_tests_for(unit_id)` | Understand expected behavior |
| 7 | `get_related_examples(query)` | Find similar patterns (**unreliable, 30% failure rate**) |

## Navigator Traversal Algorithm

```
Input: task description + TreeIndex
Output: list[ParsedUnit] — context for generator

Step 1: PLAN (Haiku) → identify likely entry points
Step 2: TRAVERSE (tool loop, max 8 calls)
  → ls_module on entry point files
  → get_function on specific functions
  → follow import_graph 1 level deep
  → get_tests_for on entry points
  → Stop when context sufficient OR 8 calls used
Step 3: ASSEMBLE → deduplicate, sort by relevance, return
```

## Cache Strategy

- Cache path: `.cache/tree_index_{codebase_hash}.json`
- Hash: SHA256 of all `.py` file mtimes concatenated
- Match → load from cache (skip parsing)
- Mismatch → rebuild and update cache
- Rebuild time for httpx: ~15-30 seconds

## Recall Measurement

10 fixed queries after indexing (defined in ARCHITECTURE.md).
Precision = retrieved ∩ relevant / retrieved.
Recall = retrieved ∩ relevant / relevant.
Target: recall > 0.8 on all 10 queries.
Compare against grep baseline. Tree must outperform on multi-file queries.