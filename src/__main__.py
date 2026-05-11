"""GrabOn AI Coder — CLI Entry Point.

Usage:
    python -m src index --path ./target/httpx
    python -m src submit "Add a timeout_seconds property to Request class"
    python -m src eval --combo a
    python -m src dashboard
"""

from __future__ import annotations

import typer
from rich.console import Console

from src.config import settings
from src.logging import setup_logging

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
) -> None:
    """Build tree index from the target codebase."""
    setup_logging()
    console.print(f"[bold blue]Indexing codebase at:[/] {path}")
    # TODO: Wire to src.indexer.indexer.build_index(path)
    console.print("[yellow]⚠ Indexer not yet implemented[/]")


@app.command()
def submit(
    task: str = typer.Argument(..., help="Natural language task description"),
) -> None:
    """Submit a coding task to the agent."""
    setup_logging()
    console.print(f"[bold blue]Submitting task:[/] {task}")
    # TODO: Wire to src.queue.task_queue.submit(task)
    console.print("[yellow]⚠ Agent loop not yet implemented[/]")


@app.command(name="eval")
def run_eval(
    combo: str = typer.Option(
        "a",
        "--combo",
        "-c",
        help="Model combo: 'a' (Gemini Flash) or 'b' (Haiku + Sonnet)",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output path for benchmark results JSON",
    ),
) -> None:
    """Run the 12-task eval benchmark."""
    setup_logging()
    combo_name = "Gemini Flash (baseline)" if combo == "a" else "Haiku + Sonnet (optimal)"
    console.print(f"[bold blue]Running eval with Combo {combo.upper()}:[/] {combo_name}")
    # TODO: Wire to src.eval.benchmark.run(combo, output)
    console.print("[yellow]⚠ Eval benchmark not yet implemented[/]")


@app.command()
def dashboard() -> None:
    """Launch the Rich terminal dashboard."""
    setup_logging()
    console.print("[bold blue]Launching dashboard...[/]")
    # TODO: Wire to src.queue.dashboard.run()
    console.print("[yellow]⚠ Dashboard not yet implemented[/]")


if __name__ == "__main__":
    app()
