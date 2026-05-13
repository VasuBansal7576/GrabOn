"""AST parser for turning Python files into structural units."""

from __future__ import annotations

import ast
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language, Parser

from src.schemas import ModuleNode, ParsedUnit

_TREE_SITTER_PARSER: Parser | None = None


def module_name_from_path(file_path: str) -> str:
    """Convert a relative Python path into a dotted module path."""
    path = Path(file_path)
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def parse_python_file(path: Path, codebase_root: Path) -> tuple[ModuleNode, list[ParsedUnit]]:
    """Parse one Python file into a module node and structural units."""
    source = path.read_text(encoding="utf-8")
    rel_path = path.relative_to(codebase_root).as_posix()
    _validate_with_tree_sitter(source, rel_path)
    tree = ast.parse(source, filename=rel_path)
    lines = source.splitlines()
    imports = _extract_imports(tree)
    module = ModuleNode(
        file_path=rel_path,
        docstring=ast.get_docstring(tree),
        imports=imports,
    )
    module_name = module_name_from_path(rel_path)
    units: list[ParsedUnit] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            unit = _class_unit(node, module_name, rel_path, lines, imports)
            units.append(unit)
            module.classes.append(unit.unit_id)
            for child in node.body:
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    method = _function_unit(
                        child,
                        module_name=module_name,
                        rel_path=rel_path,
                        lines=lines,
                        imports=imports,
                        parent_class=node.name,
                    )
                    units.append(method)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            unit = _function_unit(
                node,
                module_name=module_name,
                rel_path=rel_path,
                lines=lines,
                imports=imports,
                parent_class=None,
            )
            units.append(unit)
            module.functions.append(unit.unit_id)

    return module, units


def parse_codebase(codebase_path: str | Path) -> tuple[dict[str, ModuleNode], list[ParsedUnit]]:
    """Parse all Python files below a codebase root."""
    root = Path(codebase_path).resolve()
    modules: dict[str, ModuleNode] = {}
    units: list[ParsedUnit] = []
    for path in sorted(root.rglob("*.py")):
        if _is_ignored(path, root):
            continue
        module, parsed_units = parse_python_file(path, root)
        modules[module.file_path] = module
        units.extend(parsed_units)
    return modules, units


def _is_ignored(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    ignored = {".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
    return any(part in ignored for part in rel_parts)


def _validate_with_tree_sitter(source: str, rel_path: str) -> None:
    """Parse source with tree-sitter before AST extraction.

    The Python AST provides simpler typed extraction in this implementation,
    while tree-sitter gives the assignment-required syntax tree pass and a
    grammar-level error check.
    """
    parser = _tree_sitter_parser()
    tree = parser.parse(source.encode("utf-8"))
    if tree.root_node.has_error:
        raise SyntaxError(f"tree-sitter parse error in {rel_path}")


def _tree_sitter_parser() -> Parser:
    global _TREE_SITTER_PARSER
    if _TREE_SITTER_PARSER is None:
        parser = Parser()
        parser.language = Language(tree_sitter_python.language())
        _TREE_SITTER_PARSER = parser
    return _TREE_SITTER_PARSER


def _extract_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                imports.append(f"{module}.{alias.name}".strip("."))
    return sorted(set(imports))


def _class_unit(
    node: ast.ClassDef,
    module_name: str,
    rel_path: str,
    lines: list[str],
    imports: list[str],
) -> ParsedUnit:
    bases = [_unparse(base) for base in node.bases]
    signature = f"class {node.name}({', '.join(bases)}):" if bases else f"class {node.name}:"
    return ParsedUnit(
        unit_id=f"{module_name}.{node.name}",
        unit_type="class",
        file_path=rel_path,
        name=node.name,
        signature=signature,
        docstring=ast.get_docstring(node),
        body=_node_source(node, lines),
        line_start=node.lineno,
        line_end=getattr(node, "end_lineno", node.lineno),
        imports=imports,
    )


def _function_unit(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_name: str,
    rel_path: str,
    lines: list[str],
    imports: list[str],
    parent_class: str | None,
) -> ParsedUnit:
    prefix = f"{module_name}.{parent_class}." if parent_class else f"{module_name}."
    unit_type = "method" if parent_class else "function"
    return ParsedUnit(
        unit_id=f"{prefix}{node.name}",
        unit_type=unit_type,
        file_path=rel_path,
        name=node.name,
        signature=_signature(node, lines),
        docstring=ast.get_docstring(node),
        body=_node_source(node, lines),
        line_start=node.lineno,
        line_end=getattr(node, "end_lineno", node.lineno),
        imports=imports,
        parent_class=parent_class,
    )


def _node_source(node: ast.AST, lines: list[str]) -> str:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    return "\n".join(lines[start - 1 : end])


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str]) -> str:
    first_line = lines[node.lineno - 1].strip()
    if first_line.endswith(":"):
        return first_line
    collected = [first_line]
    for line in lines[node.lineno : getattr(node, "end_lineno", node.lineno)]:
        collected.append(line.strip())
        if line.rstrip().endswith(":"):
            break
    return " ".join(collected)


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return getattr(node, "id", "object")
