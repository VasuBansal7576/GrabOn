"""Local code-semantic embeddings for vector fallback retrieval.

This deliberately stays offline and deterministic for reproducible evals. It is
not a frontier embedding model; it is a code-aware semantic model that expands
API terms into related implementation tokens before cosine scoring.
"""

from __future__ import annotations

import math
import re
from collections import Counter

EMBEDDING_MODEL_NAME = "local-code-semantic-v1"
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")
_SEMANTIC_ALIASES: dict[str, tuple[str, ...]] = {
    "headers": ("header", "merge", "request", "response"),
    "timeout": ("deadline", "seconds", "connect", "read", "write", "pool"),
    "transport": ("send", "request", "response", "sync", "async"),
    "cache": ("ttl", "expiry", "store", "no_cache", "no_store"),
    "redirect": ("location", "follow", "status", "url"),
    "auth": ("authorization", "credentials", "flow", "digest", "basic"),
    "stream": ("iter", "read", "bytes", "content"),
    "url": ("scheme", "host", "path", "query", "params"),
    "proxy": ("mount", "transport", "url", "routing"),
    "encoding": ("charset", "decode", "text", "content"),
    "status": ("response", "error", "raise", "success"),
    "json": ("encode", "decode", "body", "content"),
}


def embed_text(text: str) -> dict[str, float]:
    """Build a normalized, code-aware semantic embedding for a text snippet."""
    raw_tokens = [token.lower() for token in _TOKEN_RE.findall(text)]
    tokens: list[str] = []
    for token in raw_tokens:
        pieces = _split_identifier(token)
        tokens.extend(pieces)
        for piece in pieces:
            tokens.extend(_SEMANTIC_ALIASES.get(piece, ()))
    if not tokens:
        return {}

    counts = Counter(tokens)
    weights = {token: 1.0 + math.log(count) for token, count in counts.items()}
    norm = math.sqrt(sum(weight * weight for weight in weights.values()))
    if norm == 0:
        return {}
    return {token: weight / norm for token, weight in weights.items()}


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse semantic embeddings."""
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(weight * right.get(token, 0.0) for token, weight in left.items())


def _split_identifier(token: str) -> list[str]:
    snake_parts = token.replace("-", "_").split("_")
    pieces: list[str] = []
    for part in snake_parts:
        camel_split = re.sub("([a-z0-9])([A-Z])", r"\1 \2", part).split()
        pieces.extend(piece.lower() for piece in camel_split if piece)
    return pieces or [token]
