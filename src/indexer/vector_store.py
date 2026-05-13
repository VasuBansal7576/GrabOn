"""SQLite-backed vector store for hybrid retrieval."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.indexer.semantic_embeddings import EMBEDDING_MODEL_NAME, cosine_similarity, embed_text
from src.schemas import CodeChunk


def build_vector_store(chunks: list[CodeChunk], path: str | Path) -> Path:
    """Persist code chunks in a local SQLite vector database."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as connection:
        connection.execute("DROP TABLE IF EXISTS vector_metadata")
        connection.execute("DROP TABLE IF EXISTS code_chunks")
        connection.execute(
            """
            CREATE TABLE vector_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE code_chunks (
                chunk_id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                symbol TEXT NOT NULL,
                unit_type TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_json TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO vector_metadata (key, value) VALUES (?, ?)",
            [
                ("backend", "sqlite-vector-db"),
                ("collection", "code_chunks"),
                ("embedding_model", EMBEDDING_MODEL_NAME),
            ],
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_code_chunks_file_path ON code_chunks(file_path)"
        )
        connection.executemany(
            """
            INSERT INTO code_chunks (
                chunk_id, unit_id, file_path, symbol, unit_type, content,
                embedding_model, embedding_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk.chunk_id,
                    chunk.unit_id,
                    chunk.file_path,
                    chunk.symbol,
                    chunk.unit_type,
                    chunk.content,
                    chunk.embedding_model,
                    json.dumps(chunk.embedding, sort_keys=True),
                )
                for chunk in chunks
            ],
        )
        connection.commit()
    return target


def query_code_chunks(
    path: str | Path,
    query: str,
    limit: int = 5,
    preferred_files: list[str] | None = None,
) -> list[CodeChunk]:
    """Query the persisted vector store and return the best matching chunks."""
    store_path = Path(path)
    if not store_path.exists():
        return []

    preferred = set(preferred_files or [])
    query_embedding = embed_text(query)
    best_by_unit: dict[str, tuple[float, CodeChunk]] = {}

    with sqlite3.connect(store_path) as connection:
        cursor = connection.execute(
            """
            SELECT
                chunk_id, unit_id, file_path, symbol, unit_type, content,
                embedding_model, embedding_json
            FROM code_chunks
            """
        )
        for row in cursor.fetchall():
            embedding = json.loads(row[7])
            score = cosine_similarity(query_embedding, embedding)
            if preferred and row[2] in preferred:
                score += 0.08
            if score <= 0:
                continue

            chunk = CodeChunk(
                chunk_id=row[0],
                unit_id=row[1],
                file_path=row[2],
                symbol=row[3],
                unit_type=row[4],
                content=row[5],
                embedding_model=row[6],
                embedding=embedding,
            )
            current = best_by_unit.get(chunk.unit_id)
            if current is None or score > current[0]:
                best_by_unit[chunk.unit_id] = (score, chunk)

    ranked = sorted(best_by_unit.values(), key=lambda item: (-item[0], item[1].chunk_id))
    return [chunk for _, chunk in ranked[:limit]]
