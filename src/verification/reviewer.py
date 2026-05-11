"""GrabOn AI Coder — LLM-as-Reviewer.

Uses Haiku (NOT Sonnet, NOT Opus) to review generated code.
Checks: code style, security, logic bugs, imports, conventions.
Returns structured ReviewResult with pass/fail + specific issues.
"""

from __future__ import annotations

# TODO: Implement LLM reviewer
# See Phase 5 in AGENTS.md for full specification
