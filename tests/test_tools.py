"""Tests for retrieval tools and tool registry."""

from __future__ import annotations

from pathlib import Path

from src.agent import router as router_module
from src.agent.generator import (
    CodeGenerator,
    _extract_diff,
    _generation_prompt,
    _normalize_generated_diff,
)
from src.agent.loop import AgentLoop
from src.agent.router import CostTracker, ModelRouter
from src.eval.compare import compare_reports
from src.indexer.indexer import index_codebase
from src.retrieval.navigator import Navigator
from src.retrieval.registry import ToolRegistry
from src.retrieval.tools import RetrievalTools
from src.schemas import (
    BenchmarkReport,
    GeneratedPatch,
    LLMResponse,
    ParsedUnit,
    Plan,
    RetrievalContext,
    Stage,
    Task,
    TaskScore,
    TestResult,
)
from src.verification.reviewer import review_patch
from src.verification.test_runner import _apply_patch


def test_registry_register_and_list() -> None:
    """Test that tools can be registered and listed."""
    registry = ToolRegistry()
    registry.register(
        name="test_tool",
        description="A test tool",
        execute_fn=lambda: "hello",
    )
    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "test_tool"


def test_registry_get_tool() -> None:
    """Test that a registered tool can be retrieved by name."""
    registry = ToolRegistry()
    registry.register(
        name="my_tool",
        description="My tool",
        execute_fn=lambda: None,
    )
    schema = registry.get("my_tool")
    assert schema.name == "my_tool"


def test_registry_tool_not_found() -> None:
    """Test that ToolNotFoundError is raised for unknown tools."""
    from src.retrieval.registry import ToolNotFoundError

    registry = ToolRegistry()
    try:
        registry.get("nonexistent")
        raise AssertionError("Should have raised ToolNotFoundError")
    except ToolNotFoundError:
        pass


def test_retrieval_tools_return_typed_results(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "def target() -> str:\n"
        "    return helper()\n\n"
        "def helper() -> str:\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )
    index = index_codebase(tmp_path, use_cache=False)
    tools = RetrievalTools(index)

    listing = tools.ls_module("mod.py")
    refs = tools.find_references("helper")
    function = tools.get_function("mod.target")

    assert listing.functions == ["mod.target", "mod.helper"]
    assert refs.references == ["mod.helper", "mod.target"]
    assert "return helper()" in function.body


def test_navigator_prefers_structural_header_merge_units(tmp_path: Path) -> None:
    package = tmp_path / "httpx"
    package.mkdir()
    (package / "_client.py").write_text(
        "class BaseClient:\n"
        "    def _merge_headers(self, headers):\n"
        "        return headers\n\n"
        "    def build_request(self, method, url, headers=None):\n"
        "        return self._merge_headers(headers)\n\n"
        "class Client(BaseClient):\n"
        "    def request(self, method, url, headers=None):\n"
        "        return self.build_request(method, url, headers=headers)\n",
        encoding="utf-8",
    )

    index = index_codebase(tmp_path, use_cache=False)
    context = Navigator(index=index).retrieve_sync("Where are request headers merged?")
    retrieved = [unit.unit_id for unit in context.units[:2]]

    assert retrieved == [
        "httpx._client.BaseClient._merge_headers",
        "httpx._client.BaseClient.build_request",
    ]
    tool_names = [record.tool_name for record in context.tool_calls]
    assert "ls_module" in tool_names
    assert "get_imports" in tool_names
    assert "find_references" in tool_names


def test_navigator_prefers_request_class_for_request_timeout(tmp_path: Path) -> None:
    package = tmp_path / "httpx"
    package.mkdir()
    (package / "_models.py").write_text(
        "class Request:\n"
        "    def __init__(self, extensions=None):\n"
        "        self.extensions = extensions or {}\n\n"
        "class Response:\n"
        "    pass\n",
        encoding="utf-8",
    )
    (package / "_config.py").write_text(
        "class Timeout:\n"
        "    def __init__(self, timeout):\n"
        "        self.timeout = timeout\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_timeouts.py").write_text(
        "def test_async_client_new_request_send_timeout():\n"
        "    pass\n",
        encoding="utf-8",
    )

    index = index_codebase(tmp_path, use_cache=False)
    context = Navigator(index=index).retrieve_sync(
        "Add a timeout_seconds property to Request class"
    )

    assert context.units[0].unit_id == "httpx._models.Request"


def test_navigator_prefers_exact_underscore_method_match(tmp_path: Path) -> None:
    package = tmp_path / "httpx"
    package.mkdir()
    (package / "_urls.py").write_text(
        "class URL:\n"
        "    def copy_with(self, **kwargs):\n"
        "        return self\n\n"
        "    def copy_set_param(self, key, value=None):\n"
        "        return self\n\n"
        "    def copy_merge_params(self, params):\n"
        "        return self\n",
        encoding="utf-8",
    )

    index = index_codebase(tmp_path, use_cache=False)
    context = Navigator(index=index).retrieve_sync(
        "Write pytest tests for the existing URL.copy_with method."
    )

    assert context.units[0].unit_id == "httpx._urls.URL.copy_with"


def test_cache_transport_plan_keeps_new_file_and_export_targets() -> None:
    plan = AgentLoop()._heuristic_plan(
        Task(
            task_id="task_08_cache_transport",
            description=(
                "Implement a CacheTransport class with Cache-Control handling "
                "and a configurable TTL."
            ),
        )
    )

    assert "httpx/_cache.py" in plan.target_files
    assert "httpx/__init__.py" in plan.target_files
    assert "tests/test_cache_transport.py" in plan.target_files


def test_navigator_retrieves_readme_conventions(tmp_path: Path) -> None:
    package = tmp_path / "httpx"
    package.mkdir()
    (package / "_client.py").write_text(
        "class Client:\n"
        "    def send(self, request):\n"
        "        return request\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Contributing\n\n"
        "Prefer the existing client helpers and keep sync plus async behavior aligned.\n",
        encoding="utf-8",
    )

    index = index_codebase(tmp_path, use_cache=False)
    context = Navigator(index=index).retrieve_sync(
        "How should I keep sync and async behavior aligned?"
    )

    assert context.docs
    assert any(chunk.file_path == "README.md" for chunk in context.docs)


def test_navigator_uses_vector_fallback_for_ambiguous_convention_query(tmp_path: Path) -> None:
    package = tmp_path / "httpx"
    package.mkdir()
    (package / "_streams.py").write_text(
        "def iter_bytes() -> bytes:\n"
        "    return b'data'\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Contributing\n\n"
        "Keep stream helpers aligned with the public response API.\n",
        encoding="utf-8",
    )

    index = index_codebase(tmp_path, use_cache=False)
    context = Navigator(index=index).retrieve_sync(
        "What convention should I follow for the stream helper API?",
        strategy="tree-first with hybrid vector fallback for conventions",
    )

    assert "vector_fallback_used" in context.notes
    assert context.units


def test_review_patch_surfaces_provider_errors() -> None:
    patch = GeneratedPatch(
        task_id="t",
        unified_diff="",
        explanation="PROVIDER_ERROR: missing API key for claude-sonnet",
    )

    result = review_patch(patch)

    assert not result.passed
    assert "missing API key" in result.summary


def test_review_patch_requires_tests_for_source_behavior_changes() -> None:
    patch = GeneratedPatch(
        task_id="t",
        unified_diff=(
            "diff --git a/httpx/_models.py b/httpx/_models.py\n"
            "+++ b/httpx/_models.py\n"
            "+def helper():\n"
            "+    return 1\n"
        ),
        explanation="candidate",
    )

    result = review_patch(patch)

    assert not result.passed
    assert "focused tests" in result.summary


def test_extract_diff_accepts_unfenced_unified_diff_and_strips_prose() -> None:
    raw = (
        "Here is the patch:\n"
        "--- a/httpx/_models.py\n"
        "+++ b/httpx/_models.py\n"
        "@@ -1,2 +1,3 @@\n"
        " class Request:\n"
        "+    pass\n"
        "Explanation: added a stub\n"
    )

    diff = _extract_diff(raw)

    assert diff.startswith("--- a/httpx/_models.py")
    assert "Explanation" not in diff


def test_extract_diff_repairs_blank_context_lines_inside_hunks() -> None:
    raw = (
        "--- a/httpx/_transports/base.py\n"
        "+++ b/httpx/_transports/base.py\n"
        "@@ -1,3 +1,4 @@\n"
        " import abc\n"
        "\n"
        "+import time\n"
        " class BaseTransport:\n"
    )

    diff = _extract_diff(raw)

    assert "\n \n+import time\n" in diff


def test_test_only_live_diff_is_wrapped_as_new_file() -> None:
    task = Task(
        task_id="task_03_url_copy_with_tests",
        description="Write pytest tests for the existing URL.copy_with method.",
    )
    diff = (
        "diff --git a/tests/test_url.py b/tests/test_url.py\n"
        "--- a/tests/test_url.py\n"
        "+++ b/tests/test_url.py\n"
        "@@ -1 +1,4 @@\n"
        "+def test_url_copy_with_scheme():\n"
        "+    url = httpx.URL('https://example.com')\n"
        "+    assert str(url.copy_with(scheme='http')) == 'http://example.com'\n"
    )

    normalized = _normalize_generated_diff(task, diff, diff)

    assert "--- /dev/null" in normalized
    assert "+++ b/tests/test_url_copy_with.py" in normalized
    assert "+import httpx" in normalized


def test_test_only_live_diff_drops_orphan_assert_and_unused_pytest() -> None:
    task = Task(
        task_id="task_03_url_copy_with_tests",
        description="Write pytest tests for the existing URL.copy_with method.",
    )
    diff = (
        "--- /dev/null\n"
        "+++ b/tests/test_httpx_urls.py\n"
        "@@ -0,0 +1,7 @@\n"
        "+import pytest\n"
        "+import httpx\n"
        "+    assert str(url) == 'orphan'\n"
        "+def test_url_copy_with_host():\n"
        "+    url = httpx.URL('https://example.com')\n"
        "+    assert str(url.copy_with(host='api.example.com')) == 'https://api.example.com'\n"
    )

    normalized = _normalize_generated_diff(task, diff, diff)

    assert "+++ b/tests/test_url_copy_with.py" in normalized
    assert "+import pytest" not in normalized
    assert "+    assert str(url) == 'orphan'" not in normalized
    assert "+def test_url_copy_with_host():" in normalized


def test_test_only_live_diff_falls_back_to_raw_response_tests() -> None:
    task = Task(
        task_id="task_03_url_copy_with_tests",
        description="Write pytest tests for the existing URL.copy_with method.",
    )
    extracted = (
        "diff --git a/tests/test_urls.py b/tests/test_urls.py\n"
        "--- a/tests/test_urls.py\n"
        "+++ b/tests/test_urls.py\n"
        "@@ -1000,6 +1000,100 @@ def test_url_copywith_security():\n"
    )
    raw = (
        extracted
        + "+def test_url_copy_with_scheme():\n"
        + "+    url = httpx.URL('https://example.com')\n"
        + "+    assert str(url.copy_with(scheme='http')) == 'http://example.com'\n"
    )

    normalized = _normalize_generated_diff(task, extracted, raw)

    assert "+++ b/tests/test_url_copy_with.py" in normalized
    assert "+def test_url_copy_with_scheme():" in normalized


def test_cache_transport_live_diff_is_stabilized_for_multifile_apply(tmp_path: Path) -> None:
    package = tmp_path / "httpx"
    package.mkdir()
    (tmp_path / "tests").mkdir()
    (package / "__init__.py").write_text(
        "from ._auth import *\n\n"
        "__all__ = [\n"
        '    "ByteStream",\n'
        '    "Client",\n'
        "]\n",
        encoding="utf-8",
    )
    task = Task(
        task_id="task_08_cache_transport",
        description="Implement a CacheTransport class with Cache-Control handling.",
    )
    malformed_live_diff = (
        "diff --git a/httpx/_models.py b/httpx/_models.py\n"
        "--- a/httpx/_models.py\n"
        "+++ b/httpx/_models.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+from ._cache import CacheTransport\n"
        "diff --git a/dev/null b/httpx/_cache.py\n"
        "--- dev/null\n"
        "+++ b/httpx/_cache.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+class CacheTransport:\n"
        "+    pass\n"
        "diff --git a/httpx/__init__.py b/httpx/__init__.py\n"
        "--- a/httpx/__init__.py\n"
        "+++ b/httpx/__init__.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+from ._cache import *\n"
        "+    \"CacheTransport\",\n"
    )

    normalized = _normalize_generated_diff(
        task,
        malformed_live_diff,
        malformed_live_diff,
        tmp_path,
    )
    _apply_patch(tmp_path, normalized)

    assert "+++ b/httpx/_models.py" not in normalized
    assert "from ._cache import *" in (package / "__init__.py").read_text(encoding="utf-8")
    assert '"CacheTransport"' in (package / "__init__.py").read_text(encoding="utf-8")
    assert "class CacheTransport" in (package / "_cache.py").read_text(encoding="utf-8")
    assert (tmp_path / "tests" / "test_grabonai_cache_transport.py").exists()


def test_refactor_keeps_original_patch_when_provider_fails() -> None:
    class FailingRouter:
        def call(self, stage: Stage, prompt: str) -> LLMResponse:
            return LLMResponse(
                content="PROVIDER_ERROR: transient failure",
                model="nvidia-chat",
                stage=stage,
            )

    patch = GeneratedPatch(
        task_id="t",
        unified_diff=(
            "--- /dev/null\n"
            "+++ b/tests/test_example.py\n"
            "@@ -0,0 +1 @@\n"
            "+def test_ok(): pass\n"
        ),
        explanation="candidate",
    )
    generator = CodeGenerator(router=FailingRouter(), use_templates=False)  # type: ignore[arg-type]

    result = generator.refactor(
        task=Task(task_id="t", description="Write pytest tests for existing behavior."),
        plan=Plan(target_files=["tests/test_example.py"], retrieval_strategy="tree-first"),
        context=RetrievalContext(task="t"),
        patch=patch,
        prior_errors=["reviewer retry"],
    )

    assert result is patch


def test_generation_prompt_clips_large_context_for_free_tier_models() -> None:
    context = RetrievalContext(task="t")
    context.units = [
        ParsedUnit(
            unit_id=f"pkg.mod.func_{index}",
            name=f"func_{index}",
            unit_type="function",
            file_path="pkg/mod.py",
            signature=f"def func_{index}():",
            line_start=1,
            line_end=2,
            body="x = 1\n" * 1000,
        )
        for index in range(8)
    ]
    context.tests = [
        TestResult(
            unit_id="pkg.mod.func",
            test_files=["tests/test_mod.py"],
            test_source="def test_many():\n    assert True\n" * 500,
        )
    ]

    prompt = _generation_prompt(
        Task(task_id="t", description="Add tests."),
        Plan(target_files=["pkg/mod.py"], retrieval_strategy="tree-first"),
        context,
        prior_errors=["error"] * 10,
    )

    assert len(prompt) < 16000
    assert "...[truncated]" in prompt


def test_generation_prompt_guides_cache_transport_to_new_module() -> None:
    prompt = _generation_prompt(
        Task(
            task_id="task_08_cache_transport",
            description="Implement a CacheTransport class with Cache-Control handling.",
        ),
        Plan(
            target_files=["httpx/_cache.py", "httpx/__init__.py", "tests/test_cache_transport.py"],
            retrieval_strategy="tree-first",
        ),
        RetrievalContext(task="cache transport"),
        prior_errors=[],
    )

    assert "Implement CacheTransport in a new `httpx/_cache.py` module" in prompt
    assert "Do not edit `httpx/_transports/base.py`" in prompt


def test_live_review_can_degrade_after_deterministic_review() -> None:
    class FailingReviewRouter:
        def call(self, stage: Stage, prompt: str) -> LLMResponse:
            return LLMResponse(
                content="PROVIDER_ERROR: APITimeoutError: Request timed out.",
                model="nvidia-chat",
                stage=stage,
            )

    patch = GeneratedPatch(
        task_id="t",
        unified_diff=(
            "--- /dev/null\n"
            "+++ b/tests/test_example.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def test_ok():\n"
            "+    assert True\n"
        ),
        explanation="candidate",
    )

    result = review_patch(
        patch,
        router=FailingReviewRouter(),  # type: ignore[arg-type]
        use_llm=True,
        allow_provider_fallback=True,
    )

    assert result.passed
    assert "live reviewer unavailable" in result.summary


def test_missing_provider_key_records_zero_cost(monkeypatch) -> None:
    monkeypatch.setattr(router_module.settings, "anthropic_api_key", "")
    tracker = CostTracker(task_id="t")
    response = ModelRouter(combo="b", tracker=tracker).call(
        Stage.CODE_GENERATION,
        "make a patch",
    )

    assert response.content == "PROVIDER_ERROR: missing API key for claude-sonnet"
    assert response.cost_usd == 0.0
    assert tracker.total() == 0.0


def test_nvidia_combo_selects_nvidia_model() -> None:
    assert ModelRouter(combo="nvidia").model_for(Stage.CODE_GENERATION) == "nvidia-chat"


def test_missing_nvidia_provider_key_records_zero_cost(monkeypatch) -> None:
    monkeypatch.setattr(router_module.settings, "nvidia_api_key", "")
    tracker = CostTracker(task_id="t")
    response = ModelRouter(combo="nvidia", tracker=tracker).call(
        Stage.CODE_GENERATION,
        "reply with ok only",
    )

    assert response.content == "PROVIDER_ERROR: missing API key for nvidia-chat"
    assert response.cost_usd == 0.0
    assert tracker.total() == 0.0


def test_configurable_live_provider_models(monkeypatch) -> None:
    monkeypatch.setattr(router_module.settings, "gemini_model", "gemini-2.5-flash-lite")
    monkeypatch.setattr(
        router_module.settings,
        "nvidia_model",
        "mistralai/mistral-small-4-119b-2603",
    )
    assert router_module._nvidia_model_name("nvidia-chat") == (
        "mistralai/mistral-small-4-119b-2603"
    )


def test_groq_combo_selects_stage_specific_models() -> None:
    router = ModelRouter(combo="groq")
    assert router.model_for(Stage.CONTEXT_RANKING) == "groq-llama-8b"
    assert router.model_for(Stage.CODE_GENERATION) == "groq-llama-70b"


def test_missing_groq_provider_key_records_zero_cost(monkeypatch) -> None:
    monkeypatch.setattr(router_module.settings, "groq_api_key", "")
    tracker = CostTracker(task_id="t")
    response = ModelRouter(combo="groq", tracker=tracker).call(
        Stage.CODE_GENERATION,
        "reply with ok only",
    )

    assert response.content == "PROVIDER_ERROR: missing API key for groq-llama-70b"
    assert response.cost_usd == 0.0
    assert tracker.total() == 0.0


def test_compare_reports_produces_paired_metric_summary() -> None:
    left = BenchmarkReport(
        combo="a",
        run_mode="fixture",
        provider_models=[],
        pass_rate="2/2",
        avg_iterations=1.0,
        avg_cost_usd=0.0,
        avg_time_seconds=1.5,
        total_cost_usd=0.0,
        tasks=[
            TaskScore(task_id="t1", passed=True, iterations_used=1, cost_usd=0.0, time_seconds=1.0),
            TaskScore(task_id="t2", passed=True, iterations_used=1, cost_usd=0.0, time_seconds=2.0),
        ],
    )
    right = BenchmarkReport(
        combo="b",
        run_mode="fixture",
        provider_models=[],
        pass_rate="1/2",
        avg_iterations=2.0,
        avg_cost_usd=0.1,
        avg_time_seconds=2.5,
        total_cost_usd=0.2,
        tasks=[
            TaskScore(task_id="t1", passed=True, iterations_used=2, cost_usd=0.1, time_seconds=2.0),
            TaskScore(
                task_id="t2",
                passed=False,
                iterations_used=2,
                cost_usd=0.1,
                time_seconds=3.0,
            ),
        ],
    )

    comparison = compare_reports(left, right)

    assert comparison.task_count == 2
    assert comparison.iterations.winner == "left"
    assert comparison.pass_rate_delta > 0
