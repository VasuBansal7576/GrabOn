"""In-memory task queue."""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from src.agent.loop import AgentLoop
from src.config import settings
from src.schemas import TaskResult, TaskStatus


@dataclass
class TaskQueue:
    """Background task queue for CLI/demo use."""

    agent: AgentLoop = field(default_factory=AgentLoop)
    max_workers: int = 2
    _counter: Iterator[int] = field(default_factory=lambda: itertools.count(1))
    _results: dict[str, TaskResult] = field(default_factory=dict)
    _futures: dict[str, Future[TaskResult]] = field(default_factory=dict)
    _executor: ThreadPoolExecutor = field(init=False)
    _lock: Lock = field(default_factory=Lock)
    state_path: Path = field(default_factory=lambda: settings.queue_state_path)

    def __post_init__(self) -> None:
        self._restore_state()
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="grabonai-task",
        )

    def submit(self, description: str) -> str:
        task_id = f"task_{next(self._counter):04d}"
        with self._lock:
            self._results[task_id] = TaskResult(task_id=task_id, status=TaskStatus.QUEUED)
            self._persist_state()
        self._futures[task_id] = self._executor.submit(self._run_task, task_id, description)
        return task_id

    def get_status(self, task_id: str) -> TaskStatus:
        return self._results[task_id].status

    def get_result(self, task_id: str) -> TaskResult:
        return self._results[task_id]

    def list_tasks(self) -> list[TaskResult]:
        return list(self._results.values())

    def all_done(self) -> bool:
        terminal = {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.IMPOSSIBLE}
        return bool(self._results) and all(
            result.status in terminal for result in self._results.values()
        )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run_task(self, task_id: str, description: str) -> TaskResult:
        with self._lock:
            self._results[task_id] = TaskResult(task_id=task_id, status=TaskStatus.RUNNING)
            self._persist_state()
        try:
            result = self.agent.run(description, task_id=task_id)
        except Exception as exc:  # pragma: no cover - defensive path
            result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )
        with self._lock:
            self._results[task_id] = result
            self._persist_state()
        return result

    def _restore_state(self) -> None:
        if not self.state_path.exists():
            return
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        restored: dict[str, TaskResult] = {}
        highest = 0
        for raw in payload:
            result = TaskResult.model_validate(raw)
            if result.status in {TaskStatus.QUEUED, TaskStatus.RUNNING}:
                result = result.model_copy(
                    update={
                        "status": TaskStatus.FAILED,
                        "failure_reason": (
                            result.failure_reason
                            or "Recovered from persisted queue snapshot before completion"
                        ),
                    }
                )
            restored[result.task_id] = result
            highest = max(highest, _task_sequence(result.task_id))
        self._results = restored
        self._counter = itertools.count(highest + 1)

    def _persist_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = [result.model_dump(mode="json") for result in self._results.values()]
        self.state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _task_sequence(task_id: str) -> int:
    try:
        return int(task_id.rsplit("_", 1)[-1])
    except ValueError:
        return 0
