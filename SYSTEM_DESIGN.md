# SYSTEM_DESIGN.md - GrabOn Coder Visual Architecture

This is the visual version of `ARCHITECTURE.md`. Use it in the Loom before
opening code so the reviewer understands the system shape in one screen.

## System Diagram

```mermaid
flowchart TB
    subgraph Input["1. Input"]
        CLI["CLI commands<br/>index, submit, eval, dashboard"]
        Queue["Task queue<br/>status, result, diff, cost"]
        Target["Pinned httpx checkout<br/>real OSS repo + real tests"]
    end

    subgraph Indexing["2. Indexing Layer"]
        Parser["Tree parser<br/>modules, classes, functions, imports"]
        Tree["Cached tree index<br/>units, references, test map, docs"]
        Vector["SQLite vector fallback<br/>code/doc chunks + local embeddings"]
    end

    subgraph Retrieval["3. Retrieval Layer"]
        Navigator["Tree-first navigator<br/>map -> module -> unit -> tests"]
        Tools["7 typed tools<br/>ls, get class/function, refs, imports, tests, examples"]
        Rerank["Cheap model rerank<br/>only when live mode needs it"]
    end

    subgraph Agent["4. Agent Loop"]
        Plan["PLAN<br/>target files, impossible check"]
        Generate["ACT<br/>generate patch"]
        Observe["OBSERVE<br/>verify result"]
        Decide{"DECIDE<br/>done or retry?"}
        Repair["Re-retrieve / repair<br/>max 5 iterations"]
    end

    subgraph Verification["5. Verification Gates"]
        Static["Static analysis<br/>ruff + mypy"]
        Pytest["Pytest sandbox<br/>apply patch in temp copy"]
        Review["Reviewer<br/>deterministic or live cheap model"]
    end

    subgraph Output["6. Evidence Output"]
        Diff["Unified diff<br/>source + tests"]
        Report["JSON report<br/>pass, cost, time, iterations"]
        Dashboard["Rich dashboard<br/>queue status + latest result"]
    end

    CLI --> Queue
    CLI --> Target
    Target --> Parser
    Parser --> Tree
    Parser --> Vector
    Queue --> Plan
    Tree --> Navigator
    Vector -.fallback when ranking is weak.-> Navigator
    Navigator --> Tools
    Tools --> Rerank
    Tools --> Generate
    Plan --> Navigator
    Plan --> Generate
    Generate --> Static
    Static --> Pytest
    Pytest --> Review
    Review --> Observe
    Observe --> Decide
    Decide -->|all gates pass| Diff
    Decide -->|all gates pass| Report
    Decide -->|needs repair| Repair
    Repair --> Navigator
    Queue --> Dashboard
    Report --> Dashboard

    classDef input fill:#243447,stroke:#7aa2f7,color:#e8f0ff;
    classDef index fill:#174c42,stroke:#5eead4,color:#ecfeff;
    classDef retrieval fill:#22543d,stroke:#86efac,color:#f0fff4;
    classDef agent fill:#3b2f63,stroke:#a78bfa,color:#f5f3ff;
    classDef verify fill:#633417,stroke:#fb923c,color:#fff7ed;
    classDef output fill:#365314,stroke:#a3e635,color:#f7fee7;

    class CLI,Queue,Target input;
    class Parser,Tree,Vector index;
    class Navigator,Tools,Rerank retrieval;
    class Plan,Generate,Observe,Decide,Repair agent;
    class Static,Pytest,Review verify;
    class Diff,Report,Dashboard output;
```

## One-Screen Explanation

The system is not just a chatbot over code. It is a coding-agent loop:

1. It indexes a real `httpx` checkout into structural code units.
2. It retrieves by module, symbol, imports, references, tests, and docs.
3. It uses vector search only as a fallback when structural ranking is weak.
4. It generates a patch.
5. It verifies the patch with static checks, pytest, and review.
6. It retries with better context or returns a clear failure.
7. It writes JSON reports with pass status, time, cost, iterations, and models.

## Why The Diagram Is Shaped This Way

For code edits, the unit of truth is usually not an arbitrary text chunk. It is
a function, class, import edge, test file, or convention. That is why the
control flow starts with a tree index and typed tools. The vector store exists,
but it is not the main driver. It is the fallback when the task is broad,
semantic, or under-specified.

## What To Point At In Loom

- Point at `Target -> Parser -> Tree`: "This is why it knows the codebase
  structure instead of blindly stuffing files into context."
- Point at `Vector`: "I still satisfy the chunk/embed/store requirement, but I
  use it as fallback, not the first source of truth."
- Point at `Navigator -> Tools`: "The retriever has inspectable actions:
  list module, get class, get function, find references, imports, tests."
- Point at `Static -> Pytest -> Review`: "Done means verified, not just
  generated."
- Point at `Report`: "Every run produces auditable evidence: pass/fail,
  iterations, time, provider models, and cost."

