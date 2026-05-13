"""Navigator that assembles code context through retrieval tools."""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.indexer.sparse_embeddings import cosine_similarity, embed_text
from src.indexer.vector_store import query_code_chunks
from src.retrieval.registry import ToolError, ToolRegistry
from src.retrieval.tools import create_tool_registry
from src.schemas import (
    ClassResult,
    CodeChunk,
    DocChunk,
    FunctionResult,
    ImportResult,
    ModuleListing,
    ParsedUnit,
    ReferenceResult,
    RetrievalContext,
    Stage,
    TestResult,
    ToolCallRecord,
    TreeIndex,
)

if TYPE_CHECKING:
    from src.agent.router import ModelRouter

_STOPWORDS = {
    "are",
    "does",
    "how",
    "the",
    "where",
    "with",
    "defined",
    "implemented",
}

_ALIASES: dict[str, set[str]] = {
    "abstraction": {"abstract", "base"},
    "abstractions": {"abstraction", "abstract", "base"},
    "called": {"call", "calls"},
    "configuration": {"config"},
    "decoded": {"decode", "decoder"},
    "headers": {"header"},
    "helpers": {"helper"},
    "hooks": {"hook"},
    "implemented": {"implement"},
    "merged": {"merge"},
    "mutation": {"copy", "param", "params"},
    "normalized": {"normalize", "config"},
    "read": {"content", "stream"},
    "transport": {"handle_request", "handle_async_request"},
}

_INTENT_HINTS: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = (
    (
        frozenset({"client", "send", "request"}),
        (
            "client.send",
            "client._send_handling_auth",
            "client._send_handling_redirects",
            "client._send_single_request",
        ),
    ),
    (
        frozenset({"request", "header", "merge"}),
        (
            "baseclient._merge_headers",
            "baseclient.build_request",
        ),
    ),
    (
        frozenset({"request", "timeout"}),
        (
            "_models.request",
            "_config.timeout",
            "timeout.__init__",
            "baseclient._set_timeout",
        ),
    ),
    (
        frozenset({"timeout", "config"}),
        (
            "_config.timeout",
            "timeout.__init__",
            "timeout.as_dict",
            "baseclient._set_timeout",
        ),
    ),
    (
        frozenset({"response", "status", "helper"}),
        (
            "response.is_success",
            "response.is_redirect",
            "response.is_client_error",
            "response.is_server_error",
            "response.is_error",
            "response.raise_for_status",
        ),
    ),
    (
        frozenset({"event", "hook", "call"}),
        (
            "baseclient.event_hooks",
            "client._send_single_request",
            "asyncclient._send_single_request",
        ),
    ),
    (
        frozenset({"sync", "async", "client"}),
        (
            "client.send",
            "asyncclient.send",
            "client._send_single_request",
            "asyncclient._send_single_request",
            "base.basetransport",
            "base.asyncbasetransport",
        ),
    ),
    (
        frozenset({"response", "content", "read"}),
        (
            "response.read",
            "response.aread",
            "response.iter_bytes",
            "response.aiter_bytes",
            "response._get_content_decoder",
        ),
    ),
    (
        frozenset({"transport", "abstraction"}),
        (
            "base.basetransport",
            "base.basetransport.handle_request",
            "base.asyncbasetransport",
            "base.asyncbasetransport.handle_async_request",
        ),
    ),
    (
        frozenset({"auth", "flow"}),
        (
            "_auth.auth",
            "auth.auth_flow",
            "auth.sync_auth_flow",
            "auth.async_auth_flow",
            "basicauth.auth_flow",
            "digestauth.auth_flow",
        ),
    ),
    (
        frozenset({"url", "copy"}),
        (
            "url.copy_with",
            "url.copy_set_param",
            "url.copy_add_param",
            "url.copy_remove_param",
            "url.copy_merge_params",
        ),
    ),
)


@dataclass(slots=True)
class Navigator:
    """Heuristic navigator with the same tool boundary used by model agents."""

    index: TreeIndex
    max_tool_calls: int = 8
    router: ModelRouter | None = None

    async def retrieve(
        self,
        task: str,
        strategy: str | None = None,
        preferred_files: list[str] | None = None,
        failure_hints: list[str] | None = None,
        force_related_examples: bool = False,
    ) -> RetrievalContext:
        registry = create_tool_registry(self.index)
        context = RetrievalContext(task=task)
        hints = failure_hints or []
        preferred = preferred_files or []
        strategy_text = strategy or "tree-first structural retrieval"
        context.notes.append(f"strategy:{strategy_text}")
        if preferred:
            context.notes.append(f"preferred_files:{','.join(preferred)}")
        if hints:
            context.notes.append(f"failure_hints:{','.join(hints)}")

        scored_units = self._rank_units(task, preferred)
        likely_units = [unit_id for _, _, unit_id in scored_units]

        if self._should_use_vector_fallback(task, scored_units, strategy_text, hints):
            context.notes.append("vector_fallback_used")
            for chunk in self._rank_code_chunks(task, preferred)[:3]:
                if chunk.unit_id not in likely_units:
                    likely_units.append(chunk.unit_id)

        likely_units = self._rank_with_model(
            task,
            scored_units,
            preferred,
            hints,
            likely_units,
            context,
        )

        await self._inspect_modules(registry, likely_units, preferred, context)

        if force_related_examples:
            await self._call_related_examples(registry, task, context)

        remaining_budget = max(0, self.max_tool_calls - len(context.tool_calls) - 1)
        direct_limit = max(1, remaining_budget // 2)
        for unit_id in likely_units[:direct_limit]:
            await self._fetch_unit(registry, unit_id, context)

        anchor_unit = context.units[0] if context.units else None
        if anchor_unit is not None:
            await self._follow_references(registry, anchor_unit, context, preferred)

        context.docs.extend(self._rank_doc_chunks(task)[:3])
        if not context.units:
            context.notes.append("no_relevant_units_found")
        return context

    def retrieve_sync(
        self,
        task: str,
        strategy: str | None = None,
        preferred_files: list[str] | None = None,
        failure_hints: list[str] | None = None,
        force_related_examples: bool = False,
    ) -> RetrievalContext:
        """Synchronous wrapper for CLI and queue callers."""
        return asyncio.run(
            self.retrieve(
                task,
                strategy=strategy,
                preferred_files=preferred_files,
                failure_hints=failure_hints,
                force_related_examples=force_related_examples,
            )
        )

    def _rank_units(self, task: str, preferred_files: list[str]) -> list[tuple[float, int, str]]:
        terms = _expanded_terms(task)
        scored: list[tuple[float, int, str]] = []
        for unit in self.index.units.values():
            score = _score_unit(unit, terms)
            score += _intent_score(unit.unit_id, terms)
            if preferred_files and unit.file_path in preferred_files:
                score += 10
            if unit.file_path.startswith("tests/") and "test" not in terms:
                score -= 25
            if score > 0:
                scored.append((score, _structural_priority(unit.unit_type), unit.unit_id))
        return sorted(scored, key=lambda item: (-item[0], -item[1], item[2]))

    def _rank_doc_chunks(self, task: str) -> list[DocChunk]:
        terms = _expanded_terms(task)
        scored: list[tuple[float, DocChunk]] = []
        for chunk in self.index.doc_chunks:
            haystack = f"{chunk.file_path} {chunk.heading} {chunk.content}".lower()
            score = sum(3 for term in terms if term in chunk.heading.lower())
            score += sum(2 for term in terms if term in chunk.file_path.lower())
            score += sum(1 for term in terms if term in haystack)
            if score > 0:
                scored.append((score, chunk))
        return [chunk for _, chunk in sorted(scored, key=lambda item: (-item[0], item[1].chunk_id))]

    def _rank_code_chunks(self, task: str, preferred_files: list[str]) -> list[CodeChunk]:
        if self.index.vector_store_path:
            persisted = query_code_chunks(
                self.index.vector_store_path,
                task,
                limit=6,
                preferred_files=preferred_files,
            )
            if persisted:
                return persisted
        query_embedding = embed_text(task)
        scored: list[tuple[float, CodeChunk]] = []
        for chunk in self.index.code_chunks:
            score = cosine_similarity(query_embedding, chunk.embedding)
            if preferred_files and chunk.file_path in preferred_files:
                score += 0.08
            if score > 0:
                scored.append((score, chunk))
        best_by_unit: dict[str, tuple[float, CodeChunk]] = {}
        for score, chunk in scored:
            current = best_by_unit.get(chunk.unit_id)
            if current is None or score > current[0]:
                best_by_unit[chunk.unit_id] = (score, chunk)
        return [
            chunk
            for _, chunk in sorted(
                best_by_unit.values(),
                key=lambda item: (-item[0], item[1].chunk_id),
            )
        ]

    def _rank_with_model(
        self,
        task: str,
        scored_units: list[tuple[float, int, str]],
        preferred_files: list[str],
        failure_hints: list[str],
        likely_units: list[str],
        context: RetrievalContext,
    ) -> list[str]:
        if self.router is None or not self.router.provider_available(Stage.CONTEXT_RANKING):
            return likely_units

        candidates = []
        for _, _, unit_id in scored_units[:12]:
            unit = self.index.units.get(unit_id)
            if unit is None:
                continue
            candidates.append(f"{unit.unit_id} | {unit.file_path} | {unit.unit_type}")
        if not candidates:
            return likely_units

        response = self.router.call(
            Stage.CONTEXT_RANKING,
            _context_ranking_prompt(task, candidates, preferred_files, failure_hints),
        )
        if response.content.startswith("PROVIDER_ERROR:"):
            context.notes.append("context_ranking_provider_error")
            return likely_units

        ranked = _extract_csv_field(response.content, "units")
        if not ranked:
            context.notes.append("context_ranking_unparsed")
            return likely_units

        merged = [unit_id for unit_id in ranked if unit_id in self.index.units]
        for unit_id in likely_units:
            if unit_id not in merged:
                merged.append(unit_id)
        context.notes.append("context_ranking_llm")
        return merged

    def _should_use_vector_fallback(
        self,
        task: str,
        scored_units: list[tuple[float, int, str]],
        strategy: str,
        failure_hints: list[str],
    ) -> bool:
        lowered_strategy = strategy.lower()
        lowered_task = task.lower()
        if "vector" in lowered_strategy or "hybrid" in lowered_strategy:
            return True
        if any(hint in {"imports", "logic", "docs", "tests"} for hint in failure_hints):
            return True
        if len(scored_units) < 2:
            return True
        return scored_units[0][0] < 18 or any(
            phrase in lowered_task
            for phrase in ("where should", "where are", "cross-cutting", "convention")
        )

    async def _inspect_modules(
        self,
        registry: ToolRegistry,
        likely_units: list[str],
        preferred_files: list[str],
        context: RetrievalContext,
    ) -> None:
        module_candidates = self._module_candidates(likely_units, preferred_files)
        if not module_candidates:
            return

        listing = await self._record_call(
            registry,
            "ls_module",
            {"module_path": module_candidates[0]},
            context,
        )
        if isinstance(listing, ModuleListing):
            symbol_count = len(listing.classes) + len(listing.functions)
            context.notes.append(
                f"module_listing:{listing.file_path}:{symbol_count}"
            )

        if len(context.tool_calls) >= self.max_tool_calls:
            context.notes.append("tool_call_limit_reached")
            return

        imports = await self._record_call(
            registry,
            "get_imports",
            {"file_path": module_candidates[0]},
            context,
        )
        if isinstance(imports, ImportResult):
            expanded_modules = [
                module_path
                for module_path in self._related_modules_from_imports(imports)
                if module_path not in preferred_files
            ]
            if expanded_modules:
                context.notes.append(f"import_chain:{','.join(expanded_modules[:3])}")

    def _module_candidates(self, likely_units: list[str], preferred_files: list[str]) -> list[str]:
        candidates: list[str] = []
        for file_path in preferred_files:
            if file_path in self.index.modules and file_path not in candidates:
                candidates.append(file_path)
        for unit_id in likely_units[:3]:
            unit = self.index.units.get(unit_id)
            if unit and unit.file_path not in candidates:
                candidates.append(unit.file_path)
        return candidates

    def _related_modules_from_imports(self, imports: ImportResult) -> list[str]:
        modules: list[str] = []
        for import_name in imports.imports:
            resolved = self._resolve_module(import_name)
            if resolved and resolved not in modules:
                modules.append(resolved)
        for file_path in imports.imported_by:
            if file_path not in modules:
                modules.append(file_path)
        return modules

    def _resolve_module(self, import_name: str) -> str | None:
        normalized = import_name.removesuffix(".py").replace(".", "/")
        for candidate in (
            f"{normalized}.py",
            f"{normalized}/__init__.py",
        ):
            if candidate in self.index.modules:
                return candidate
        tail = normalized.rsplit("/", 1)[-1]
        for module_path in self.index.modules:
            if module_path.endswith(f"/{tail}.py") or module_path == f"{tail}.py":
                return module_path
        return None

    async def _fetch_unit(
        self,
        registry: ToolRegistry,
        unit_id: str,
        context: RetrievalContext,
    ) -> None:
        if len(context.tool_calls) >= self.max_tool_calls:
            context.notes.append("tool_call_limit_reached")
            return

        unit = self.index.units.get(unit_id)
        if unit is None or any(existing.unit_id == unit_id for existing in context.units):
            return

        if unit.unit_type == "class":
            result = await self._record_call(registry, "get_class", {"unit_id": unit_id}, context)
            if isinstance(result, ClassResult):
                context.units.append(unit)
        else:
            result = await self._record_call(
                registry,
                "get_function",
                {"unit_id": unit_id},
                context,
            )
            if isinstance(result, FunctionResult):
                context.units.append(unit)

        if len(context.tool_calls) >= self.max_tool_calls:
            context.notes.append("tool_call_limit_reached")
            return

        test_result = await self._record_call(
            registry,
            "get_tests_for",
            {"unit_id": unit_id},
            context,
        )
        if isinstance(test_result, TestResult):
            self._append_test(context, test_result)

    async def _follow_references(
        self,
        registry: ToolRegistry,
        anchor_unit: ParsedUnit,
        context: RetrievalContext,
        preferred_files: list[str],
    ) -> None:
        if len(context.tool_calls) >= self.max_tool_calls:
            return

        reference_result = await self._record_call(
            registry,
            "find_references",
            {"name": anchor_unit.name},
            context,
        )
        if not isinstance(reference_result, ReferenceResult):
            return

        candidate_unit = self._best_reference_match(
            reference_result,
            preferred_files,
            context.units,
        )
        if candidate_unit is not None:
            await self._fetch_unit(registry, candidate_unit.unit_id, context)

    def _best_reference_match(
        self,
        reference_result: ReferenceResult,
        preferred_files: list[str],
        existing_units: list[ParsedUnit],
    ) -> ParsedUnit | None:
        existing_ids = {unit.unit_id for unit in existing_units}
        candidates: list[tuple[int, int, str]] = []
        for unit_id in reference_result.references:
            unit = self.index.units.get(unit_id)
            if unit is None or unit.unit_id in existing_ids:
                continue
            preferred_score = 1 if unit.file_path in preferred_files else 0
            candidates.append((preferred_score, _structural_priority(unit.unit_type), unit.unit_id))
        if not candidates:
            return None
        _, _, winner = max(candidates, key=lambda item: (item[0], item[1], -len(item[2])))
        return self.index.units[winner]

    def _append_test(self, context: RetrievalContext, result: TestResult) -> None:
        if any(existing.unit_id == result.unit_id for existing in context.tests):
            return
        context.tests.append(result)

    async def _call_related_examples(
        self,
        registry: ToolRegistry,
        task: str,
        context: RetrievalContext,
    ) -> None:
        for attempt in range(3):
            result = await self._record_call(
                registry,
                "get_related_examples",
                {"query": task},
                context,
            )
            if result is not None:
                context.examples.extend(result.examples)
                return
            context.notes.append(f"related_examples_retry_{attempt + 1}")
        context.notes.append("related_examples_degraded")

    async def _record_call(
        self,
        registry: ToolRegistry,
        tool_name: str,
        arguments: dict[str, str],
        context: RetrievalContext,
    ) -> Any | None:
        start = time.monotonic()
        try:
            result = await registry.execute(tool_name, **arguments)
        except ToolError as exc:
            context.tool_calls.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    success=False,
                    latency_ms=(time.monotonic() - start) * 1000,
                    error=str(exc),
                )
            )
            return None
        except Exception as exc:
            context.tool_calls.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    success=False,
                    latency_ms=(time.monotonic() - start) * 1000,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            return None

        context.tool_calls.append(
            ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                success=True,
                latency_ms=(time.monotonic() - start) * 1000,
            )
        )
        return result


def _terms(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() or char == "_" else " " for char in text)
    raw_terms = normalized.split()
    split_terms = normalized.replace("_", " ").split()
    return {
        term
        for term in [*raw_terms, *split_terms]
        if len(term) > 2 and term not in _STOPWORDS
    }


def _expanded_terms(text: str) -> set[str]:
    terms = set(_terms(text))
    for term in list(terms):
        terms.update(_ALIASES.get(term, set()))
        terms.update(_stem_variants(term))
    return {term for term in terms if len(term) > 2}


def _stem_variants(term: str) -> set[str]:
    variants: set[str] = set()
    if term.endswith("ies") and len(term) > 4:
        variants.add(f"{term[:-3]}y")
    if term.endswith("s") and len(term) > 4:
        variants.add(term[:-1])
    if term.endswith("ed") and len(term) > 4:
        variants.add(term[:-2])
        variants.add(f"{term[:-2]}e")
    if term.endswith("ing") and len(term) > 5:
        variants.add(term[:-3])
        variants.add(f"{term[:-3]}e")
    return variants


def _score_unit(unit: Any, terms: set[str]) -> float:
    unit_id = unit.unit_id.lower()
    name = unit.name.lower()
    docstring = (unit.docstring or "").lower()
    file_path = unit.file_path.lower()
    body = unit.body.lower()
    name_tokens = _identifier_tokens(unit.name)
    id_tokens = _identifier_tokens(unit.unit_id)
    signature_tokens = _identifier_tokens(unit.signature)
    body_tokens = _identifier_tokens(unit.body[:4000])
    parent_tokens = _identifier_tokens(unit.parent_class or "")

    score = 0.0
    for term in terms:
        if term == name or term in name_tokens:
            score += 18
        if term in parent_tokens:
            score += 9
        if term in id_tokens:
            score += 7
        elif term in unit_id:
            score += 5
        if term in signature_tokens:
            score += 4
        if term in file_path:
            score += 3
        if term in docstring:
            score += 2
        if term in body_tokens:
            score += 1.5
        elif term in body:
            score += 0.5

    overlap = terms & (name_tokens | id_tokens | signature_tokens)
    score += min(len(overlap), 8) * 2
    if unit.unit_type == "class" and terms & {"send", "merge", "read", "copy", "call", "helper"}:
        score -= 3
    return score


def _intent_score(unit_id: str, terms: set[str]) -> float:
    normalized_unit_id = unit_id.lower().replace("_", "")
    score = 0.0
    for triggers, fragments in _INTENT_HINTS:
        if not triggers.issubset(terms):
            continue
        for rank, fragment in enumerate(fragments):
            normalized_fragment = fragment.lower().replace("_", "")
            if normalized_fragment in normalized_unit_id:
                score += max(20.0, 80.0 - (rank * 4))
                break
    return score


def _identifier_tokens(text: str) -> set[str]:
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    raw = re.findall(r"[A-Za-z0-9_]+", expanded.lower())
    tokens: set[str] = set()
    for item in raw:
        tokens.add(item)
        tokens.update(part for part in item.split("_") if len(part) > 1)
    return {token for token in tokens if len(token) > 1 and token not in _STOPWORDS}


def _structural_priority(unit_type: str) -> int:
    if unit_type in {"method", "function"}:
        return 3
    if unit_type == "class":
        return 2
    return 1


def _context_ranking_prompt(
    task: str,
    candidates: list[str],
    preferred_files: list[str],
    failure_hints: list[str],
) -> str:
    preferred = ", ".join(preferred_files) or "(none)"
    hints = ", ".join(failure_hints) or "(none)"
    candidate_lines = "\n".join(f"- {candidate}" for candidate in candidates)
    return f"""Rank the best code units to inspect for this Python coding task.

Return exactly:
units: comma-separated unit ids in descending relevance

Task:
{task}

Preferred files:
{preferred}

Failure hints:
{hints}

Candidates:
{candidate_lines}
"""


def _extract_csv_field(content: str, field: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(field)}\s*:\s*(?P<value>.+)$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(content)
    if match is None:
        return []
    value = match.group("value").strip()
    if value.lower() in {"blank", "none", "n/a"}:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
