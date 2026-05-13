"""CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from src.agent.loop import AgentLoop
from src.config import settings
from src.eval.benchmark import run_benchmark
from src.eval.compare import compare_report_files
from src.eval.cost_report import build_cost_report
from src.eval.provider_smoke import run_provider_smoke
from src.eval.retrieval_recall import run_retrieval_recall
from src.indexer.indexer import index_with_progress
from src.logging import setup_logging
from src.queue.dashboard import run as run_dashboard
from src.schemas import Stage

app = typer.Typer(
    name="grabonai-coder",
    help="Coding agent with tree-index retrieval, self-testing, and iterative repair.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def index(
    path: str = typer.Option(
        str(settings.target_codebase_path),
        "--path",
        "-p",
        help="Path to the target codebase",
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable index cache"),
) -> None:
    """Build tree index from the target codebase."""
    setup_logging()
    tree = index_with_progress(path, use_cache=not no_cache)
    console.print(
        f"[green]Indexed[/] {len(tree.modules)} modules, {len(tree.units)} units "
        f"from {Path(path)}"
    )


@app.command()
def submit(
    task: str = typer.Argument(..., help="Natural language task description"),
    path: str = typer.Option(
        str(settings.target_codebase_path),
        "--path",
        "-p",
        help="Path to the target codebase",
    ),
    combo: str = typer.Option("b", "--combo", "-c", help="Model combo: a or b"),
    live: bool = typer.Option(
        False,
        "--live",
        help="Disable deterministic templates and require live provider generation/review",
    ),
) -> None:
    """Submit a coding task to the agent."""
    setup_logging()
    result = AgentLoop(codebase_path=path, combo=combo, live_models=live).run(task)
    console.print_json(result.model_dump_json(indent=2))


@app.command(name="eval")
def run_eval(
    combo: str = typer.Option("a", "--combo", "-c", help="Model combo: a or b"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output JSON path"),
    limit: int | None = typer.Option(None, "--limit", "-n", help="Limit number of tasks"),
    tasks: str | None = typer.Option(
        None,
        "--tasks",
        help="Comma-separated task ids to run, e.g. task_01_request_timeout_seconds",
    ),
    path: str = typer.Option(
        str(settings.target_codebase_path),
        "--path",
        "-p",
        help="Path to the target codebase",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help="Disable deterministic templates and require live provider generation/review",
    ),
) -> None:
    """Run the eval benchmark."""
    setup_logging()
    report = run_benchmark(
        combo=combo,
        output=output,
        limit=limit,
        task_ids=[task.strip() for task in tasks.split(",") if task.strip()] if tasks else None,
        codebase_path=path,
        live_models=live,
    )
    console.print_json(report.model_dump_json(indent=2))


@app.command()
def dashboard(
    tasks: Annotated[
        list[str] | None,
        typer.Argument(help="Quoted tasks to submit before rendering the dashboard"),
    ] = None,
    path: str = typer.Option(
        str(settings.target_codebase_path),
        "--path",
        "-p",
        help="Path to the target codebase",
    ),
    combo: str = typer.Option("b", "--combo", "-c", help="Model combo: a or b"),
    live: bool = typer.Option(
        False,
        "--live",
        help="Require live provider generation/review for submitted tasks",
    ),
) -> None:
    """Render queue status, verification, diff summaries, cost, and time."""
    setup_logging()
    run_dashboard(
        tasks or (),
        codebase_path=path,
        combo=combo,
        live_models=live,
    )


@app.command(name="retrieval-eval")
def retrieval_eval(
    output: str | None = typer.Option(None, "--output", "-o", help="Output JSON path"),
    path: str = typer.Option(
        str(settings.target_codebase_path),
        "--path",
        "-p",
        help="Path to the target codebase",
    ),
) -> None:
    """Measure tree-index retrieval against a grep-style baseline."""
    setup_logging()
    report = run_retrieval_recall(codebase_path=path, output=output)
    console.print_json(report.model_dump_json(indent=2))


@app.command(name="compare-eval")
def compare_eval(
    left: str = typer.Option(..., "--left", help="Path to the left benchmark JSON report"),
    right: str = typer.Option(..., "--right", help="Path to the right benchmark JSON report"),
    output: str | None = typer.Option(None, "--output", "-o", help="Output JSON path"),
) -> None:
    """Compare two benchmark reports with paired sign-test p-values."""
    setup_logging()
    comparison = compare_report_files(left, right, output=output)
    console.print_json(comparison.model_dump_json(indent=2))


@app.command(name="provider-smoke")
def provider_smoke(
    combos: str = typer.Option(
        "a,nvidia",
        "--combos",
        help="Comma-separated combo names to smoke, e.g. a,nvidia",
    ),
    stages: str = typer.Option(
        "planning",
        "--stages",
        help=(
            "Comma-separated stages to smoke, e.g. "
            "planning,context_ranking,error_parsing,test_analysis,llm_review"
        ),
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output JSON path"),
) -> None:
    """Call configured live providers once and write raw evidence."""
    setup_logging()
    names = [combo.strip() for combo in combos.split(",") if combo.strip()]
    selected_stages = [Stage(stage.strip()) for stage in stages.split(",") if stage.strip()]
    report = run_provider_smoke(names, output=output, stages=selected_stages)
    console.print_json(report.model_dump_json(indent=2))


@app.command(name="cost-report")
def cost_report(
    reports_dir: str = typer.Option(
        "reports",
        "--reports-dir",
        help="Directory of raw JSON reports",
    ),
    output: str | None = typer.Option(
        "reports/submission_cost_summary.json",
        "--output",
        "-o",
        help="Output JSON path",
    ),
) -> None:
    """Aggregate measured cost evidence from raw reports."""
    summary = build_cost_report(reports_dir=reports_dir, output=output)
    console.print_json(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
