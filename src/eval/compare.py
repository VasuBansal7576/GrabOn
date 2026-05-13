"""Paired comparison helpers for benchmark reports."""

from __future__ import annotations

from collections.abc import Callable
from math import comb
from pathlib import Path

from src.schemas import BenchmarkComparison, BenchmarkReport, ComparisonMetric, TaskScore


def compare_reports(
    left_report: BenchmarkReport,
    right_report: BenchmarkReport,
) -> BenchmarkComparison:
    """Compare two benchmark reports on aligned task ids."""
    left_tasks = {task.task_id: task for task in left_report.tasks}
    right_tasks = {task.task_id: task for task in right_report.tasks}
    shared_ids = sorted(set(left_tasks) & set(right_tasks))

    left_pass_rate = _pass_rate(left_report.tasks)
    right_pass_rate = _pass_rate(right_report.tasks)

    return BenchmarkComparison(
        left_combo=left_report.combo,
        right_combo=right_report.combo,
        left_run_mode=left_report.run_mode,
        right_run_mode=right_report.run_mode,
        task_count=len(shared_ids),
        left_provider_models=left_report.provider_models,
        right_provider_models=right_report.provider_models,
        pass_rate_delta=round(left_pass_rate - right_pass_rate, 4),
        pass_rate_p_value=_paired_sign_p_value(
            [
                (1.0 if left_tasks[task_id].passed else 0.0)
                - (1.0 if right_tasks[task_id].passed else 0.0)
                for task_id in shared_ids
            ]
        ),
        iterations=_metric_summary(
            [left_tasks[task_id] for task_id in shared_ids],
            [right_tasks[task_id] for task_id in shared_ids],
            lambda task: float(task.iterations_used),
            lower_is_better=True,
            left_average=left_report.avg_iterations,
            right_average=right_report.avg_iterations,
        ),
        cost=_metric_summary(
            [left_tasks[task_id] for task_id in shared_ids],
            [right_tasks[task_id] for task_id in shared_ids],
            lambda task: task.cost_usd,
            lower_is_better=True,
            left_average=left_report.avg_cost_usd,
            right_average=right_report.avg_cost_usd,
        ),
        time=_metric_summary(
            [left_tasks[task_id] for task_id in shared_ids],
            [right_tasks[task_id] for task_id in shared_ids],
            lambda task: task.time_seconds,
            lower_is_better=True,
            left_average=left_report.avg_time_seconds,
            right_average=right_report.avg_time_seconds,
        ),
    )


def compare_report_files(
    left_path: str | Path,
    right_path: str | Path,
    output: str | Path | None = None,
) -> BenchmarkComparison:
    """Load two JSON reports, compare them, and optionally write the result."""
    left = BenchmarkReport.model_validate_json(Path(left_path).read_text(encoding="utf-8"))
    right = BenchmarkReport.model_validate_json(Path(right_path).read_text(encoding="utf-8"))
    comparison = compare_reports(left, right)
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(comparison.model_dump_json(indent=2), encoding="utf-8")
    return comparison


def _metric_summary(
    left_tasks: list[TaskScore],
    right_tasks: list[TaskScore],
    getter: Callable[[TaskScore], float],
    *,
    lower_is_better: bool,
    left_average: float,
    right_average: float,
) -> ComparisonMetric:
    deltas = [
        getter(left) - getter(right)
        for left, right in zip(left_tasks, right_tasks, strict=False)
    ]
    p_value = _paired_sign_p_value(deltas)
    winner = "tie"
    if left_average != right_average:
        left_is_better = (
            left_average < right_average
            if lower_is_better
            else left_average > right_average
        )
        winner = "left" if left_is_better else "right"
    return ComparisonMetric(
        left_avg=round(left_average, 6),
        right_avg=round(right_average, 6),
        delta=round(left_average - right_average, 6),
        winner=winner,
        p_value=p_value,
    )


def _pass_rate(tasks: list[TaskScore]) -> float:
    if not tasks:
        return 0.0
    return sum(1 for task in tasks if task.passed) / len(tasks)


def _paired_sign_p_value(deltas: list[float]) -> float | None:
    wins = 0
    losses = 0
    for delta in deltas:
        if delta == 0:
            continue
        if delta < 0:
            wins += 1
        else:
            losses += 1
    trials = wins + losses
    if trials == 0:
        return None
    tail = sum(comb(trials, count) for count in range(0, min(wins, losses) + 1)) / (2**trials)
    return float(round(min(1.0, 2 * tail), 6))
