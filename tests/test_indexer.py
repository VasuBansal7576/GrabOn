"""Tests for the codebase indexer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import settings
from src.indexer.indexer import index_codebase
from src.indexer.tree_index import build_tree_index, save_tree_index
from src.indexer.vector_store import query_code_chunks


def test_indexer_extracts_structural_units(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "service.py").write_text(
        '"""Service docs."""\n'
        "import os\n\n"
        "class Greeter:\n"
        "    def hello(self, name: str) -> str:\n"
        "        return format_name(name)\n\n"
        "def format_name(name: str) -> str:\n"
        "    return name.title()\n",
        encoding="utf-8",
    )

    index = index_codebase(package, use_cache=False)

    assert "service.py" in index.modules
    assert "service.Greeter" in index.units
    assert "service.Greeter.hello" in index.units
    assert "service.format_name" in index.units
    assert "service.format_name" in index.import_graph["service.Greeter.hello"]


def test_indexer_chunks_readme_docs(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "service.py").write_text("def main() -> None:\n    return None\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Contributing\n\nUse existing helper functions before adding new abstractions.\n",
        encoding="utf-8",
    )

    index = index_codebase(tmp_path, use_cache=False)

    assert any(chunk.file_path == "README.md" for chunk in index.doc_chunks)
    assert any(chunk.unit_id == "pkg.service.main" for chunk in index.code_chunks)
    assert any(chunk.embedding for chunk in index.code_chunks)
    assert index.vector_store_path is not None
    assert Path(index.vector_store_path).exists()
    with sqlite3.connect(index.vector_store_path) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM vector_metadata").fetchall())
    assert metadata["backend"] == "sqlite-vector-db"
    assert metadata["embedding_model"] == "local-code-semantic-v1"
    matches = query_code_chunks(index.vector_store_path, "main helper function", limit=2)
    assert matches


def test_legacy_cached_index_rebuilds_hybrid_state(tmp_path: Path, monkeypatch) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "service.py").write_text(
        "def main() -> str:\n"
        '    return "ready"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "cache_dir", tmp_path / ".cache")

    fresh = build_tree_index(package, use_cache=False)
    fresh.code_chunks = []
    fresh.vector_store_path = None

    cached = build_tree_index(package, use_cache=False)
    cache_path = settings.cache_dir / f"tree_index_{cached.source_hash}.json"
    save_tree_index(fresh, cache_path)

    rebuilt = index_codebase(package, use_cache=True)

    assert rebuilt.code_chunks
    assert rebuilt.vector_store_path is not None
    assert Path(rebuilt.vector_store_path).exists()
