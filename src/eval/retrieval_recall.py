"""Retrieval recall measurement against a grep-style lexical baseline."""

from __future__ import annotations

from pathlib import Path

from src.indexer.indexer import index_codebase
from src.retrieval.navigator import Navigator
from src.schemas import (
    ParsedUnit,
    RetrievalEvalQuery,
    RetrievalEvalReport,
    RetrievalEvalScore,
    TreeIndex,
)

DEFAULT_RETRIEVAL_QUERIES: list[RetrievalEvalQuery] = [
    RetrievalEvalQuery(
        query="How does Client send a request?",
        relevant_units=[
            "httpx._client.Client.send",
            "httpx._client.Client._send_handling_auth",
            "httpx._client.Client._send_handling_redirects",
            "httpx._client.Client._send_single_request",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are request headers merged?",
        relevant_units=[
            "httpx._client.BaseClient._merge_headers",
            "httpx._client.BaseClient.build_request",
        ],
    ),
    RetrievalEvalQuery(
        query="Where is timeout configuration normalized?",
        relevant_units=[
            "httpx._config.Timeout",
            "httpx._config.Timeout.__init__",
            "httpx._config.Timeout.as_dict",
            "httpx._client.BaseClient._set_timeout",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are response status helpers defined?",
        relevant_units=[
            "httpx._models.Response.is_success",
            "httpx._models.Response.is_redirect",
            "httpx._models.Response.is_client_error",
            "httpx._models.Response.is_server_error",
            "httpx._models.Response.is_error",
            "httpx._models.Response.raise_for_status",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are event hooks called?",
        relevant_units=[
            "httpx._client.BaseClient.event_hooks",
            "httpx._client.Client._send_single_request",
            "httpx._client.AsyncClient._send_single_request",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are sync and async clients different?",
        relevant_units=[
            "httpx._client.Client.send",
            "httpx._client.AsyncClient.send",
            "httpx._client.Client._send_single_request",
            "httpx._client.AsyncClient._send_single_request",
            "httpx._transports.base.BaseTransport",
            "httpx._transports.base.AsyncBaseTransport",
        ],
    ),
    RetrievalEvalQuery(
        query="Where is response content read and decoded?",
        relevant_units=[
            "httpx._models.Response.read",
            "httpx._models.Response.aread",
            "httpx._models.Response.iter_bytes",
            "httpx._models.Response.aiter_bytes",
            "httpx._models.Response._get_content_decoder",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are transport abstractions defined?",
        relevant_units=[
            "httpx._transports.base.BaseTransport",
            "httpx._transports.base.BaseTransport.handle_request",
            "httpx._transports.base.AsyncBaseTransport",
            "httpx._transports.base.AsyncBaseTransport.handle_async_request",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are auth flows implemented?",
        relevant_units=[
            "httpx._auth.Auth",
            "httpx._auth.Auth.auth_flow",
            "httpx._auth.Auth.sync_auth_flow",
            "httpx._auth.Auth.async_auth_flow",
            "httpx._auth.BasicAuth.auth_flow",
            "httpx._auth.DigestAuth.auth_flow",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are URL mutation helpers defined?",
        relevant_units=[
            "httpx._urls.URL.copy_with",
            "httpx._urls.URL.copy_set_param",
            "httpx._urls.URL.copy_add_param",
            "httpx._urls.URL.copy_remove_param",
            "httpx._urls.URL.copy_merge_params",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are cookies merged onto outgoing requests?",
        relevant_units=[
            "httpx._client.BaseClient._merge_cookies",
            "httpx._models.Cookies.set_cookie_header",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are redirect requests rebuilt?",
        relevant_units=[
            "httpx._client.BaseClient._build_redirect_request",
            "httpx._client.BaseClient._redirect_method",
            "httpx._client.BaseClient._redirect_headers",
            "httpx._client.BaseClient._redirect_url",
            "httpx._client.BaseClient._redirect_stream",
        ],
    ),
    RetrievalEvalQuery(
        query="Where is proxy configuration initialized?",
        relevant_units=[
            "httpx._config.Proxy",
            "httpx._config.Proxy.__init__",
            "httpx._client.BaseClient._get_proxy_map",
            "httpx._client.Client._init_proxy_transport",
            "httpx._client.AsyncClient._init_proxy_transport",
        ],
    ),
    RetrievalEvalQuery(
        query="Where is response encoding determined?",
        relevant_units=[
            "httpx._models._is_known_encoding",
            "httpx._models.Response.encoding",
            "httpx._models.Response.charset_encoding",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are streaming response context managers defined?",
        relevant_units=[
            "httpx._api.stream",
            "httpx._client.BoundSyncStream",
            "httpx._client.BoundAsyncStream",
            "httpx._client.Client.stream",
            "httpx._client.AsyncClient.stream",
        ],
    ),
    RetrievalEvalQuery(
        query="Where are JSON request and response helpers implemented?",
        relevant_units=[
            "httpx._content.encode_json",
            "httpx._models.Response.json",
        ],
    ),
    RetrievalEvalQuery(
        query="Where is proxy transport selected for a URL?",
        relevant_units=[
            "httpx._client.Client._transport_for_url",
            "httpx._client.AsyncClient._transport_for_url",
            "httpx._client.Client._init_proxy_transport",
            "httpx._client.AsyncClient._init_proxy_transport",
        ],
    ),
    RetrievalEvalQuery(
        query="Where is the base URL merged into requests?",
        relevant_units=[
            "httpx._client.BaseClient.base_url",
            "httpx._client.BaseClient._merge_url",
            "httpx._client.BaseClient.build_request",
        ],
    ),
]

STOPWORDS = {
    "are",
    "does",
    "how",
    "the",
    "where",
    "with",
    "defined",
    "implemented",
}


def run_retrieval_recall(
    codebase_path: str | Path,
    output: str | Path | None = None,
    max_units: int = 8,
) -> RetrievalEvalReport:
    """Run the fixed recall suite and optionally write a JSON report."""
    index = index_codebase(codebase_path)
    navigator = Navigator(index=index, max_tool_calls=max_units * 2)
    scores = [
        _score_query(query, index, navigator, max_units)
        for query in DEFAULT_RETRIEVAL_QUERIES
    ]
    report = _aggregate_report(str(codebase_path), scores)
    if output is not None:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def _score_query(
    query: RetrievalEvalQuery,
    index: TreeIndex,
    navigator: Navigator,
    max_units: int,
) -> RetrievalEvalScore:
    relevant = {unit for unit in query.relevant_units if unit in index.units}
    missing = sorted(set(query.relevant_units) - relevant)
    context = navigator.retrieve_sync(query.query)
    tree_units = [unit.unit_id for unit in context.units[:max_units]]
    grep_units = _grep_baseline(index, query.query, max_units)
    tree_precision, tree_recall = _precision_recall(tree_units, relevant)
    grep_precision, grep_recall = _precision_recall(grep_units, relevant)
    return RetrievalEvalScore(
        query=query.query,
        relevant_units=sorted(relevant),
        missing_relevant_units=missing,
        tree_units=tree_units,
        grep_units=grep_units,
        tree_precision=tree_precision,
        tree_recall=tree_recall,
        grep_precision=grep_precision,
        grep_recall=grep_recall,
        tree_beats_grep=(tree_recall, tree_precision) > (grep_recall, grep_precision),
    )


def _grep_baseline(index: TreeIndex, query: str, max_units: int) -> list[str]:
    terms = _terms(query)
    scored: list[tuple[int, int, str]] = []
    for unit in index.units.values():
        score = _lexical_score(unit, terms)
        if score > 0:
            scored.append((score, -len(unit.body), unit.unit_id))
    return [
        unit_id
        for _, _, unit_id in sorted(scored, key=lambda item: (-item[0], item[1], item[2]))[
            :max_units
        ]
    ]


def _lexical_score(unit: ParsedUnit, terms: set[str]) -> int:
    haystack = " ".join(
        [
            unit.unit_id,
            unit.name,
            unit.signature,
            unit.docstring or "",
            unit.file_path,
            unit.body,
        ]
    ).lower()
    score = 0
    for term in terms:
        if term == unit.name.lower():
            score += 12
        if term in unit.unit_id.lower():
            score += 5
        if term in unit.signature.lower():
            score += 3
        if term in haystack:
            score += 1
    return score


def _precision_recall(retrieved: list[str], relevant: set[str]) -> tuple[float, float]:
    precision = 0.0 if not retrieved else len(set(retrieved) & relevant) / len(set(retrieved))
    recall = len(set(retrieved) & relevant) / len(relevant) if relevant else 0.0
    return round(precision, 4), round(recall, 4)


def _aggregate_report(codebase_path: str, scores: list[RetrievalEvalScore]) -> RetrievalEvalReport:
    total = len(scores) or 1
    return RetrievalEvalReport(
        codebase_path=codebase_path,
        query_count=len(scores),
        avg_tree_precision=round(sum(score.tree_precision for score in scores) / total, 4),
        avg_tree_recall=round(sum(score.tree_recall for score in scores) / total, 4),
        avg_grep_precision=round(sum(score.grep_precision for score in scores) / total, 4),
        avg_grep_recall=round(sum(score.grep_recall for score in scores) / total, 4),
        tree_wins=sum(1 for score in scores if score.tree_beats_grep),
        scores=scores,
    )


def _terms(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() or char == "_" else " " for char in text)
    return {
        term
        for term in normalized.replace("_", " ").split()
        if len(term) > 2 and term not in STOPWORDS
    }
