"""Aggregate measured cost evidence from raw report files."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.schemas import BenchmarkReport, ProviderSmokeReport


def build_cost_report(
    reports_dir: str | Path = "reports",
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize measured benchmark/provider costs without hiding fixture zeros."""
    root = Path(reports_dir)
    benchmark_reports: list[dict[str, Any]] = []
    smoke_reports: list[dict[str, Any]] = []
    measured_live_cost = 0.0
    measured_fixture_cost = 0.0
    measured_input_tokens = 0
    measured_output_tokens = 0

    for path in sorted(root.glob("*.json")):
        payload = path.read_text(encoding="utf-8")
        parsed = json.loads(payload)
        if "pass_rate" in parsed and "tasks" in parsed:
            benchmark = BenchmarkReport.model_validate(parsed)
            entry = {
                "path": path.as_posix(),
                "type": "benchmark",
                "combo": benchmark.combo,
                "run_mode": benchmark.run_mode,
                "pass_rate": benchmark.pass_rate,
                "total_cost_usd": benchmark.total_cost_usd,
                "avg_cost_usd": benchmark.avg_cost_usd,
                "avg_time_seconds": benchmark.avg_time_seconds,
                "task_count": len(benchmark.tasks),
            }
            benchmark_reports.append(entry)
            if benchmark.run_mode == "live":
                measured_live_cost += benchmark.total_cost_usd
            else:
                measured_fixture_cost += benchmark.total_cost_usd
            continue
        if "successful_count" in parsed and "results" in parsed:
            smoke = ProviderSmokeReport.model_validate(parsed)
            report_cost = sum(result.cost_usd for result in smoke.results)
            report_input = sum(result.input_tokens for result in smoke.results)
            report_output = sum(result.output_tokens for result in smoke.results)
            smoke_reports.append(
                {
                    "path": path.as_posix(),
                    "type": "provider_smoke",
                    "successful_count": smoke.successful_count,
                    "total_cost_usd": report_cost,
                    "input_tokens": report_input,
                    "output_tokens": report_output,
                    "models": sorted({result.model for result in smoke.results}),
                    "stages": sorted({result.stage.value for result in smoke.results}),
                }
            )
            measured_live_cost += report_cost
            measured_input_tokens += report_input
            measured_output_tokens += report_output

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "method": (
            "Aggregates costs embedded in raw benchmark and provider-smoke JSON. "
            "Fixture reports are intentionally counted separately because they "
            "do not call paid APIs."
        ),
        "measured_live_report_cost_usd": round(measured_live_cost, 8),
        "measured_fixture_report_cost_usd": round(measured_fixture_cost, 8),
        "measured_provider_smoke_input_tokens": measured_input_tokens,
        "measured_provider_smoke_output_tokens": measured_output_tokens,
        "benchmark_reports": benchmark_reports,
        "provider_smoke_reports": smoke_reports,
        "submission_note": (
            "Use this for per-run repo evidence. Add provider-dashboard totals separately "
            "for the full development-process cost required by the PDF."
        ),
    }
    if output is not None:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
