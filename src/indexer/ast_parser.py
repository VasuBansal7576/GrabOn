"""GrabOn AI Coder — AST Parser using tree-sitter.

Parses every .py file in the target codebase and extracts structural units:
- Function definitions (name, signature, docstring, body, line range)
- Class definitions (name, bases, docstring, methods)
- Imports (module path, imported names)
- File-level docstrings

Output: ParsedUnit Pydantic models per function/class.
"""

from __future__ import annotations

# TODO: Implement tree-sitter parsing
# See Phase 2 in AGENTS.md for full specification
