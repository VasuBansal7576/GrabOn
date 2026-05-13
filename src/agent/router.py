"""Multi-model router and cost tracker."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.config import settings
from src.schemas import CostBreakdown, LLMCall, LLMResponse, Stage

PRICES_PER_1K: dict[str, tuple[float, float]] = {
    "fake": (0.0, 0.0),
    "claude-haiku": (0.0008, 0.004),
    "claude-sonnet": (0.003, 0.015),
    "gemini-flash": (0.0001, 0.0004),
    "groq-llama-8b": (0.00005, 0.00008),
    "groq-llama-70b": (0.00059, 0.00079),
}


@dataclass
class CostTracker:
    """Records every model call for a task."""

    task_id: str
    calls: list[LLMCall] = field(default_factory=list)

    def record(self, response: LLMResponse) -> None:
        call = LLMCall(
            model=response.model,
            stage=response.stage,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            latency_ms=response.latency_ms,
        )
        self.calls.append(call)

    def total(self) -> float:
        return sum(call.cost_usd for call in self.calls)

    def breakdown(self) -> CostBreakdown:
        by_stage: dict[str, float] = {}
        for call in self.calls:
            by_stage[call.stage.value] = by_stage.get(call.stage.value, 0.0) + call.cost_usd
        return CostBreakdown(
            task_id=self.task_id,
            calls=self.calls,
            cost_per_stage=by_stage,
            total_cost_usd=sum(by_stage.values()),
        )


class ModelRouter:
    """Routes stages to configured models.

    Live providers are optional. Without API keys this router returns a
    structured provider error so offline and live runs cannot be confused.
    """

    def __init__(self, combo: str = "b", tracker: CostTracker | None = None) -> None:
        self.combo = combo
        self.tracker = tracker

    def model_for(self, stage: Stage) -> str:
        if self.combo.lower() in {"n", "nv", "nvidia"}:
            return "nvidia-chat"
        if self.combo.lower() in {"g", "groq"}:
            if stage in {Stage.CONTEXT_RANKING, Stage.ERROR_PARSING, Stage.LLM_REVIEW}:
                return "groq-llama-8b"
            return "groq-llama-70b"
        if self.combo.lower() == "a":
            return "gemini-flash"
        if stage in {
            Stage.CONTEXT_RANKING,
            Stage.ERROR_PARSING,
            Stage.TEST_ANALYSIS,
            Stage.LLM_REVIEW,
        }:
            return "claude-haiku"
        return "claude-sonnet"

    def provider_available(self, stage: Stage) -> bool:
        """Return whether the configured provider for a stage can be called live."""
        return self._provider_available_for_model(self.model_for(stage))

    def provider_models(self) -> list[str]:
        """List models whose providers are configured in the current environment."""
        models = {
            self.model_for(Stage.PLANNING),
            self.model_for(Stage.CONTEXT_RANKING),
            self.model_for(Stage.CODE_GENERATION),
            self.model_for(Stage.LLM_REVIEW),
        }
        return sorted(model for model in models if self._provider_available_for_model(model))

    def call(self, stage: Stage, prompt: str) -> LLMResponse:
        model = self.model_for(stage)
        start = time.monotonic()
        content = self._call_provider(model, prompt, stage)
        input_tokens = _estimate_tokens(prompt)
        output_tokens = _estimate_tokens(content)
        cost = 0.0 if content.startswith("PROVIDER_ERROR:") else _estimate_cost(
            model,
            input_tokens,
            output_tokens,
        )
        response = LLMResponse(
            content=content,
            model=model,
            stage=stage,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=(time.monotonic() - start) * 1000,
        )
        if self.tracker is not None:
            self.tracker.record(response)
        return response

    def _provider_available_for_model(self, model: str) -> bool:
        if model.startswith("claude"):
            return settings.has_anthropic
        if model.startswith("gemini"):
            return settings.has_google
        if model.startswith("groq"):
            return settings.has_groq
        if model.startswith("nvidia"):
            return settings.has_nvidia
        return False

    def _call_provider(self, model: str, prompt: str, stage: Stage) -> str:
        if model.startswith("claude") and settings.has_anthropic:
            return _call_anthropic(model, prompt)
        if model.startswith("gemini") and settings.has_google:
            return _call_gemini(model, prompt, stage)
        if model.startswith("groq") and settings.has_groq:
            return _call_groq(model, prompt)
        if model.startswith("nvidia") and settings.has_nvidia:
            return _call_nvidia(model, prompt, stage)
        return f"PROVIDER_ERROR: missing API key for {model}"


def _call_anthropic(model: str, prompt: str) -> str:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        model_name = "claude-3-5-haiku-latest" if "haiku" in model else "claude-sonnet-4-5"
        message = client.messages.create(
            model=model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(str(getattr(block, "text", "")) for block in message.content)
    except Exception as exc:
        return f"PROVIDER_ERROR: {type(exc).__name__}: {exc}"


def _call_gemini(model: str, prompt: str, stage: Stage) -> str:
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.google_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=_gemini_max_tokens(stage),
            ),
        )
        return response.text or ""
    except Exception as exc:
        return f"PROVIDER_ERROR: {type(exc).__name__}: {exc}"


def _call_nvidia(model: str, prompt: str, stage: Stage) -> str:
    try:
        from openai import OpenAI

        model_name = _nvidia_model_name(model)
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=settings.nvidia_api_key,
            timeout=120.0,
            max_retries=0,
        )
        if model_name.startswith(("deepseek-ai/", "minimaxai/", "qwen/")):
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                top_p=1,
                max_tokens=_nvidia_max_tokens(stage),
                extra_body={"chat_template_kwargs": {"thinking": False}},
                stream=False,
            )
        else:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                top_p=1,
                max_tokens=_nvidia_max_tokens(stage),
                stream=False,
            )
        if not response.choices:
            return ""
        return response.choices[0].message.content or ""
    except Exception as exc:
        return f"PROVIDER_ERROR: {type(exc).__name__}: {exc}"


def _call_groq(model: str, prompt: str) -> str:
    try:
        from groq import Groq

        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=_groq_model_name(model),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            top_p=0.95,
            max_tokens=4096,
        )
        content = response.choices[0].message.content if response.choices else ""
        return content or ""
    except Exception as exc:
        return f"PROVIDER_ERROR: {type(exc).__name__}: {exc}"


def _nvidia_model_name(model: str) -> str:
    if model == "nvidia-chat":
        return settings.nvidia_model
    return model


def _nvidia_max_tokens(stage: Stage) -> int:
    if stage in {Stage.CODE_GENERATION, Stage.REFACTORING}:
        return 8192
    return 512


def _gemini_max_tokens(stage: Stage) -> int:
    if stage in {Stage.CODE_GENERATION, Stage.REFACTORING}:
        return 4096
    return 512


def _groq_model_name(model: str) -> str:
    if model == "groq-llama-8b":
        return "llama-3.1-8b-instant"
    if model == "groq-llama-70b":
        return "llama-3.3-70b-versatile"
    return model


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 4 // 3)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model == "nvidia-chat":
        return (
            input_tokens / 1000 * settings.nvidia_input_cost_per_1k
            + output_tokens / 1000 * settings.nvidia_output_cost_per_1k
        )
    in_price, out_price = PRICES_PER_1K.get(model, PRICES_PER_1K["fake"])
    return (input_tokens / 1000 * in_price) + (output_tokens / 1000 * out_price)
