"""Rich terminal dashboard."""

from __future__ import annotations

import time
from collections.abc import Iterable

from rich.console import Console
from rich.live import Live
from rich.table import Table

from src.agent.loop import AgentLoop
from src.queue.task_queue import TaskQueue
from src.schemas import TaskResult


def render_dashboard(queue: TaskQueue) -> Table:
    """Build a dashboard table for the current queue state."""
    table = Table(title="GrabOn Coder Tasks")
    table.add_column("Task ID")
    table.add_column("Status")
    table.add_column("Iterations")
    table.add_column("Verification")
    table.add_column("Diff")
    table.add_column("Cost USD")
    table.add_column("Time")
    table.add_column("Failure")
    for result in queue.list_tasks():
        table.add_row(
            result.task_id,
            result.status.value,
            str(result.iterations_used),
            _verification_summary(result),
            _diff_summary(result),
            f"{result.total_cost_usd:.4f}",
            f"{result.time_seconds:.3f}s",
            result.failure_reason or "",
        )
    return table


def run(
    tasks: Iterable[str] = (),
    *,
    codebase_path: str | None = None,
    combo: str = "b",
    live_models: bool = False,
) -> None:
    """Submit optional tasks, then render the task queue state."""
    console = Console()
    queue = TaskQueue(
        agent=AgentLoop(
            codebase_path=codebase_path,
            combo=combo,
            live_models=live_models,
        )
    )
    for task in tasks:
        queue.submit(task)
    if not tasks:
        console.print(render_dashboard(queue))
        queue.shutdown()
        return
    with Live(render_dashboard(queue), console=console, refresh_per_second=4) as live:
        while not queue.all_done():
            live.update(render_dashboard(queue))
            time.sleep(0.1)
        live.update(render_dashboard(queue))
    queue.shutdown()


def _verification_summary(result: TaskResult) -> str:
    verification = result.verification
    if verification is None:
        return "-"
    static = _layer_status(verification.static.passed if verification.static else None)
    tests = _layer_status(verification.tests.passed if verification.tests else None)
    review = _layer_status(verification.review.passed if verification.review else None)
    return f"static:{static} tests:{tests} review:{review}"


def _layer_status(passed: bool | None) -> str:
    if passed is True:
        return "ok"
    if passed is False:
        return "fail"
    return "-"


def _diff_summary(result: TaskResult) -> str:
    patch = result.patch.unified_diff if result.patch else result.generated_code or ""
    files = [
        line.removeprefix("+++ b/") for line in patch.splitlines() if line.startswith("+++ b/")
    ]
    changed_lines = sum(
        1
        for line in patch.splitlines()
        if (line.startswith("+") or line.startswith("-"))
        and not line.startswith("+++")
        and not line.startswith("---")
    )
    if not files:
        return "-"
    preview = ", ".join(files[:2])
    if len(files) > 2:
        preview = f"{preview}, +{len(files) - 2} more"
    return f"{preview} ({changed_lines} changed lines)"
