"""Compatibility wrapper for the local code-semantic embedding model."""

from __future__ import annotations

from src.indexer.semantic_embeddings import cosine_similarity, embed_text

__all__ = ["cosine_similarity", "embed_text"]
