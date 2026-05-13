"""Tests for config and schemas."""

from __future__ import annotations

from src.schemas import (
    Stage,
    TaskResult,
    TaskStatus,
)


def test_task_status_enum() -> None:
    assert TaskStatus.QUEUED == "queued"
    assert TaskStatus.IMPOSSIBLE == "impossible"


def test_stage_enum() -> None:
    assert Stage.CODE_GENERATION == "code_generation"
    assert Stage.LLM_REVIEW == "llm_review"


def test_task_result_success() -> None:
    result = TaskResult.success(
        task_id="task_01",
        code="def foo(): pass",
        iterations=2,
        cost={"planning": 0.001, "generation": 0.012},
        time_s=15.3,
    )
    assert result.status == TaskStatus.DONE
    assert result.iterations_used == 2
    assert result.total_cost_usd == 0.013


def test_task_result_impossible() -> None:
    result = TaskResult.impossible(
        task_id="task_10",
        reason="Contradicts async architecture",
    )
    assert result.status == TaskStatus.IMPOSSIBLE
    assert "async" in result.failure_reason
