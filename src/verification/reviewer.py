"""Lightweight reviewer for generated patches."""

from __future__ import annotations

import re

from src.agent.router import ModelRouter
from src.schemas import GeneratedPatch, RetrievalContext, ReviewResult, Stage


def review_patch(
    patch: GeneratedPatch,
    context: RetrievalContext | None = None,
    router: ModelRouter | None = None,
    use_llm: bool = False,
    allow_provider_fallback: bool = False,
) -> ReviewResult:
    """Review a patch for obvious risks before marking a task done.

    The deterministic pass always runs first. In live mode a routed reviewer
    model must also return a parseable PASS/FAIL verdict.
    """
    issues: list[str] = []
    diff = patch.unified_diff
    if patch.explanation.startswith("PROVIDER_ERROR:"):
        issues.append(patch.explanation)
    if not diff.strip():
        issues.append("empty patch")
    if "TODO" in diff or "pass  # TODO" in diff:
        issues.append("patch contains TODO placeholder")
    if _introduces_wildcard_import(diff):
        issues.append("wildcard import introduced outside package export file")
    if _changes_behavior_without_tests(diff):
        issues.append("behavioral source patch must add or update focused tests")
    if context is not None and not context.units:
        issues.append("patch generated without retrieved code context")
    if issues:
        return ReviewResult(passed=False, issues=issues, summary="; ".join(issues))

    if not use_llm:
        return ReviewResult(passed=True, summary="passed deterministic review")

    if router is None:
        return ReviewResult(
            passed=False,
            issues=["live reviewer requested without a model router"],
            summary="live reviewer unavailable",
        )

    response = router.call(Stage.LLM_REVIEW, _review_prompt(patch, context))
    if response.content.startswith("PROVIDER_ERROR:") and allow_provider_fallback:
        return ReviewResult(
            passed=True,
            summary=(
                "passed deterministic review; live reviewer unavailable: "
                f"{response.content[:300]}"
            ),
        )
    verdict = _parse_review_response(response.content)
    if verdict.passed:
        verdict.summary = f"LLM reviewer passed via {response.model}: {verdict.summary}"
    return verdict


def _introduces_wildcard_import(diff: str) -> bool:
    current_file = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line.removeprefix("+++ b/")
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        if re.search(r"from\s+\S+\s+import\s+\*", line) and not current_file.endswith(
            "__init__.py"
        ):
            return True
    return False


def _changes_behavior_without_tests(diff: str) -> bool:
    paths = _changed_paths(diff)
    source_changed = any(path.startswith("httpx/") for path in paths)
    tests_changed = any(path.startswith("tests/") for path in paths)
    return source_changed and not tests_changed


def _changed_paths(diff: str) -> list[str]:
    return [
        line.removeprefix("+++ b/")
        for line in diff.splitlines()
        if line.startswith("+++ b/")
    ]


def _review_prompt(patch: GeneratedPatch, context: RetrievalContext | None) -> str:
    units = []
    if context is not None:
        units = [unit.unit_id for unit in context.units[:8]]
    return f"""You are reviewing a generated patch for a Python library.

Return exactly one of these formats:
PASS: one sentence explaining why the patch is acceptable
FAIL: semicolon-separated concrete issues

Check for bugs, security risks, hallucinated imports, unrelated files, and
violations of the surrounding codebase conventions.
A test-only patch is acceptable when it adds focused tests for existing
behavior. Do not fail it for not changing implementation code.
If retrieved units are nearby but not exact, judge the patch against the task
and public API instead of failing only because the retrieved unit names differ.

Retrieved units:
{chr(10).join(units)}

Patch:
{patch.unified_diff}
"""


def _parse_review_response(content: str) -> ReviewResult:
    text = content.strip()
    if text.startswith("PROVIDER_ERROR:"):
        return ReviewResult(passed=False, issues=[text], summary=text)
    first_line = text.splitlines()[0] if text else ""
    upper = first_line.upper()
    if upper.startswith("PASS"):
        return ReviewResult(passed=True, summary=first_line)
    if upper.startswith("FAIL"):
        detail = first_line.split(":", 1)[1] if ":" in first_line else first_line[4:]
        issues = [
            issue.strip(" :-")
            for issue in detail.split(";")
            if issue.strip(" :-")
        ]
        return ReviewResult(
            passed=False,
            issues=issues or [first_line],
            summary=first_line,
        )
    return ReviewResult(
        passed=False,
        issues=["LLM reviewer returned an unparseable verdict"],
        summary=text[:500],
    )
