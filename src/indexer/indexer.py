"""Public indexer entry point."""

from __future__ import annotations

from pathlib import Path

from rich.progress import track

from src.indexer.tree_index import build_tree_index
from src.schemas import TreeIndex


def index_codebase(codebase_path: str | Path, use_cache: bool = True) -> TreeIndex:
    """Index a codebase and return a tree index."""
    path = Path(codebase_path)
    if not path.exists():
        raise FileNotFoundError(f"Target codebase does not exist: {path}")
    return build_tree_index(path, use_cache=use_cache)


def count_python_files(codebase_path: str | Path) -> int:
    """Count Python files for progress/UI reporting."""
    root = Path(codebase_path)
    return sum(1 for _ in root.rglob("*.py"))


def index_with_progress(codebase_path: str | Path, use_cache: bool = True) -> TreeIndex:
    """Index with a small progress pulse for CLI feedback."""
    for _ in track(range(1), description="Building tree index"):
        return index_codebase(codebase_path, use_cache=use_cache)
    raise RuntimeError("Indexing did not start")
