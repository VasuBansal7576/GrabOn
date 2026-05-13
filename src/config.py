"""GrabOn AI Coder — Configuration via Pydantic Settings.

All environment variables loaded from .env file or system environment.
Type-safe, validated at startup. No raw os.environ access anywhere else.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- LLM Provider Keys ---
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude models")
    google_api_key: str = Field(default="", description="Google API key for Gemini models")
    groq_api_key: str = Field(default="", description="Groq API key for Llama models")
    nvidia_api_key: str = Field(default="", description="NVIDIA API key for hosted NIM models")
    gemini_model: str = Field(
        default="gemini-2.5-flash-lite",
        description="Hosted Gemini model used by the Gemini live route",
    )
    nvidia_model: str = Field(
        default="mistralai/mistral-small-4-119b-2603",
        description="Hosted NVIDIA NIM chat model used by the NVIDIA live route",
    )
    nvidia_input_cost_per_1k: float = Field(
        default=0.0,
        description=(
            "Observed/declared NVIDIA NIM input price per 1K tokens; "
            "free tier defaults to 0"
        ),
    )
    nvidia_output_cost_per_1k: float = Field(
        default=0.0,
        description=(
            "Observed/declared NVIDIA NIM output price per 1K tokens; "
            "free tier defaults to 0"
        ),
    )

    # --- Target Codebase ---
    target_codebase_path: Path = Field(
        default=Path("./target/httpx"),
        description="Path to the target codebase to index and operate on",
    )

    # --- Agent Configuration ---
    log_level: str = Field(default="INFO", description="Logging level")
    max_iterations: int = Field(default=5, description="Max iterations per task")
    cost_budget_per_task_usd: float = Field(
        default=0.50, description="Max cost in USD per task before halting"
    )
    max_tool_calls_per_task: int = Field(
        default=50, description="Max tool calls per task before halting"
    )
    max_wall_clock_seconds: int = Field(
        default=300, description="Max wall-clock time per task in seconds"
    )
    max_consecutive_failures: int = Field(
        default=3, description="Max consecutive failures before re-planning"
    )

    # --- Cache ---
    cache_dir: Path = Field(default=Path(".cache"), description="Directory for index cache")
    index_cache_enabled: bool = Field(default=True, description="Enable index cache")
    queue_state_path: Path = Field(
        default=Path(".cache/task_queue_state.json"),
        description="Path for persisted task queue snapshots",
    )

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_google(self) -> bool:
        return bool(self.google_api_key)

    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def has_nvidia(self) -> bool:
        return bool(self.nvidia_api_key)


# Singleton instance — import this everywhere
settings = Settings()
