"""GrabOn AI Coder — Multi-Model Router + Cost Tracker.

Routes to the right model for each stage:
  CONTEXT_RANKING    → Haiku (cheap, fast)
  ERROR_PARSING      → Regex first, Haiku if ambiguous
  CODE_GENERATION    → Sonnet (real reasoning)
  REFACTORING        → Sonnet
  LLM_REVIEW         → Haiku
  IMPOSSIBLE_DETECT  → Sonnet

Tracks cost per call: model, stage, input_tokens, output_tokens, cost_usd, latency_ms.
CRITICAL: Never use Sonnet/Opus for error message parsing.
"""

from __future__ import annotations

# TODO: Implement multi-model router
# See Phase 4 in AGENTS.md for full specification
