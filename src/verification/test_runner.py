"""GrabOn AI Coder — Test Runner.

Runs pytest in subprocess against the codebase with generated code applied.
Steps: copy httpx to temp dir → apply patch → run pytest → parse JSON report → clean up.
CRITICAL: Always clean up temp dirs even on exception (try/finally).
"""

from __future__ import annotations

# TODO: Implement test runner
# See Phase 5 in AGENTS.md for full specification
