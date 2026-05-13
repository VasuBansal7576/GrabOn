"""Tests for the in-memory task queue."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from src.queue.task_queue import TaskQueue
from src.schemas import TaskResult, TaskStatus


class FakeAgent:
    def run(self, description: str, task_id: str) -> TaskResult:
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.DONE,
            generated_code=description,
            iterations_used=1,
        )


def test_task_queue_submit_status_and_result() -> None:
    queue = TaskQueue(agent=FakeAgent(), state_path=Path("test-queue-state.json"))  # type: ignore[arg-type]

    task_id = queue.submit("change code")
    deadline = time.monotonic() + 2.0
    while queue.get_status(task_id) != TaskStatus.DONE and time.monotonic() < deadline:
        time.sleep(0.01)

    assert queue.get_status(task_id) == TaskStatus.DONE
    assert queue.get_result(task_id).generated_code == "change code"
    assert [result.task_id for result in queue.list_tasks()] == [task_id]
    queue.shutdown()
    queue.state_path.unlink(missing_ok=True)


class BlockingAgent:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, description: str, task_id: str) -> TaskResult:
        self.started.set()
        self.release.wait(timeout=2.0)
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.DONE,
            generated_code=description,
            iterations_used=1,
        )


def test_task_queue_submit_returns_before_work_finishes() -> None:
    agent = BlockingAgent()
    queue = TaskQueue(agent=agent, state_path=Path("test-queue-state-running.json"))  # type: ignore[arg-type]

    start = time.monotonic()
    task_id = queue.submit("change code")
    submit_duration = time.monotonic() - start

    assert submit_duration < 0.1
    assert agent.started.wait(timeout=1.0)
    assert queue.get_status(task_id) == TaskStatus.RUNNING

    agent.release.set()
    deadline = time.monotonic() + 2.0
    while queue.get_status(task_id) != TaskStatus.DONE and time.monotonic() < deadline:
        time.sleep(0.01)

    assert queue.get_status(task_id) == TaskStatus.DONE
    queue.shutdown()
    queue.state_path.unlink(missing_ok=True)


def test_task_queue_restores_persisted_results(tmp_path: Path) -> None:
    state_path = tmp_path / "queue-state.json"
    first = TaskQueue(agent=FakeAgent(), state_path=state_path)  # type: ignore[arg-type]

    task_id = first.submit("persisted change")
    deadline = time.monotonic() + 2.0
    while first.get_status(task_id) != TaskStatus.DONE and time.monotonic() < deadline:
        time.sleep(0.01)
    first.shutdown()

    second = TaskQueue(agent=FakeAgent(), state_path=state_path)  # type: ignore[arg-type]

    assert second.get_status(task_id) == TaskStatus.DONE
    assert second.get_result(task_id).generated_code == "persisted change"
    second.shutdown()
