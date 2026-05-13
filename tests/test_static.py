"""Tests for static-analysis baseline subtraction."""

from __future__ import annotations

from src.schemas import LintError, MypyError, StaticAnalysisResult
from src.verification.static import subtract_static_baseline
from src.verification.test_runner import _apply_patch


def test_subtract_static_baseline_filters_preexisting_errors() -> None:
    baseline = StaticAnalysisResult(
        passed=False,
        ruff_errors=[
            LintError(file="pkg/mod.py", line=10, column=1, code="F401", message="unused import")
        ],
        mypy_errors=[
            MypyError(
                file="pkg/mod.py",
                line=42,
                code="unused-ignore",
                message='Unused "type: ignore" comment',
            )
        ],
        error_count=2,
    )
    candidate = StaticAnalysisResult(
        passed=False,
        ruff_errors=[
            LintError(file="pkg/mod.py", line=12, column=1, code="F401", message="unused import"),
            LintError(file="pkg/new.py", line=3, column=5, code="F821", message="undefined name"),
        ],
        mypy_errors=[
            MypyError(
                file="pkg/mod.py",
                line=50,
                code="unused-ignore",
                message='Unused "type: ignore" comment',
            ),
            MypyError(file="pkg/new.py", line=7, code="attr-defined", message="Missing attribute"),
        ],
        error_count=4,
    )

    result = subtract_static_baseline(candidate, baseline)

    assert result.passed is False
    assert result.error_count == 2
    assert [error.code for error in result.ruff_errors] == ["F821"]
    assert [error.code for error in result.mypy_errors] == ["attr-defined"]


def test_apply_patch_recounts_bad_live_model_hunk_headers(tmp_path) -> None:
    patch = (
        "--- /dev/null\n"
        "+++ b/new_module.py\n"
        "@@ -0,0 +1,99 @@\n"
        "+VALUE = 1\n"
        "+OTHER = 2\n"
    )

    _apply_patch(tmp_path, patch)

    assert (tmp_path / "new_module.py").read_text(encoding="utf-8") == (
        "VALUE = 1\nOTHER = 2\n"
    )
