"""Benchmark task loading."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.schemas import Difficulty, TaskDefinition


def load_tasks(tasks_dir: str | Path = "eval/tasks") -> list[TaskDefinition]:
    """Load benchmark task YAML files."""
    root = Path(tasks_dir)
    tasks: list[TaskDefinition] = []
    for path in sorted(root.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if "difficulty" in data:
            data["difficulty"] = Difficulty(data["difficulty"])
        tasks.append(TaskDefinition.model_validate(data))
    return tasks
