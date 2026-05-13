"""Benchmark scoring helpers."""

from __future__ import annotations

from src.schemas import BenchmarkReport, TaskDefinition, TaskResult, TaskScore, TaskStatus


def score_task(task: TaskDefinition, result: TaskResult) -> TaskScore:
    """Convert a task result into benchmark score."""
    impossible_detected = task.should_be_impossible and result.status == TaskStatus.IMPOSSIBLE
    static_passed = bool(
        result.verification and result.verification.static and result.verification.static.passed
    )
    tests_passed = bool(
        result.verification and result.verification.tests and result.verification.tests.passed
    )
    review_passed = bool(
        result.verification and result.verification.review and result.verification.review.passed
    )
    passed = result.status == TaskStatus.DONE or impossible_detected
    if (
        task.is_budget_exceeded
        and result.failure_reason
        and "Budget exceeded" in result.failure_reason
    ):
        passed = True
    return TaskScore(
        task_id=task.task_id,
        passed=passed,
        impossible_correctly_detected=impossible_detected,
        iterations_used=result.iterations_used,
        cost_usd=result.total_cost_usd,
        cost_breakdown=result.cost_breakdown,
        time_seconds=result.time_seconds,
        static_passed=static_passed,
        tests_passed=tests_passed,
        review_passed=review_passed,
        failure_reason=result.failure_reason,
    )


def aggregate_scores(
    combo: str,
    scores: list[TaskScore],
    run_mode: str = "fixture",
    provider_models: list[str] | None = None,
) -> BenchmarkReport:
    """Aggregate task scores into a report."""
    passed_count = sum(1 for score in scores if score.passed)
    total = len(scores)
    avg_iterations = sum(score.iterations_used for score in scores) / total if total else 0.0
    avg_cost = sum(score.cost_usd for score in scores) / total if total else 0.0
    avg_time = sum(score.time_seconds for score in scores) / total if total else 0.0
    return BenchmarkReport(
        combo=combo,
        run_mode=run_mode,
        provider_models=provider_models or [],
        pass_rate=f"{passed_count}/{total}",
        impossible_detected=any(score.impossible_correctly_detected for score in scores),
        avg_iterations=avg_iterations,
        avg_cost_usd=avg_cost,
        avg_time_seconds=avg_time,
        total_cost_usd=sum(score.cost_usd for score in scores),
        tasks=scores,
    )
