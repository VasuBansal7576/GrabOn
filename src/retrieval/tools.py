"""GrabOn AI Coder — Retrieval Tools.

7 typed tools for navigating the tree index. All return Pydantic models.
All have 5-second timeout enforced via asyncio.wait_for.

Tools:
  1. ls_module     — List classes and functions in a module
  2. get_function  — Return full source of a function/method
  3. get_class     — Return class definition + method signatures
  4. find_references — Find all units referencing a name
  5. get_imports   — Return import graph for a file
  6. get_tests_for — Return test functions for a unit
  7. get_related_examples — Return related code examples (UNRELIABLE: fails 30%)
"""

from __future__ import annotations

# TODO: Implement 7 retrieval tools
# See Phase 3 in AGENTS.md for full specification
# Tool 7 (get_related_examples) must fail 30% of the time
