"""Static analysis runner with deterministic output parsing."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections import Counter
from functools import lru_cache
from pathlib import Path

from src.schemas import GeneratedPatch, LintError, MypyError, StaticAnalysisResult

RUFF_RE = re.compile(r"^(?P<file>.*?):(?P<line>\d+):(?P<col>\d+): (?P<code>\S+) (?P<msg>.*)$")
MYPY_RE = re.compile(
    r"^(?P<file>.*?):(?P<line>\d+): (?P<level>error): (?P<msg>.*?)(?:  \[(?P<code>.*?)\])?$"
)


def run_static_analysis(path: str | Path, timeout_seconds: int = 30) -> StaticAnalysisResult:
    """Run ruff and mypy in a directory and parse errors without LLMs."""
    cwd = Path(path)
    ruff_errors = _run_ruff(cwd, timeout_seconds)
    mypy_errors = _run_mypy(cwd, timeout_seconds)
    error_count = len(ruff_errors) + len(mypy_errors)
    return StaticAnalysisResult(
        passed=error_count == 0,
        ruff_errors=ruff_errors,
        mypy_errors=mypy_errors,
        error_count=error_count,
    )


def run_static_analysis_in_sandbox(
    codebase_path: str | Path,
    patch: GeneratedPatch | str | None = None,
    timeout_seconds: int = 30,
) -> StaticAnalysisResult:
    """Apply a patch in a temp copy and fail only on errors beyond the baseline.

    Some real upstream targets already carry unrelated static-analysis noise in
    their pinned environment. For patch verification we compare the patched tree
    against the untouched baseline and only surface newly introduced issues.
    """
    source = Path(codebase_path).resolve()
    temp_parent = Path(tempfile.mkdtemp(prefix="grabonai-static-"))
    sandbox = temp_parent / source.name
    try:
        ignore = shutil.ignore_patterns(".git", ".venv", "venv", "__pycache__", ".mypy_cache")
        shutil.copytree(source, sandbox, ignore=ignore)
        diff = patch.unified_diff if isinstance(patch, GeneratedPatch) else patch
        if diff:
            _apply_patch(sandbox, diff)
        baseline = _baseline_static_analysis(source, timeout_seconds)
        candidate = run_static_analysis(sandbox, timeout_seconds=timeout_seconds)
        return subtract_static_baseline(candidate, baseline)
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)


@lru_cache(maxsize=8)
def _baseline_static_analysis(codebase_path: Path, timeout_seconds: int) -> StaticAnalysisResult:
    return run_static_analysis(codebase_path, timeout_seconds=timeout_seconds)


def _run_ruff(cwd: Path, timeout_seconds: int) -> list[LintError]:
    if shutil.which("ruff") is None:
        return []
    proc = subprocess.run(
        ["ruff", "check", "."],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return parse_ruff_output(proc.stdout + proc.stderr)


def _run_mypy(cwd: Path, timeout_seconds: int) -> list[MypyError]:
    if shutil.which("mypy") is None:
        return []
    proc = subprocess.run(
        ["mypy", "."],
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    return parse_mypy_output(proc.stdout + proc.stderr)


def _apply_patch(cwd: Path, unified_diff: str) -> None:
    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "--recount", "-"],
        cwd=cwd,
        input=unified_diff,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Patch failed to apply: {proc.stderr.strip() or proc.stdout.strip()}")


def subtract_static_baseline(
    candidate: StaticAnalysisResult,
    baseline: StaticAnalysisResult,
) -> StaticAnalysisResult:
    ruff_errors = _subtract_lint_errors(candidate.ruff_errors, baseline.ruff_errors)
    mypy_errors = _subtract_mypy_errors(candidate.mypy_errors, baseline.mypy_errors)
    error_count = len(ruff_errors) + len(mypy_errors)
    return StaticAnalysisResult(
        passed=error_count == 0,
        ruff_errors=ruff_errors,
        mypy_errors=mypy_errors,
        error_count=error_count,
    )


def _subtract_lint_errors(
    candidate: list[LintError],
    baseline: list[LintError],
) -> list[LintError]:
    remaining = Counter(_lint_error_key(error) for error in baseline)
    delta: list[LintError] = []
    for error in candidate:
        key = _lint_error_key(error)
        if remaining[key] > 0:
            remaining[key] -= 1
            continue
        delta.append(error)
    return delta


def _subtract_mypy_errors(
    candidate: list[MypyError],
    baseline: list[MypyError],
) -> list[MypyError]:
    remaining = Counter(_mypy_error_key(error) for error in baseline)
    delta: list[MypyError] = []
    for error in candidate:
        key = _mypy_error_key(error)
        if remaining[key] > 0:
            remaining[key] -= 1
            continue
        delta.append(error)
    return delta


def _lint_error_key(error: LintError) -> tuple[str, str, str]:
    return (error.file, error.code, error.message)


def _mypy_error_key(error: MypyError) -> tuple[str, str, str]:
    return (error.file, error.code, error.message)


def parse_ruff_output(output: str) -> list[LintError]:
    """Parse standard ruff line output."""
    errors: list[LintError] = []
    for line in output.splitlines():
        match = RUFF_RE.match(line.strip())
        if not match:
            continue
        errors.append(
            LintError(
                file=match.group("file"),
                line=int(match.group("line")),
                column=int(match.group("col")),
                code=match.group("code"),
                message=match.group("msg"),
            )
        )
    return errors


def parse_mypy_output(output: str) -> list[MypyError]:
    """Parse standard mypy line output."""
    errors: list[MypyError] = []
    for line in output.splitlines():
        match = MYPY_RE.match(line.strip())
        if not match:
            continue
        errors.append(
            MypyError(
                file=match.group("file"),
                line=int(match.group("line")),
                code=match.group("code") or "mypy",
                message=match.group("msg"),
            )
        )
    return errors
