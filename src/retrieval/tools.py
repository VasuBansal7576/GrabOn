"""Typed retrieval tools for navigating a tree index."""

from __future__ import annotations

from pathlib import Path

from src.retrieval.registry import ToolRegistry
from src.schemas import (
    ClassResult,
    ExampleResult,
    FunctionResult,
    ImportResult,
    ModuleListing,
    ReferenceResult,
    TestResult,
    TreeIndex,
)


class RetrievalTools:
    """Deep module exposing retrieval operations over a TreeIndex."""

    def __init__(self, index: TreeIndex) -> None:
        self.index = index

    def ls_module(self, module_path: str) -> ModuleListing:
        module = self.index.modules.get(module_path)
        if module is None:
            raise KeyError(f"Module not found: {module_path}")
        return ModuleListing(
            file_path=module.file_path,
            functions=module.functions,
            classes=module.classes,
        )

    def get_function(self, unit_id: str) -> FunctionResult:
        unit = self.index.units.get(unit_id)
        if unit is None or unit.unit_type not in {"function", "method"}:
            raise KeyError(f"Function or method not found: {unit_id}")
        return FunctionResult(
            unit_id=unit.unit_id,
            signature=unit.signature,
            body=unit.body,
            docstring=unit.docstring,
            file_path=unit.file_path,
            line_start=unit.line_start,
            line_end=unit.line_end,
        )

    def get_class(self, unit_id: str) -> ClassResult:
        unit = self.index.units.get(unit_id)
        if unit is None or unit.unit_type != "class":
            raise KeyError(f"Class not found: {unit_id}")
        methods = [
            candidate.signature
            for candidate in self.index.units.values()
            if candidate.parent_class == unit.name and candidate.file_path == unit.file_path
        ]
        bases = _parse_bases(unit.signature)
        return ClassResult(
            unit_id=unit.unit_id,
            definition=unit.body,
            methods=methods,
            bases=bases,
        )

    def find_references(self, name: str) -> ReferenceResult:
        references = [
            unit_id
            for unit_id, unit in self.index.units.items()
            if name in unit.body or name in unit.signature or name == unit.name
        ]
        return ReferenceResult(name=name, references=sorted(set(references)))

    def get_imports(self, file_path: str) -> ImportResult:
        module = self.index.modules.get(file_path)
        if module is None:
            raise KeyError(f"Module not found: {file_path}")
        imported_by = [
            path
            for path, candidate in self.index.modules.items()
            if path != file_path
            and any(_import_mentions_file(imp, file_path) for imp in candidate.imports)
        ]
        return ImportResult(
            file_path=file_path,
            imports=module.imports,
            imported_by=sorted(imported_by),
        )

    def get_tests_for(self, unit_id: str) -> TestResult:
        unit = self.index.units.get(unit_id)
        if unit is None:
            raise KeyError(f"Unit not found: {unit_id}")
        test_files = self.index.test_map.get(unit_id, [])
        test_functions: list[str] = []
        test_source_parts: list[str] = []
        root = Path(self.index.codebase_path or ".")
        for test_file in test_files:
            module = self.index.modules.get(test_file)
            if module is not None:
                test_functions.extend(module.functions)
            path = root / test_file
            if path.exists():
                test_source_parts.append(path.read_text(encoding="utf-8"))
        return TestResult(
            unit_id=unit_id,
            test_file=", ".join(test_files) if test_files else None,
            test_functions=sorted(set(test_functions)),
            test_source="\n\n".join(test_source_parts) if test_source_parts else None,
        )

    def get_related_examples(self, query: str) -> ExampleResult:
        query_terms = {term.lower() for term in query.replace("_", " ").split() if len(term) > 2}
        scored: list[tuple[int, str]] = []
        for unit in self.index.units.values():
            haystack = f"{unit.unit_id} {unit.signature} {unit.docstring or ''}".lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score:
                scored.append((score, f"{unit.unit_id}: {unit.signature}"))
        examples = [example for _, example in sorted(scored, reverse=True)[:5]]
        return ExampleResult(query=query, examples=examples)


def create_tool_registry(index: TreeIndex) -> ToolRegistry:
    """Create a registry populated with all retrieval tools."""
    tools = RetrievalTools(index)
    registry = ToolRegistry()
    registry.register(
        "ls_module",
        "List classes and functions in a module",
        tools.ls_module,
        parameters={"module_path": "str"},
    )
    registry.register(
        "get_function",
        "Return full source for a function or method",
        tools.get_function,
        parameters={"unit_id": "str"},
    )
    registry.register(
        "get_class",
        "Return class definition and method signatures",
        tools.get_class,
        parameters={"unit_id": "str"},
    )
    registry.register(
        "find_references",
        "Find units referencing a name",
        tools.find_references,
        parameters={"name": "str"},
    )
    registry.register(
        "get_imports",
        "Return imports and reverse imports for a file",
        tools.get_imports,
        parameters={"file_path": "str"},
    )
    registry.register(
        "get_tests_for",
        "Return tests related to a unit",
        tools.get_tests_for,
        parameters={"unit_id": "str"},
    )
    registry.register(
        "get_related_examples",
        "Return related examples; deliberately unreliable",
        tools.get_related_examples,
        parameters={"query": "str"},
        is_unreliable=True,
        failure_rate=0.30,
    )
    return registry


def _parse_bases(signature: str) -> list[str]:
    if "(" not in signature or ")" not in signature:
        return []
    inside = signature.split("(", 1)[1].rsplit(")", 1)[0].strip()
    if not inside:
        return []
    return [part.strip() for part in inside.split(",")]


def _import_mentions_file(import_name: str, file_path: str) -> bool:
    dotted = file_path.removesuffix(".py").replace("/", ".")
    return import_name == dotted or import_name.endswith(f".{Path(file_path).stem}")
