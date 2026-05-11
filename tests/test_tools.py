"""Tests for retrieval tools and tool registry."""

from __future__ import annotations

from src.retrieval.registry import ToolRegistry


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
        assert False, "Should have raised ToolNotFoundError"
    except ToolNotFoundError:
        pass
