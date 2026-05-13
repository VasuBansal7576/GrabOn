"""Live-provider smoke reports."""

from __future__ import annotations

import re
from pathlib import Path

from src.agent.router import ModelRouter
from src.schemas import ProviderSmokeReport, ProviderSmokeResult, Stage

DEFAULT_PROMPT = "Reply with exactly OK."
_OK_RE = re.compile(r"^OK[.!]?$", re.IGNORECASE)


def run_provider_smoke(
    combos: list[str],
    output: str | Path | None = None,
    prompt: str = DEFAULT_PROMPT,
    stages: list[Stage] | None = None,
) -> ProviderSmokeReport:
    """Call each configured provider/stage route and persist honest raw evidence."""
    results: list[ProviderSmokeResult] = []
    selected_stages = stages or [Stage.PLANNING]
    for combo in combos:
        router = ModelRouter(combo=combo)
        for stage in selected_stages:
            provider_available = router.provider_available(stage)
            response = router.call(stage, prompt)
            content = response.content.strip()
            provider_error = content.startswith("PROVIDER_ERROR:")
            status = (
                "ok"
                if _is_smoke_success(content)
                else "error"
                if provider_error
                else "unexpected"
            )
            results.append(
                ProviderSmokeResult(
                    combo=combo,
                    stage=stage,
                    model=response.model,
                    status=status,
                    provider_available=provider_available,
                    content_preview="" if provider_error else content[:240],
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cost_usd=response.cost_usd,
                    latency_ms=response.latency_ms,
                    error=content if provider_error else None,
                )
            )

    report = ProviderSmokeReport(
        prompt=prompt,
        successful_count=sum(1 for result in results if result.status == "ok"),
        results=results,
    )
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def _is_smoke_success(content: str) -> bool:
    """Accept tiny punctuation drift without calling a healthy provider broken."""
    return bool(_OK_RE.fullmatch(content.strip()))
