# ADR 0001: Tree-First Retrieval

Status: Accepted as tree-first hybrid retrieval

## Context

Assignment 05 asks for codebase retrieval, and the PDF describes a conventional
chunk/embed/vector-DB approach. The project has a stronger argument for
structural retrieval over code: code already has an AST, imports, tests,
classes, and functions. To remove reviewer risk, the final implementation keeps
tree traversal primary while also adding a real chunk/embed/store/query fallback.

## Decision

Use a tree-first hybrid retrieval architecture:

1. Parse the target codebase into structural units.
2. Build a tree index from modules, classes, functions, imports, references, and tests.
3. Let the Navigator traverse this index through typed tools.
4. Measure recall against a grep baseline.
5. Chunk code units and markdown docs.
6. Embed code chunks with deterministic local code-semantic embeddings.
7. Store/query those chunks through a persisted SQLite vector database when
   structural ranking is weak, broad, or retry-driven.

## Consequences

Positive:

- Retrieval units map to code structure instead of arbitrary chunks.
- Context is easier for the generator to use.
- Tool traces are explainable in the deep-dive.
- The architecture is differentiated from generic RAG submissions.
- The repo still satisfies the PDF's chunk/embed/store requirement.

Negative:

- AST/import graph quality becomes critical.
- The vector fallback is local/reproducible, not a hosted vector database
  service.
- The hybrid path needs cache-version checks so old tree-only caches do not
  silently disable code chunk retrieval.

## Reversal Criteria

Revisit this ADR if:

1. Tree retrieval does not beat grep on multi-file recall queries.
2. Benchmark failures repeatedly trace to missing non-code context.
3. Evaluator feedback requires a hosted vector DB instead of the current local
   SQLite-backed vector store.
4. Dense embeddings materially outperform the local code-semantic fallback without
   increasing context noise.
