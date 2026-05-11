"""GrabOn AI Coder — Navigator Agent.

The navigator is an agent (Haiku) that decides which tools to call
to build context for a given task.

Input: natural language task + TreeIndex
Output: assembled context (list of ParsedUnits relevant to the task)

Max 8 tool calls per retrieval pass. Follows import chains.
Logs every tool call: tool name, input, output size, latency.
"""

from __future__ import annotations

# TODO: Implement navigator agent
# See Phase 3 in AGENTS.md for full specification
