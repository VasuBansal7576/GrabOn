"""Provider smoke report helpers."""

from pathlib import Path

from src.eval import provider_smoke as provider_smoke_module
from src.eval.cost_report import build_cost_report
from src.eval.provider_smoke import _is_smoke_success, run_provider_smoke
from src.schemas import LLMResponse, Stage


def test_provider_smoke_accepts_tiny_ok_variants() -> None:
    assert _is_smoke_success("OK")
    assert _is_smoke_success("OK.")
    assert _is_smoke_success("ok!")
    assert not _is_smoke_success("Okay")


def test_provider_smoke_records_each_requested_stage(monkeypatch) -> None:
    class FakeRouter:
        def __init__(self, combo: str) -> None:
            self.combo = combo

        def provider_available(self, stage: Stage) -> bool:
            return True

        def call(self, stage: Stage, prompt: str) -> LLMResponse:
            return LLMResponse(
                content="OK",
                model=f"{self.combo}-{stage.value}",
                stage=stage,
                input_tokens=1,
                output_tokens=1,
            )

    monkeypatch.setattr(provider_smoke_module, "ModelRouter", FakeRouter)

    report = run_provider_smoke(
        ["a"],
        stages=[Stage.PLANNING, Stage.ERROR_PARSING],
    )

    assert report.successful_count == 2
    assert [result.stage for result in report.results] == [
        Stage.PLANNING,
        Stage.ERROR_PARSING,
    ]


def test_cost_report_separates_live_and_fixture_costs(tmp_path: Path) -> None:
    (tmp_path / "fixture.json").write_text(
        """
        {
          "combo": "a",
          "run_mode": "fixture",
          "provider_models": [],
          "pass_rate": "1/1",
          "total_cost_usd": 0.0,
          "tasks": []
        }
        """,
        encoding="utf-8",
    )
    (tmp_path / "smoke.json").write_text(
        """
        {
          "prompt": "OK?",
          "successful_count": 1,
          "results": [
            {
              "combo": "a",
              "stage": "planning",
              "model": "gemini-flash",
              "status": "ok",
              "provider_available": true,
              "input_tokens": 2,
              "output_tokens": 1,
              "cost_usd": 0.25
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    summary = build_cost_report(tmp_path)

    assert summary["measured_live_report_cost_usd"] == 0.25
    assert summary["measured_fixture_report_cost_usd"] == 0.0
