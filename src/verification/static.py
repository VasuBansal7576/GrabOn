"""GrabOn AI Coder — Static Analysis Runner.

Runs ruff + mypy on generated code in a temp directory.
Parses output deterministically with regex (no LLM).
Uses subprocess with timeout=30s.
CRITICAL: Never allow generated code to run outside sandbox.
"""

from __future__ import annotations

# TODO: Implement static analysis runner
# See Phase 5 in AGENTS.md for full specification
