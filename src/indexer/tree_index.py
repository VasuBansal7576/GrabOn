"""Tree index builder and cache support."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from src.config import settings
from src.indexer.ast_parser import parse_codebase
from src.indexer.semantic_embeddings import EMBEDDING_MODEL_NAME, embed_text
from src.indexer.vector_store import build_vector_store
from src.schemas import CodeChunk, DocChunk, ModuleNode, ParsedUnit, TreeIndex


def build_tree_index(codebase_path: str | Path, use_cache: bool = True) -> TreeIndex:
    """Build or load a tree index for a codebase."""
    root = Path(codebase_path).resolve()
    source_hash = codebase_hash(root)
    cache_path = _cache_path(source_hash)
    if use_cache and settings.index_cache_enabled and cache_path.exists():
        cached = load_tree_index(cache_path)
        if _cache_supports_hybrid_retrieval(cached):
            return cached

    modules, units = parse_codebase(root)
    unit_map = {unit.unit_id: unit for unit in units}
    import_graph = _build_reference_graph(unit_map)
    test_map = _build_test_map(modules, unit_map)
    doc_chunks = _build_doc_chunks(root)
    code_chunks = _build_code_chunks(unit_map)
    vector_store_path = _vector_store_path(source_hash)
    build_vector_store(code_chunks, vector_store_path)
    index = TreeIndex(
        modules=modules,
        units=unit_map,
        import_graph=import_graph,
        test_map=test_map,
        doc_chunks=doc_chunks,
        code_chunks=code_chunks,
        vector_store_path=str(vector_store_path),
        codebase_path=str(root),
        source_hash=source_hash,
    )
    if use_cache and settings.index_cache_enabled:
        save_tree_index(index, cache_path)
    return index


def save_tree_index(index: TreeIndex, path: str | Path) -> None:
    """Save a tree index as JSON."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(index.model_dump_json(indent=2), encoding="utf-8")


def load_tree_index(path: str | Path) -> TreeIndex:
    """Load a tree index from JSON."""
    return TreeIndex.model_validate_json(Path(path).read_text(encoding="utf-8"))


def codebase_hash(codebase_path: str | Path) -> str:
    """Hash Python and markdown sources for cache invalidation."""
    root = Path(codebase_path).resolve()
    digest = hashlib.sha256()
    candidates = list(root.rglob("*.py"))
    candidates.extend(root.rglob("*.md"))
    for path in sorted(candidates):
        if any(part in {".git", "__pycache__", ".venv", "venv"} for part in path.parts):
            continue
        stat = path.stat()
        rel = path.relative_to(root).as_posix()
        digest.update(f"{rel}:{stat.st_mtime_ns}:{stat.st_size}\n".encode())
    return digest.hexdigest()[:16]


def _cache_path(source_hash: str) -> Path:
    return settings.cache_dir / f"tree_index_{source_hash}.json"


def _vector_store_path(source_hash: str) -> Path:
    return settings.cache_dir / f"tree_index_{source_hash}.sqlite3"


def _cache_supports_hybrid_retrieval(index: TreeIndex) -> bool:
    """Reject legacy caches that predate code chunks or vector persistence."""
    if index.units and not index.code_chunks:
        return False
    if index.units and not index.vector_store_path:
        return False
    if not index.vector_store_path:
        return True
    store = Path(index.vector_store_path)
    if not store.exists():
        return False
    try:
        with sqlite3.connect(store) as connection:
            rows = dict(connection.execute("SELECT key, value FROM vector_metadata").fetchall())
    except sqlite3.Error:
        return False
    return rows.get("embedding_model") == EMBEDDING_MODEL_NAME


def _build_reference_graph(units: dict[str, ParsedUnit]) -> dict[str, list[str]]:
    by_name: dict[str, list[str]] = {}
    for unit in units.values():
        by_name.setdefault(unit.name, []).append(unit.unit_id)

    graph: dict[str, list[str]] = {}
    for unit in units.values():
        references: set[str] = set()
        for name, unit_ids in by_name.items():
            if name == unit.name:
                continue
            if name in unit.body:
                references.update(unit_ids)
        graph[unit.unit_id] = sorted(references)
    return graph


def _build_test_map(
    modules: dict[str, ModuleNode],
    units: dict[str, ParsedUnit],
) -> dict[str, list[str]]:
    tests = {
        path: module
        for path, module in modules.items()
        if path.startswith("tests/") or "/tests/" in path or path.startswith("test_")
    }
    result: dict[str, list[str]] = {unit_id: [] for unit_id in units}
    for unit_id, unit in units.items():
        if unit.file_path in tests:
            continue
        candidates: set[str] = set()
        file_stem = Path(unit.file_path).stem.replace("_", "")
        for test_path, test_module in tests.items():
            haystack = " ".join([test_path, *test_module.functions, *test_module.classes])
            compact = haystack.replace("_", "")
            if unit.name in haystack or file_stem in compact:
                candidates.add(test_path)
        result[unit_id] = sorted(candidates)
    return result


def _build_doc_chunks(root: Path) -> list[DocChunk]:
    chunks: list[DocChunk] = []
    candidates: list[Path] = []
    readme = root / "README.md"
    if readme.exists():
        candidates.append(readme)
    docs_dir = root / "docs"
    if docs_dir.exists():
        candidates.extend(sorted(docs_dir.rglob("*.md")))

    for path in candidates:
        rel_path = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8")
        chunks.extend(_chunk_markdown(rel_path, content))
    return chunks


def _build_code_chunks(units: dict[str, ParsedUnit], max_chars: int = 900) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    for unit in sorted(units.values(), key=lambda candidate: candidate.unit_id):
        sections = [unit.unit_id, unit.signature]
        if unit.docstring:
            sections.append(unit.docstring)
        sections.append(unit.body)
        content = "\n\n".join(section for section in sections if section.strip())
        for index, chunk_text in enumerate(_chunk_code_text(content, max_chars=max_chars)):
            chunks.append(
                CodeChunk(
                    chunk_id=f"{unit.unit_id}::{index}",
                    unit_id=unit.unit_id,
                    file_path=unit.file_path,
                    symbol=unit.name,
                    unit_type=unit.unit_type,
                    content=chunk_text,
                    embedding=embed_text(chunk_text),
                    embedding_model=EMBEDDING_MODEL_NAME,
                )
            )
    return chunks


def _chunk_markdown(file_path: str, content: str, max_chars: int = 900) -> list[DocChunk]:
    parts = re.split(r"(?m)^#{1,6}\s+", content)
    headings = re.findall(r"(?m)^#{1,6}\s+(.*)$", content)
    if not headings:
        return _chunk_plain_text(file_path, "README", content, max_chars)

    intro = parts[0].strip()
    chunks: list[DocChunk] = []
    if intro:
        chunks.extend(_chunk_plain_text(file_path, "Overview", intro, max_chars))

    for heading, body in zip(headings, parts[1:], strict=False):
        text = body.strip()
        if not text:
            continue
        chunks.extend(_chunk_plain_text(file_path, heading.strip(), text, max_chars))
    return chunks


def _chunk_plain_text(
    file_path: str,
    heading: str,
    content: str,
    max_chars: int,
) -> list[DocChunk]:
    paragraphs = [paragraph.strip() for paragraph in content.split("\n\n") if paragraph.strip()]
    chunks: list[DocChunk] = []
    buffer = ""
    chunk_index = 0
    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        if buffer:
            chunks.append(
                DocChunk(
                    chunk_id=f"{file_path}::{chunk_index}",
                    file_path=file_path,
                    heading=heading,
                    content=buffer,
                )
            )
            chunk_index += 1
        buffer = paragraph
    if buffer:
        chunks.append(
            DocChunk(
                chunk_id=f"{file_path}::{chunk_index}",
                file_path=file_path,
                heading=heading,
                content=buffer,
            )
        )
    return chunks


def _chunk_code_text(content: str, max_chars: int) -> list[str]:
    lines = content.splitlines()
    if not lines:
        return []

    chunks: list[str] = []
    start = 0
    overlap = 3
    while start < len(lines):
        buffer: list[str] = []
        total = 0
        end = start
        while end < len(lines):
            line = lines[end]
            projected = total + len(line) + 1
            if buffer and projected > max_chars:
                break
            buffer.append(line)
            total = projected
            end += 1
        chunks.append("\n".join(buffer).strip())
        if end >= len(lines):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]
