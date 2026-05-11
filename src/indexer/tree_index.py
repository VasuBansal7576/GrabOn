"""GrabOn AI Coder — Tree Index Builder.

Builds hierarchical TreeIndex from ParsedUnits:
- modules: dict[file_path → ModuleNode]
- units: dict[unit_id → ParsedUnit]
- import_graph: dict[unit_id → list[unit_id]]
- test_map: dict[unit_id → test_file_path]

Serializes to JSON for caching. Loads from cache if codebase unchanged.
"""

from __future__ import annotations

# TODO: Implement tree index builder
# See Phase 2 in AGENTS.md for full specification
