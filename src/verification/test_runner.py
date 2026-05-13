"""Pytest runner that verifies patches in a temporary sandbox."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from src.schemas import FailedTest, GeneratedPatch, TestRunResult


def run_pytest_in_sandbox(
    codebase_path: str | Path,
    patch: GeneratedPatch | str | None = None,
    pytest_args: list[str] | None = None,
    timeout_seconds: int = 60,
) -> TestRunResult:
    """Copy codebase to a temp dir, apply patch, run pytest, and clean up."""
    source = Path(codebase_path).resolve()
    start = time.monotonic()
    temp_parent = Path(tempfile.mkdtemp(prefix="grabonai-verify-"))
    sandbox = temp_parent / source.name
    try:
        ignore = shutil.ignore_patterns(".git", ".venv", "venv", "__pycache__", ".mypy_cache")
        shutil.copytree(source, sandbox, ignore=ignore)
        diff = patch.unified_diff if isinstance(patch, GeneratedPatch) else patch
        if diff:
            _apply_patch(sandbox, diff)
        report_path = sandbox / ".pytest_report.json"
        args = pytest_args or ["tests"]
        command = [
            "python",
            "-m",
            "pytest",
            *args,
            "--json-report",
            f"--json-report-file={report_path}",
        ]
        proc = subprocess.run(
            command,
            cwd=sandbox,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if report_path.exists():
            return _parse_json_report(report_path, time.monotonic() - start)
        return _fallback_result(
            proc.returncode,
            proc.stdout + proc.stderr,
            time.monotonic() - start,
        )
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)


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


def _parse_json_report(path: Path, duration_seconds: float) -> TestRunResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    failed_tests = []
    for test in data.get("tests", []):
        if test.get("outcome") in {"failed", "error"}:
            failed_tests.append(
                FailedTest(
                    name=test.get("nodeid", "unknown"),
                    message=str(test.get("call", {}).get("crash", {}).get("message", "")),
                    longrepr=str(test.get("call", {}).get("longrepr", "")),
                )
            )
    failed = int(summary.get("failed", 0)) + int(summary.get("error", 0))
    passed = int(summary.get("passed", 0))
    total = int(summary.get("total", passed + failed))
    return TestRunResult(
        passed=failed == 0,
        tests_run=total,
        tests_passed=passed,
        tests_failed=failed,
        failed_tests=failed_tests,
        duration_seconds=duration_seconds,
    )


def _fallback_result(returncode: int, output: str, duration_seconds: float) -> TestRunResult:
    return TestRunResult(
        passed=returncode == 0,
        tests_run=0,
        tests_passed=0,
        tests_failed=0 if returncode == 0 else 1,
        failed_tests=[] if returncode == 0 else [FailedTest(name="pytest", message=output[-2000:])],
        duration_seconds=duration_seconds,
    )
