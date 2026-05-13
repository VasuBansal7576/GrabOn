"""GrabOn AI Coder — Structured Logging via structlog.

JSONL output in production, pretty console output in development.
Every log entry includes: timestamp, task_id, iteration, phase, tokens, cost_usd.
No print() statements anywhere in core logic — use this module instead.
"""

from __future__ import annotations

import logging as py_logging
import sys
from typing import Any, cast

import orjson
import structlog
from structlog.types import EventDict, WrappedLogger

from src.config import settings


def _orjson_serializer(data: dict[str, Any], **_kwargs: Any) -> str:
    """Fast JSON serialization using orjson."""
    return orjson.dumps(data, option=orjson.OPT_NAIVE_UTC).decode("utf-8")


def _add_app_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add default application context to every log entry."""
    event_dict.setdefault("app", "grabonai-coder")
    return event_dict


def setup_logging() -> None:
    """Configure structlog for the application.

    - Development (LOG_LEVEL=DEBUG): Pretty console output with colors.
    - Production (LOG_LEVEL=INFO+): JSONL output for machine parsing.
    """
    is_dev = settings.log_level == "DEBUG"
    log_level = getattr(py_logging, settings.log_level.upper(), py_logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _add_app_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_dev:
        # Human-readable console output for development
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )
    else:
        # Machine-readable JSONL for production / eval
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(serializer=_orjson_serializer),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named logger bound with the module name."""
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(module=name))


def log_phase(
    task_id: str,
    iteration: int,
    phase: str,
    data: Any,
    tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Log an agent loop phase event with structured fields.

    This is the primary logging function for the agent loop.
    Every call writes a structured JSONL entry with all fields
    needed for observability and cost tracking.
    """
    logger = get_logger("agent.loop")
    logger.info(
        phase,
        task_id=task_id,
        iteration=iteration,
        data=_summarize_for_log(data),
        tokens=tokens,
        cost_usd=cost_usd,
    )


def _summarize_for_log(value: Any) -> Any:
    """Keep JSONL useful without dumping entire source files."""
    if isinstance(value, dict):
        if {"task", "units", "tests", "tool_calls"}.issubset(value.keys()):
            return {
                "task": _truncate(value.get("task")),
                "unit_ids": [unit.get("unit_id") for unit in value.get("units", [])[:8]],
                "test_count": len(value.get("tests", [])),
                "tool_call_count": len(value.get("tool_calls", [])),
                "notes": value.get("notes", []),
            }
        if {"unified_diff", "task_id"}.issubset(value.keys()):
            return {
                **value,
                "unified_diff": _truncate(value.get("unified_diff"), limit=1200),
            }
        return {key: _summarize_for_log(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_summarize_for_log(item) for item in value[:20]]
    if isinstance(value, str):
        return _truncate(value)
    return value


def _truncate(value: Any, limit: int = 500) -> Any:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[:limit] + "...[truncated]"
