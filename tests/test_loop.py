"""Tests for the agent loop."""

from __future__ import annotations

from pathlib import Path

from src.agent import loop as loop_module
from src.agent.loop import AgentLoop
from src.schemas import (
    GeneratedPatch,
    RetrievalContext,
    ReviewResult,
    StaticAnalysisResult,
    Task,
    TaskStatus,
)
from src.schemas import TestRunResult as PytestRunResult


def test_loop_detects_impossible_task_before_target_checkout(tmp_path: Path) -> None:
    loop = AgentLoop(codebase_path=tmp_path / "missing")

    result = loop.run("Make all httpx requests synchronous by removing async transport")

    assert result.status == TaskStatus.IMPOSSIBLE
    assert result.iterations_used == 0
    assert "async" in (result.failure_reason or "")


def test_loop_reports_missing_target_for_possible_task(tmp_path: Path) -> None:
    loop = AgentLoop(codebase_path=tmp_path / "missing")

    result = loop.run("Add a timeout_seconds property to Request")

    assert result.status == TaskStatus.FAILED
    assert result.run_mode == "fixture"
    assert "Target codebase not found" in (result.failure_reason or "")


def test_loop_detects_sync_contract_removal_before_target_checkout(tmp_path: Path) -> None:
    loop = AgentLoop(codebase_path=tmp_path / "missing")

    result = loop.run("Delete the sync Client API and keep only transport internals")

    assert result.status == TaskStatus.IMPOSSIBLE
    assert result.iterations_used == 0
    assert "sync-client" in (result.failure_reason or "")


def test_plan_routes_request_id_header_tasks_to_client_module() -> None:
    loop = AgentLoop()

    plan = loop._plan(
        Task(
            task_id="adhoc_request_id",
            description="Add a request_id header to every outgoing request using a UUID4",
        )
    )

    assert "httpx/_client.py" in plan.target_files
    assert "hybrid vector fallback" in plan.retrieval_strategy


def test_failure_classifier_marks_import_related_errors() -> None:
    loop = AgentLoop()

    hints, files = loop._classify_failures(
        [
            "NameError: request_id is not defined in httpx/_client.py",
            "tests/test_client.py::test_request_id failed",
        ]
    )

    assert "imports" in hints
    assert "httpx/_client.py" in files


def test_live_loop_stops_after_generation_provider_failure(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "httpx"
    target.mkdir()
    (target / "_models.py").write_text("class Request:\n    pass\n", encoding="utf-8")

    class FakeNavigator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def retrieve_sync(self, *args, **kwargs) -> RetrievalContext:
            return RetrievalContext(task="provider failure")

    def fake_generate(self, *args, **kwargs) -> GeneratedPatch:
        return GeneratedPatch(
            task_id="provider_failure",
            explanation="PROVIDER_ERROR: quota exhausted",
            model="gemini-flash",
        )

    monkeypatch.setattr(loop_module, "Navigator", FakeNavigator)
    monkeypatch.setattr(loop_module.CodeGenerator, "generate", fake_generate)

    result = AgentLoop(codebase_path=target, combo="b", live_models=True).run(
        "Add a timeout property",
        task_id="provider_failure",
    )

    assert result.status == TaskStatus.FAILED
    assert result.iterations_used == 1
    assert "Provider failure during code_generation" in (result.failure_reason or "")


def test_live_loop_invokes_refactoring_stage_on_retry(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "httpx"
    target.mkdir()
    (target / "_models.py").write_text("class Request:\n    pass\n", encoding="utf-8")
    seen = {"refactor": 0, "review": 0}

    class FakeNavigator:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def retrieve_sync(self, *args, **kwargs) -> RetrievalContext:
            return RetrievalContext(task="refactor retry")

    def fake_generate(self, *args, **kwargs) -> GeneratedPatch:
        return GeneratedPatch(
            task_id="retry",
            unified_diff="diff --git a/httpx/_models.py b/httpx/_models.py\n",
            explanation="candidate",
            model="gemini-flash",
        )

    def fake_refactor(self, *args, **kwargs) -> GeneratedPatch:
        seen["refactor"] += 1
        return GeneratedPatch(
            task_id="retry",
            unified_diff=(
                "diff --git a/httpx/_models.py b/httpx/_models.py\n"
                "diff --git a/tests/test_retry.py b/tests/test_retry.py\n"
            ),
            explanation="refactored",
            model="gemini-flash",
        )

    def fake_review(*args, **kwargs) -> ReviewResult:
        seen["review"] += 1
        if seen["review"] == 1:
            return ReviewResult(
                passed=False,
                issues=["needs refinement"],
                summary="needs refinement",
            )
        return ReviewResult(passed=True, summary="ok")

    monkeypatch.setattr(loop_module, "Navigator", FakeNavigator)
    monkeypatch.setattr(loop_module.CodeGenerator, "generate", fake_generate)
    monkeypatch.setattr(loop_module.CodeGenerator, "refactor", fake_refactor)
    monkeypatch.setattr(loop_module, "review_patch", fake_review)
    monkeypatch.setattr(
        loop_module,
        "run_pytest_in_sandbox",
        lambda *args, **kwargs: PytestRunResult(passed=True),
    )
    monkeypatch.setattr(
        loop_module,
        "run_static_analysis_in_sandbox",
        lambda *args, **kwargs: StaticAnalysisResult(passed=True),
    )

    result = AgentLoop(codebase_path=target, combo="a", live_models=True).run(
        "Add a retry-friendly Request helper",
        task_id="retry",
    )

    assert result.status == TaskStatus.DONE
    assert result.iterations_used == 2
    assert seen["refactor"] == 1
