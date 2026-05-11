# EVAL.md — Benchmark Tasks + Scoring

## Target Codebase: httpx
Clone: `git clone https://github.com/encode/httpx ./target/httpx`
Version: pin to latest stable tag before running eval.
Do not use main/HEAD — pin so results are reproducible.

---

## The 10 Tasks

### TASK 01 — Easy
**ID:** task_01
**Description:** Add a `timeout_seconds` property to the `Request` class
that returns the request timeout as a float in seconds.
If no timeout is set, return None.
**Expected files modified:** `httpx/_models.py`
**Expected behavior:** `request.timeout_seconds` returns float or None
**Should be impossible:** False
**Difficulty:** easy

---

### TASK 02 — Easy
**ID:** task_02
**Description:** Add an `is_redirect` property to the `Response` class
that returns True if the status code is in the 3xx range.
**Expected files modified:** `httpx/_models.py`
**Expected behavior:** `response.is_redirect` returns bool
**Should be impossible:** False
**Difficulty:** easy

---

### TASK 03 — Easy
**ID:** task_03
**Description:** Write pytest tests for the existing `URL.copy_with()` method.
Cover: changing scheme, changing host, changing path, changing query params,
and combining multiple changes at once.
**Expected files modified:** `tests/test_url.py` (new tests added)
**Expected behavior:** All new tests pass with existing httpx code unchanged
**Should be impossible:** False
**Difficulty:** easy

---

### TASK 04 — Medium
**ID:** task_04
**Description:** Add a `default_encoding` parameter to `Client.__init__`
that sets the default response encoding when the server does not specify one.
Must wire through to response decoding.
**Expected files modified:** `httpx/_client.py`, `httpx/_models.py`
**Expected behavior:** `Client(default_encoding="latin-1")` uses latin-1
when response has no charset header
**Should be impossible:** False
**Difficulty:** medium
**Note:** Tests retrieval of multi-file dependencies (Client init → Response decode)

---

### TASK 05 — Medium
**ID:** task_05
**Description:** Add a `log_requests` parameter to `Client.__init__` that,
when True, logs every request method + URL + response status code + elapsed
time to Python's standard logging at INFO level.
**Expected files modified:** `httpx/_client.py`
**Expected behavior:** `Client(log_requests=True)` produces log output per request
**Should be impossible:** False
**Difficulty:** medium

---

### TASK 06 — Medium (deliberate bug)
**ID:** task_06
**Description:** The `Client.headers` property currently does not correctly
merge instance-level default headers with per-request headers when the same
header key appears in both. Fix this so per-request headers take precedence
over instance defaults.
**Expected files modified:** `httpx/_client.py`, `httpx/_merging.py`
**Expected behavior:** per-request headers override instance headers for same key
**Should be impossible:** False
**Difficulty:** medium
**Note:** Tests whether reviewer catches regressions. Generator may introduce
new bugs while fixing this. Reviewer must catch them.

---

### TASK 07 — Hard
**ID:** task_07
**Description:** Add a `DigestAuth` class to `httpx/_auth.py` that implements
HTTP Digest Authentication (RFC 7616). Must integrate with the existing
`Auth` base class pattern. Must work with both `Client` and `AsyncClient`.
Write tests covering successful auth and 401 challenge handling.
**Expected files modified:** `httpx/_auth.py`, `tests/test_auth.py`
**Expected behavior:** `DigestAuth(username, password)` can be passed to
Client's auth parameter and handles digest challenge correctly
**Should be impossible:** False
**Difficulty:** hard
**Note:** Multi-file retrieval test. Navigator must find Auth base class,
existing BasicAuth implementation, and test patterns.

---

### TASK 08 — Hard
**ID:** task_08
**Description:** Implement a `CacheTransport` class that wraps an existing
transport and caches GET responses in memory. Cache key is the full URL.
Respect `Cache-Control: no-cache` and `Cache-Control: no-store` headers.
Cache entries expire after TTL (configurable, default 60s).
**Expected files modified:** `httpx/_transports/`, new file `httpx/_cache.py`
**Expected behavior:** Second identical GET returns cached response,
no-cache header bypasses cache, TTL expiry works
**Should be impossible:** False
**Difficulty:** hard
**Note:** Tests navigation of transport abstraction layer.

---

### TASK 09 — Hard
**ID:** task_09
**Description:** Add a `raise_on_4xx` and `raise_on_5xx` parameter to
`Client.__init__` that automatically raises `HTTPStatusError` for 4xx and
5xx responses respectively without needing to call `response.raise_for_status()`.
**Expected files modified:** `httpx/_client.py`
**Expected behavior:** `Client(raise_on_4xx=True)` raises on 404,
`Client(raise_on_5xx=True)` raises on 500, both can be combined
**Should be impossible:** False
**Difficulty:** hard

---

### TASK 10 — Impossible
**ID:** task_10
**Description:** Make all httpx requests synchronous by removing the async
transport layer entirely. All methods currently using `async/await` should
become regular synchronous functions.
**Expected files modified:** None
**Expected behavior:** Agent detects this is impossible in PLAN phase.
Returns IMPOSSIBLE with explanation that this contradicts the async
transport architecture and would require a full rewrite.
**Should be impossible:** True
**Difficulty:** impossible
**Scoring:** PASS if agent detects in PLAN phase. FAIL if agent attempts
generation. PARTIAL if agent detects after iteration 1-2.

---

### TASK 11 — Budget Exceeded
**ID:** task_11
**Description:** Add a `max_response_size` parameter to `Client.__init__`
that limits the maximum response body size in bytes. If exceeded, raise
a `ResponseTooLargeError`. Run this task with a $0.02 budget ceiling
(extremely low) so the agent must complete in 1-2 iterations or hit
the budget ceiling.
**Expected files modified:** `httpx/_client.py`, `httpx/_exceptions.py`
**Expected behavior:** Agent either completes within budget or halts
cleanly with a budget report showing completed vs remaining work.
**Should be impossible:** False
**Difficulty:** medium
**Scoring:** PASS if agent completes within budget OR halts cleanly with
a budget report. FAIL if agent crashes or loops without budget check.

---

### TASK 12 — Failure Recovery (Unreliable Tool)
**ID:** task_12
**Description:** Add a `request_id` header to every outgoing request
using a UUID4. The agent must use the unreliable `get_related_examples`
tool to find similar patterns in the codebase. This tool fails 30% of
the time. The agent must recover from tool failures and complete the task.
**Expected files modified:** `httpx/_client.py`
**Expected behavior:** Agent recovers from unreliable tool failures
using retry-with-backoff or re-plan-with-alternative-tools strategy.
**Should be impossible:** False
**Difficulty:** medium
**Scoring:** PASS if agent recovers from tool failure and completes.
FAIL if agent crashes on tool failure. PARTIAL if agent skips the
unreliable tool entirely without attempting it.

---

## Scoring Methodology

### Per-task score
```python
class TaskScore(BaseModel):
    task_id: str
    passed: bool
    impossible_correctly_detected: bool  # only for task_10
    iterations_used: int                 # 0 if impossible
    cost_usd: float
    time_seconds: float
    static_passed: bool
    tests_passed: bool
    review_passed: bool
    failure_reason: str | None
```

### Aggregate score
```python
class BenchmarkReport(BaseModel):
    combo: str                          # "a" or "b"
    pass_rate: str                      # "8/10"
    impossible_detected: bool           # task_10 result
    avg_iterations: float
    avg_cost_usd: float
    avg_time_seconds: float
    total_cost_usd: float
    tasks: list[TaskScore]
```

### Pass criteria per task
- PASS: all 3 verification layers pass
- FAIL: any layer fails after 5 iterations
- IMPOSSIBLE: agent returns IMPOSSIBLE in PLAN phase (only valid for task_10)
- PARTIAL: not counted as pass but noted

### Recall measurement (separate from 10 tasks)
Run 10 fixed retrieval queries (defined in ARCHITECTURE.md).
For each query, manually label which units are relevant (ground truth).
Record which units the navigator retrieved.
Compute precision and recall per query.
Compare against grep-based baseline.
Report in README.

---

## Running the Benchmark

```bash
# Clone and pin httpx
git clone https://github.com/encode/httpx ./target/httpx
cd ./target/httpx && git checkout 0.28.1 && cd ../..

# Build tree index
python -m src index --path ./target/httpx

# Run benchmark with Combo A (Gemini Flash baseline)
python -m src eval --combo a --output eval/results/combo_a.json

# Run benchmark with Combo B (Haiku + Sonnet)
python -m src eval --combo b --output eval/results/combo_b.json

# Generate comparison report
python -m src eval report \
  --combo-a eval/results/combo_a.json \
  --combo-b eval/results/combo_b.json \
  --output eval/results/final_report.json
```

---

## Expected Results (estimate before running)

| Task | Combo A (Flash) | Combo B (Haiku+Sonnet) |
|------|----------------|----------------------|
| 01 (easy) | PASS, 1 iter | PASS, 1 iter |
| 02 (easy) | PASS, 1 iter | PASS, 1 iter |
| 03 (easy) | PASS, 1-2 iter | PASS, 1 iter |
| 04 (medium) | PASS, 2-3 iter | PASS, 1-2 iter |
| 05 (medium) | PASS, 2 iter | PASS, 1-2 iter |
| 06 (medium+bug) | FAIL or 3-4 iter | PASS, 2-3 iter |
| 07 (hard) | FAIL or 4-5 iter | PASS, 3-4 iter |
| 08 (hard) | FAIL | PASS, 4-5 iter |
| 09 (hard) | PASS, 3 iter | PASS, 2 iter |
| 10 (impossible) | FAIL (attempts gen) | PASS (detects in PLAN) |
| 11 (budget-exceeded) | PASS (halts cleanly) | PASS (halts cleanly) |
| 12 (failure-recovery) | FAIL or 3-4 iter | PASS, 2 iter |

Predicted: Combo A = 7/12, Combo B = 11/12
Actual results will differ — run it and report real numbers.