"""Core Plan -> Act -> Observe -> Decide loop."""

from __future__ import annotations

import re
import time
from pathlib import Path

from src.agent.generator import CodeGenerator
from src.agent.router import CostTracker, ModelRouter
from src.config import settings
from src.indexer.indexer import index_codebase
from src.logging import log_phase
from src.retrieval.navigator import Navigator
from src.schemas import (
    DecisionType,
    GeneratedPatch,
    Plan,
    RetrievalContext,
    ReviewResult,
    Stage,
    Task,
    TaskResult,
    TaskStatus,
    VerificationResult,
)
from src.verification.reviewer import review_patch
from src.verification.static import run_static_analysis_in_sandbox
from src.verification.test_runner import run_pytest_in_sandbox


class AgentLoop:
    """Single-agent coding loop with explicit phases."""

    def __init__(
        self,
        codebase_path: str | Path | None = None,
        combo: str = "b",
        max_iterations: int | None = None,
        budget_usd: float | None = None,
        live_models: bool = False,
    ) -> None:
        self.codebase_path = Path(codebase_path or settings.target_codebase_path)
        self.combo = combo
        self.max_iterations = max_iterations or settings.max_iterations
        self.budget_usd = (
            budget_usd if budget_usd is not None else settings.cost_budget_per_task_usd
        )
        self.live_models = live_models

    def run(self, task_description: str, task_id: str = "adhoc") -> TaskResult:
        start = time.monotonic()
        task = Task(task_id=task_id, description=task_description)
        tracker = CostTracker(task_id=task_id)
        router = ModelRouter(combo=self.combo, tracker=tracker)
        generator = CodeGenerator(router=router, use_templates=not self.live_models)
        live_router = router if self.live_models else None
        plan = self._plan(task, live_router)
        log_phase(task_id, 0, "plan", plan.model_dump())
        if plan.is_impossible:
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.IMPOSSIBLE,
                run_mode=_run_mode(self.live_models),
                plan=plan,
                failure_reason=plan.impossible_reason or "Task is impossible",
                time_seconds=time.monotonic() - start,
            )

        if not self.codebase_path.exists():
            return TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                run_mode=_run_mode(self.live_models),
                plan=plan,
                failure_reason=f"Target codebase not found: {self.codebase_path}",
                time_seconds=time.monotonic() - start,
            )

        index = index_codebase(self.codebase_path)
        navigator = Navigator(index=index, router=live_router)
        prior_errors: list[str] = []
        failure_hints: list[str] = []
        last_patch: GeneratedPatch | None = None
        last_verification: VerificationResult | None = None
        retrieval = None
        iterations_run = 0
        retrieval_strategy = plan.retrieval_strategy
        preferred_files = list(plan.target_files)

        for iteration in range(1, self.max_iterations + 1):
            iterations_run = iteration
            if tracker.total() >= self.budget_usd:
                return self._budget_result(task_id, plan, retrieval, tracker, start)

            retrieval = navigator.retrieve_sync(
                task.description,
                strategy=retrieval_strategy,
                preferred_files=preferred_files,
                failure_hints=failure_hints,
                force_related_examples="related_examples" in task.description
                or "unreliable" in task.description,
            )
            log_phase(task_id, iteration, "act_retrieve", retrieval.model_dump())

            patch = generator.generate(
                task=task,
                plan=plan,
                context=retrieval,
                codebase_path=self.codebase_path,
                prior_errors=prior_errors,
            )
            last_patch = patch
            log_phase(
                task_id,
                iteration,
                "act_generate",
                patch.model_dump(),
                cost_usd=tracker.total(),
            )
            if _is_provider_error(patch.explanation):
                log_phase(
                    task_id,
                    iteration,
                    "observe_provider_failed",
                    {"stage": Stage.CODE_GENERATION.value, "error": patch.explanation[:1000]},
                )
                return self._provider_failure_result(
                    task_id=task_id,
                    plan=plan,
                    retrieval=retrieval,
                    patch=patch,
                    verification=None,
                    tracker=tracker,
                    start=start,
                    iteration=iteration,
                    stage=Stage.CODE_GENERATION,
                    error=patch.explanation,
                )

            if self.live_models and iteration > 1 and prior_errors:
                patch = generator.refactor(
                    task=task,
                    plan=plan,
                    context=retrieval,
                    patch=patch,
                    prior_errors=prior_errors,
                )
                last_patch = patch
                log_phase(
                    task_id,
                    iteration,
                    "act_refactor",
                    patch.model_dump(),
                    cost_usd=tracker.total(),
                )
                if _is_provider_error(patch.explanation):
                    log_phase(
                        task_id,
                        iteration,
                        "observe_provider_failed",
                        {"stage": Stage.REFACTORING.value, "error": patch.explanation[:1000]},
                    )
                    return self._provider_failure_result(
                        task_id=task_id,
                        plan=plan,
                        retrieval=retrieval,
                        patch=patch,
                        verification=None,
                        tracker=tracker,
                        start=start,
                        iteration=iteration,
                        stage=Stage.REFACTORING,
                        error=patch.explanation,
                    )

            review = review_patch(
                patch,
                retrieval,
                router=router,
                use_llm=False,
            )
            if not review.passed:
                if _is_provider_error(review.summary):
                    verification = VerificationResult(review=review)
                    log_phase(
                        task_id,
                        iteration,
                        "observe_provider_failed",
                        {"stage": Stage.LLM_REVIEW.value, "error": review.summary[:1000]},
                    )
                    return self._provider_failure_result(
                        task_id=task_id,
                        plan=plan,
                        retrieval=retrieval,
                        patch=patch,
                        verification=verification,
                        tracker=tracker,
                        start=start,
                        iteration=iteration,
                        stage=Stage.LLM_REVIEW,
                        error=review.summary,
                    )
                prior_errors.append(review.summary)
                failure_hints, suggested_files = self._classify_failures(
                    [review.summary],
                    live_router,
                )
                retrieval_strategy = self._next_retrieval_strategy(plan, failure_hints)
                preferred_files = self._expand_preferred_files(
                    preferred_files,
                    retrieval,
                    failure_hints,
                    suggested_files,
                )
                last_verification = VerificationResult(review=review)
                log_phase(task_id, iteration, "observe_review_failed", review.model_dump())
                log_phase(
                    task_id,
                    iteration,
                    "decide_retrieve_again",
                    {"failure_hints": failure_hints, "strategy": retrieval_strategy},
                )
                continue

            try:
                tests = run_pytest_in_sandbox(
                    self.codebase_path,
                    patch,
                    pytest_args=_pytest_args_from_patch(patch)
                    or _pytest_args_from_context(retrieval),
                )
                static = run_static_analysis_in_sandbox(self.codebase_path, patch)
                review = review_patch(
                    patch,
                    retrieval,
                    router=router,
                    use_llm=self.live_models,
                    allow_provider_fallback=True,
                )
            except Exception as exc:
                prior_errors.append(f"{type(exc).__name__}: {exc}")
                failure_hints, suggested_files = self._classify_failures([str(exc)], live_router)
                retrieval_strategy = self._next_retrieval_strategy(plan, failure_hints)
                preferred_files = self._expand_preferred_files(
                    preferred_files,
                    retrieval,
                    failure_hints,
                    suggested_files,
                )
                last_verification = VerificationResult(
                    review=ReviewResult(passed=False, issues=[str(exc)])
                )
                log_phase(task_id, iteration, "observe_exception", {"error": str(exc)})
                log_phase(
                    task_id,
                    iteration,
                    "decide_retrieve_again",
                    {"failure_hints": failure_hints, "strategy": retrieval_strategy},
                )
                if "timed out" in str(exc):
                    break
                continue

            verification = VerificationResult(static=static, tests=tests, review=review)
            last_verification = verification
            log_phase(task_id, iteration, "observe_verify", verification.model_dump())

            if verification.all_passed:
                cost = tracker.breakdown()
                return TaskResult(
                    task_id=task_id,
                    status=TaskStatus.DONE,
                    run_mode=_run_mode(self.live_models),
                    patch=patch,
                    generated_code=patch.unified_diff,
                    plan=plan,
                    retrieval=retrieval,
                    iterations_used=iteration,
                    verification=verification,
                    cost_breakdown=cost.cost_per_stage,
                    total_cost_usd=cost.total_cost_usd,
                    time_seconds=time.monotonic() - start,
                )
            verification_errors = _verification_errors(verification)
            prior_errors.extend(verification_errors)
            failure_hints, suggested_files = self._classify_failures(
                verification_errors,
                live_router,
            )
            retrieval_strategy = self._next_retrieval_strategy(plan, failure_hints)
            preferred_files = self._expand_preferred_files(
                preferred_files,
                retrieval,
                failure_hints,
                suggested_files,
            )
            log_phase(
                task_id,
                iteration,
                "decide_retrieve_again",
                {"failure_hints": failure_hints, "strategy": retrieval_strategy},
            )

        exhausted = iterations_run >= self.max_iterations
        stop_reason = (
            f"Exhausted {self.max_iterations} iterations"
            if exhausted
            else f"Stopped after {iterations_run} iterations"
        )
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            run_mode=_run_mode(self.live_models),
            patch=last_patch,
            generated_code=last_patch.unified_diff if last_patch else None,
            plan=plan,
            retrieval=retrieval,
            iterations_used=iterations_run,
            verification=last_verification,
            cost_breakdown=tracker.breakdown().cost_per_stage,
            total_cost_usd=tracker.total(),
            time_seconds=time.monotonic() - start,
            failure_reason=f"{stop_reason}. Last errors: {prior_errors[-3:]}",
        )

    def _plan(self, task: Task, router: ModelRouter | None = None) -> Plan:
        heuristic = self._heuristic_plan(task)
        if heuristic.is_impossible:
            return heuristic

        if router is not None and router.provider_available(Stage.IMPOSSIBLE_DETECT):
            impossible_check = router.call(
                Stage.IMPOSSIBLE_DETECT,
                _impossible_prompt(task, heuristic),
            )
            reason = _extract_text_field(impossible_check.content, "reason")
            heuristic_impossible = _heuristic_impossible_reason(task.description.lower())
            if _extract_bool_field(impossible_check.content, "impossible") and (
                _looks_like_impossible_reason(reason) or heuristic_impossible
            ):
                return Plan(
                    target_files=heuristic.target_files,
                    retrieval_strategy=heuristic.retrieval_strategy,
                    is_impossible=True,
                    impossible_reason=reason or heuristic.impossible_reason or "Task is impossible",
                )

        if router is not None and router.provider_available(Stage.PLANNING):
            planned = _merge_planner_response(
                heuristic,
                router.call(Stage.PLANNING, _planning_prompt(task, heuristic)).content,
            )
            return planned
        return heuristic

    def _heuristic_plan(self, task: Task) -> Plan:
        text = task.description.lower()
        impossible_reason = _heuristic_impossible_reason(text)
        if impossible_reason is not None:
            return Plan(
                target_files=[],
                retrieval_strategy="none",
                is_impossible=True,
                impossible_reason=impossible_reason,
            )
        targets = []
        if (
            "cachetransport" in text
            or "cache transport" in text
            or "cache-control" in text
        ):
            targets.extend(
                [
                    "httpx/_cache.py",
                    "httpx/__init__.py",
                    "httpx/_transports/base.py",
                    "tests/test_cache_transport.py",
                ]
            )
        if (
            "request id" in text
            or "request_id" in text
            or ("header" in text and "request" in text)
        ):
            targets.append("httpx/_client.py")
        for keyword, file_path in {
            "request": "httpx/_models.py",
            "response": "httpx/_models.py",
            "client": "httpx/_client.py",
            "transport": "httpx/_transports/base.py",
            "auth": "httpx/_auth.py",
            "url": "httpx/_urls.py",
        }.items():
            if keyword in text:
                targets.append(file_path)
        return Plan(
            target_files=sorted(set(targets)),
            retrieval_strategy=(
                "tree-first map -> module traversal -> tests -> hybrid vector fallback when "
                "ranking is weak"
            ),
        )

    def _classify_failures(
        self,
        errors: list[str],
        router: ModelRouter | None = None,
    ) -> tuple[list[str], list[str]]:
        hints = _heuristic_failure_hints(errors)
        suggested_files = _extract_file_hints(errors)
        if router is not None and errors and router.provider_available(Stage.ERROR_PARSING):
            response = router.call(Stage.ERROR_PARSING, _error_parser_prompt(errors))
            for hint in _extract_labels(response.content):
                if hint not in hints:
                    hints.append(hint)
            for file_path in _extract_csv_field(response.content, "files"):
                if file_path not in suggested_files:
                    suggested_files.append(file_path)
        if (
            router is not None
            and errors
            and _looks_like_test_failure(errors)
            and router.provider_available(Stage.TEST_ANALYSIS)
        ):
            response = router.call(Stage.TEST_ANALYSIS, _test_analysis_prompt(errors))
            for hint in _extract_labels(response.content):
                if hint not in hints:
                    hints.append(hint)
            for file_path in _extract_csv_field(response.content, "files"):
                if file_path not in suggested_files:
                    suggested_files.append(file_path)
        return hints, suggested_files

    def _next_retrieval_strategy(self, plan: Plan, failure_hints: list[str]) -> str:
        parts = ["tree-first map"]
        if plan.target_files:
            parts.append(f"focus files {', '.join(plan.target_files[:3])}")
        parts.append("list modules and inspect import chains")
        parts.append("retrieve focused tests")
        if any(hint in {"imports", "typing"} for hint in failure_hints):
            parts.append("follow import and reference edges more aggressively")
        if any(hint in {"tests", "logic"} for hint in failure_hints):
            parts.append("promote failing tests and related callsites")
        if any(hint in {"docs", "style", "logic"} for hint in failure_hints):
            parts.append("enable hybrid vector fallback for broader context")
        return " -> ".join(dict.fromkeys(parts))

    def _expand_preferred_files(
        self,
        preferred_files: list[str],
        retrieval: RetrievalContext | None,
        failure_hints: list[str],
        suggested_files: list[str],
    ) -> list[str]:
        if retrieval is None:
            return preferred_files[:6]
        expanded = list(preferred_files)
        for file_path in suggested_files:
            if file_path and file_path not in expanded:
                expanded.append(file_path)
        for unit in retrieval.units[:4]:
            if unit.file_path not in expanded:
                expanded.append(unit.file_path)
        if any(hint in {"tests", "logic"} for hint in failure_hints):
            for test in retrieval.tests:
                if not test.test_file:
                    continue
                for part in test.test_file.split(","):
                    path = part.strip()
                    if path and path not in expanded:
                        expanded.append(path)
        return expanded[:8]

    def _budget_result(
        self,
        task_id: str,
        plan: Plan,
        retrieval: RetrievalContext | None,
        tracker: CostTracker,
        start: float,
    ) -> TaskResult:
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            run_mode=_run_mode(self.live_models),
            plan=plan,
            retrieval=retrieval,
            cost_breakdown=tracker.breakdown().cost_per_stage,
            total_cost_usd=tracker.total(),
            time_seconds=time.monotonic() - start,
            failure_reason=f"Budget exceeded before completion: ${tracker.total():.4f}",
        )

    def _provider_failure_result(
        self,
        task_id: str,
        plan: Plan,
        retrieval: RetrievalContext | None,
        patch: GeneratedPatch | None,
        verification: VerificationResult | None,
        tracker: CostTracker,
        start: float,
        iteration: int,
        stage: Stage,
        error: str,
    ) -> TaskResult:
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILED,
            run_mode=_run_mode(self.live_models),
            patch=patch,
            generated_code=patch.unified_diff if patch else None,
            plan=plan,
            retrieval=retrieval,
            iterations_used=iteration,
            verification=verification,
            cost_breakdown=tracker.breakdown().cost_per_stage,
            total_cost_usd=tracker.total(),
            time_seconds=time.monotonic() - start,
            failure_reason=f"Provider failure during {stage.value}: {error[:1000]}",
        )


def _verification_errors(verification: VerificationResult) -> list[str]:
    errors: list[str] = []
    if verification.static and not verification.static.passed:
        errors.extend(error.message for error in verification.static.ruff_errors[:5])
        errors.extend(error.message for error in verification.static.mypy_errors[:5])
    if verification.tests and not verification.tests.passed:
        errors.extend(test.message for test in verification.tests.failed_tests[:5])
    if verification.review and not verification.review.passed:
        errors.extend(verification.review.issues)
    return errors or [f"verification failed with decision {DecisionType.RETRY.value}"]


def _heuristic_impossible_reason(text: str) -> str | None:
    """Catch obvious API-contract contradictions before touching the target tree."""
    destructive = any(
        token in text
        for token in ("remove", "removing", "delete", "drop", "eliminate", "disable", "sync only")
    )
    async_contract = any(
        token in text
        for token in (
            "async",
            "asyncclient",
            "async transport",
            "handle_async_request",
            "all requests synchronous",
        )
    )
    sync_contract = any(
        token in text
        for token in (
            "sync transport",
            "sync client",
            "client api",
            "all requests async",
            "remove client",
        )
    )
    if destructive and async_contract:
        return (
            "Removing httpx async support contradicts the dual sync/async public "
            "architecture and would require a full rewrite."
        )
    if destructive and sync_contract:
        return (
            "Removing httpx sync-client support contradicts the dual sync/async public "
            "architecture and would require a full rewrite."
        )
    return None


def _looks_like_impossible_reason(reason: str | None) -> bool:
    if not reason:
        return False
    lowered = reason.lower()
    return any(
        phrase in lowered
        for phrase in (
            "contradict",
            "existing tests",
            "public api",
            "public architecture",
            "full rewrite",
            "cannot be done",
            "impossible",
        )
    )


def _pytest_args_from_context(retrieval: RetrievalContext) -> list[str]:
    task_terms = {
        term
        for term in retrieval.task.lower().replace("_", " ").split()
        if len(term) > 2
    }
    test_files: list[str] = []
    for test in retrieval.tests:
        if not test.test_file:
            continue
        for part in test.test_file.split(","):
            path = part.strip()
            if path and not path.endswith("__init__.py") and path not in test_files:
                test_files.append(path)
    if not test_files:
        return ["tests"]
    ranked = sorted(
        test_files,
        key=lambda path: (
            -sum(term in path.lower() for term in task_terms),
            len(path),
            path,
        ),
    )
    return ranked[:2]


def _pytest_args_from_patch(patch: GeneratedPatch) -> list[str]:
    paths: list[str] = []
    for line in patch.unified_diff.splitlines():
        if not line.startswith("+++ b/tests/"):
            continue
        path = line.removeprefix("+++ b/")
        if path not in paths:
            paths.append(path)
    return paths


def _run_mode(live_models: bool) -> str:
    return "live" if live_models else "fixture"


def _is_provider_error(text: str) -> bool:
    return text.startswith("PROVIDER_ERROR:")


def _planning_prompt(task: Task, heuristic: Plan) -> str:
    return f"""You are planning retrieval for a Python codebase coding task.

Return exactly these fields on separate lines:
targets: comma-separated file paths or blank
retrieval: one short sentence
impossible: yes or no
reason: short explanation or blank

Task:
{task.description}

Heuristic targets:
{", ".join(heuristic.target_files) or "(none)"}

Current retrieval strategy:
{heuristic.retrieval_strategy}
"""


def _impossible_prompt(task: Task, heuristic: Plan) -> str:
    return f"""Assess whether this request contradicts the httpx architecture.

Return exactly:
impossible: yes or no
reason: one short sentence

Task:
{task.description}

Heuristic retrieval strategy:
{heuristic.retrieval_strategy}
"""


def _merge_planner_response(fallback: Plan, content: str) -> Plan:
    if content.startswith("PROVIDER_ERROR:"):
        return fallback

    planner_targets = _extract_csv_field(content, "targets")
    targets = _dedupe_paths([*fallback.target_files, *planner_targets])
    retrieval = _extract_text_field(content, "retrieval") or fallback.retrieval_strategy
    impossible = _extract_bool_field(content, "impossible") or fallback.is_impossible
    reason = _extract_text_field(content, "reason") or fallback.impossible_reason
    return Plan(
        target_files=targets,
        retrieval_strategy=retrieval,
        is_impossible=impossible,
        impossible_reason=reason,
    )


def _dedupe_paths(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(path for path in paths if path))


def _extract_csv_field(content: str, field: str) -> list[str]:
    value = _extract_text_field(content, field)
    if not value:
        return []
    if value in {"(none)", "none", "blank"}:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _extract_text_field(content: str, field: str) -> str | None:
    pattern = re.compile(rf"^{re.escape(field)}\s*:\s*(?P<value>.+)$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(content)
    if match is None:
        return None
    value = match.group("value").strip()
    if value.lower() in {"blank", "none", "n/a"}:
        return ""
    return value


def _extract_bool_field(content: str, field: str) -> bool:
    value = (_extract_text_field(content, field) or "").lower()
    return value.startswith("y") or value in {"true", "1"}


def _error_parser_prompt(errors: list[str]) -> str:
    joined = "\n".join(f"- {error}" for error in errors[:8])
    return f"""Classify these verification failures for a Python codebase agent.

Allowed labels: imports, typing, tests, style, logic, timeout, docs.
Return exactly:
labels: comma-separated labels
files: comma-separated file paths or blank

Errors:
{joined}
"""


def _test_analysis_prompt(errors: list[str]) -> str:
    joined = "\n".join(f"- {error}" for error in errors[:8])
    return f"""Analyze these failing Python test signals for a coding agent.

Allowed labels: imports, typing, tests, style, logic, timeout, docs.
Return exactly:
labels: comma-separated labels
files: comma-separated file paths or blank

Errors:
{joined}
"""


def _extract_labels(content: str) -> list[str]:
    allowed = {"imports", "typing", "tests", "style", "logic", "timeout", "docs"}
    labels = []
    for part in re.split(r"[\s,]+", content.lower()):
        token = part.strip().strip(".:")
        if token in allowed and token not in labels:
            labels.append(token)
    return labels


def _heuristic_failure_hints(errors: list[str]) -> list[str]:
    text = " ".join(errors).lower()
    hints: list[str] = []
    rules = (
        ("imports", ("importerror", "module not found", "nameerror", "attributeerror")),
        ("typing", ("mypy", "incompatible type", "unused \"type: ignore\"", "type error")),
        ("tests", ("assert", "failed", "pytest", "test_")),
        ("style", ("ruff", "lint", "format", "line too long")),
        ("timeout", ("timed out", "timeout", "deadline exceeded")),
        ("docs", ("convention", "docstring", "style guide")),
    )
    for label, needles in rules:
        if any(needle in text for needle in needles):
            hints.append(label)
    if not hints or ("tests" in hints and "logic" not in hints):
        hints.append("logic")
    return hints


def _extract_file_hints(errors: list[str]) -> list[str]:
    matches: list[str] = []
    pattern = re.compile(r"(?P<path>(?:tests|httpx|src)/[A-Za-z0-9_./-]+\.py)")
    for error in errors:
        for match in pattern.finditer(error):
            path = match.group("path")
            if path not in matches:
                matches.append(path)
    return matches


def _looks_like_test_failure(errors: list[str]) -> bool:
    text = " ".join(errors).lower()
    return any(token in text for token in ("assert", "pytest", "failed", "test_"))
