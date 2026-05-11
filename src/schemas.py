"""GrabOn AI Coder — Shared Pydantic Schemas.

All inter-module data structures defined here.
No raw dicts passed between phases — Pydantic models only (Critical Rule 7).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    """Status of a task in the queue."""
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    IMPOSSIBLE = "impossible"


class Stage(str, Enum):
    """Agent pipeline stages for model routing and cost tracking."""
    CONTEXT_RANKING = "context_ranking"
    ERROR_PARSING = "error_parsing"
    CODE_GENERATION = "code_generation"
    REFACTORING = "refactoring"
    LLM_REVIEW = "llm_review"
    IMPOSSIBLE_DETECT = "impossible_detect"
    PLANNING = "planning"


class DecisionType(str, Enum):
    """Decision outcomes from the DECIDE phase."""
    DONE = "done"
    RETRY = "retry"
    RE_RETRIEVE = "re_retrieve"
    IMPOSSIBLE = "impossible"
    EXHAUSTED = "exhausted"


class Difficulty(str, Enum):
    """Task difficulty levels."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    IMPOSSIBLE = "impossible"


# ---------------------------------------------------------------------------
# Indexer Models
# ---------------------------------------------------------------------------

class ParsedUnit(BaseModel):
    """A single structural unit extracted from the codebase via tree-sitter."""
    unit_id: str = Field(description='Qualified name, e.g. "httpx._client.Client.send"')
    unit_type: str = Field(description='"function" | "class" | "method"')
    file_path: str = Field(description="Relative path from codebase root")
    name: str
    signature: str = Field(description="Full def/class line")
    docstring: str | None = None
    body: str = Field(description="Full source code")
    line_start: int
    line_end: int
    imports: list[str] = Field(default_factory=list, description="Imports used in this unit")
    parent_class: str | None = None
    test_file: str | None = None


class ModuleNode(BaseModel):
    """A module (file) in the tree index."""
    file_path: str
    docstring: str | None = None
    imports: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list, description="Class unit_ids")
    functions: list[str] = Field(default_factory=list, description="Function unit_ids")


class TreeIndex(BaseModel):
    """Hierarchical codebase index built from tree-sitter AST."""
    modules: dict[str, ModuleNode] = Field(description="file_path → ModuleNode")
    units: dict[str, ParsedUnit] = Field(description="unit_id → ParsedUnit")
    import_graph: dict[str, list[str]] = Field(description="unit_id → list of imported unit_ids")
    test_map: dict[str, str] = Field(description="unit_id → test_file_path")


# ---------------------------------------------------------------------------
# Retrieval Tool Result Models
# ---------------------------------------------------------------------------

class ModuleListing(BaseModel):
    """Result of ls_module tool."""
    file_path: str
    functions: list[str]
    classes: list[str]


class FunctionResult(BaseModel):
    """Result of get_function tool."""
    unit_id: str
    signature: str
    body: str
    docstring: str | None = None
    file_path: str
    line_start: int
    line_end: int


class ClassResult(BaseModel):
    """Result of get_class tool."""
    unit_id: str
    definition: str
    methods: list[str]
    bases: list[str]


class ReferenceResult(BaseModel):
    """Result of find_references tool."""
    name: str
    references: list[str] = Field(description="List of unit_ids referencing this name")


class ImportResult(BaseModel):
    """Result of get_imports tool."""
    file_path: str
    imports: list[str]
    imported_by: list[str]


class TestResult(BaseModel):
    """Result of get_tests_for tool."""
    unit_id: str
    test_file: str | None = None
    test_functions: list[str] = Field(default_factory=list)
    test_source: str | None = None


class ExampleResult(BaseModel):
    """Result of get_related_examples tool (unreliable, fails 30% of the time)."""
    query: str
    examples: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Verification Models
# ---------------------------------------------------------------------------

class LintError(BaseModel):
    """A single ruff lint error."""
    file: str
    line: int
    column: int
    code: str
    message: str


class TypeError_(BaseModel):
    """A single mypy type error (underscore to avoid shadowing builtins)."""
    file: str
    line: int
    code: str
    message: str


class StaticAnalysisResult(BaseModel):
    """Result of ruff + mypy static analysis."""
    passed: bool
    ruff_errors: list[LintError] = Field(default_factory=list)
    mypy_errors: list[TypeError_] = Field(default_factory=list)
    error_count: int = 0


class FailedTest(BaseModel):
    """A single failed pytest test."""
    name: str
    message: str
    longrepr: str | None = None


class TestRunResult(BaseModel):
    """Result of pytest execution."""
    passed: bool
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    failed_tests: list[FailedTest] = Field(default_factory=list)
    duration_seconds: float = 0.0


class ReviewResult(BaseModel):
    """Result of LLM-as-reviewer check."""
    passed: bool
    issues: list[str] = Field(default_factory=list)
    summary: str = ""


class VerificationResult(BaseModel):
    """Combined result of all 3 verification layers."""
    static: StaticAnalysisResult | None = None
    tests: TestRunResult | None = None
    review: ReviewResult | None = None

    @property
    def all_passed(self) -> bool:
        return all([
            self.static is not None and self.static.passed,
            self.tests is not None and self.tests.passed,
            self.review is not None and self.review.passed,
        ])


# ---------------------------------------------------------------------------
# Agent Loop Models
# ---------------------------------------------------------------------------

class Task(BaseModel):
    """A coding task submitted to the agent."""
    task_id: str
    description: str
    submitted_at: datetime = Field(default_factory=datetime.now)


class Plan(BaseModel):
    """Output of the PLAN phase."""
    target_files: list[str] = Field(description="Files likely to be modified")
    retrieval_strategy: str = Field(description="How to retrieve context")
    is_impossible: bool = False
    impossible_reason: str | None = None


class Decision(BaseModel):
    """Output of the DECIDE phase."""
    decision_type: DecisionType
    done: bool = False
    impossible: bool = False
    reason: str | None = None
    next_plan: Plan | None = None


class TaskResult(BaseModel):
    """Final result of an agent run."""
    task_id: str
    status: TaskStatus
    generated_code: str | None = None
    iterations_used: int = 0
    verification: VerificationResult | None = None
    cost_breakdown: dict[str, float] = Field(default_factory=dict)
    total_cost_usd: float = 0.0
    time_seconds: float = 0.0
    failure_reason: str | None = None

    @classmethod
    def success(
        cls, task_id: str, code: str, iterations: int, cost: dict[str, float], time_s: float
    ) -> TaskResult:
        return cls(
            task_id=task_id,
            status=TaskStatus.DONE,
            generated_code=code,
            iterations_used=iterations,
            cost_breakdown=cost,
            total_cost_usd=sum(cost.values()),
            time_seconds=time_s,
        )

    @classmethod
    def impossible(cls, task_id: str, reason: str) -> TaskResult:
        return cls(
            task_id=task_id,
            status=TaskStatus.IMPOSSIBLE,
            failure_reason=reason,
        )

    @classmethod
    def exhausted(cls, task_id: str, last_error: str, iterations: int) -> TaskResult:
        return cls(
            task_id=task_id,
            status=TaskStatus.FAILED,
            iterations_used=iterations,
            failure_reason=f"Exhausted {iterations} iterations. Last error: {last_error}",
        )


# ---------------------------------------------------------------------------
# Cost Tracking Models
# ---------------------------------------------------------------------------

class LLMCall(BaseModel):
    """Record of a single LLM API call for cost tracking."""
    model: str
    stage: Stage
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    timestamp: datetime = Field(default_factory=datetime.now)


class CostBreakdown(BaseModel):
    """Cost breakdown for a task."""
    task_id: str
    calls: list[LLMCall] = Field(default_factory=list)
    cost_per_stage: dict[str, float] = Field(default_factory=dict)
    total_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Tool Registry Models
# ---------------------------------------------------------------------------

class ToolSchema(BaseModel):
    """Schema describing a registered tool."""
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = 5.0
    is_unreliable: bool = False
    failure_rate: float = 0.0


# ---------------------------------------------------------------------------
# Eval Models
# ---------------------------------------------------------------------------

class TaskDefinition(BaseModel):
    """Definition of a benchmark task."""
    task_id: str
    description: str
    difficulty: Difficulty
    expected_files: list[str] = Field(default_factory=list)
    expected_behavior: str = ""
    should_be_impossible: bool = False
    is_budget_exceeded: bool = False
    tests_failure_recovery: bool = False


class TaskScore(BaseModel):
    """Score for a single benchmark task."""
    task_id: str
    passed: bool
    impossible_correctly_detected: bool = False
    iterations_used: int = 0
    cost_usd: float = 0.0
    time_seconds: float = 0.0
    static_passed: bool = False
    tests_passed: bool = False
    review_passed: bool = False
    failure_reason: str | None = None


class BenchmarkReport(BaseModel):
    """Aggregate benchmark report."""
    combo: str
    pass_rate: str
    impossible_detected: bool = False
    avg_iterations: float = 0.0
    avg_cost_usd: float = 0.0
    avg_time_seconds: float = 0.0
    total_cost_usd: float = 0.0
    tasks: list[TaskScore] = Field(default_factory=list)
