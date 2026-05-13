"""Benchmark runner."""

from __future__ import annotations

from pathlib import Path

from src.agent.loop import AgentLoop
from src.agent.router import ModelRouter
from src.config import settings
from src.eval.scorer import aggregate_scores, score_task
from src.eval.tasks import load_tasks
from src.schemas import BenchmarkReport


def run_benchmark(
    combo: str = "a",
    output: str | Path | None = None,
    limit: int | None = None,
    task_ids: list[str] | None = None,
    codebase_path: str | Path | None = None,
    live_models: bool = False,
) -> BenchmarkReport:
    """Run benchmark tasks and optionally write a JSON report."""
    tasks = load_tasks()
    if task_ids is not None:
        allowed = set(task_ids)
        tasks = [task for task in tasks if task.task_id in allowed]
    if limit is not None:
        tasks = tasks[:limit]
    scores = []
    provider_models: set[str] = set()
    for task in tasks:
        budget = (
            task.budget_usd if task.budget_usd is not None else settings.cost_budget_per_task_usd
        )
        if task.is_budget_exceeded:
            budget = task.budget_usd or 0.02
        loop = AgentLoop(
            codebase_path=codebase_path or settings.target_codebase_path,
            combo=combo,
            budget_usd=budget,
            live_models=live_models,
        )
        provider_models.update(ModelRouter(combo=combo).provider_models())
        result = loop.run(task.description, task_id=task.task_id)
        scores.append(score_task(task, result))
    report = aggregate_scores(
        combo,
        scores,
        run_mode="live" if live_models else "fixture",
        provider_models=sorted(provider_models),
    )
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report
