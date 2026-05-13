# EVAL.md — Benchmark and Retrieval Evaluation

## Eval Shape

This repo now carries two explicit evaluation suites:

1. a 12-task coding benchmark
2. an 18-query labeled retrieval recall suite

That gives 30 explicit eval cases total.

## Benchmark Tasks

The coding benchmark keeps 12 tasks even though the PDF asked for 10, because
the extra two preserve explicit coverage for budget and recovery behavior.

Task mix:

- 3 easy
- 3 medium
- 3 hard
- 1 impossible
- 1 budget ceiling
- 1 failure recovery

The task YAMLs live in `eval/tasks/`.

## Benchmark Scoring

Per-task fields:

- `passed`
- `impossible_correctly_detected`
- `iterations_used`
- `cost_usd`
- `cost_breakdown`
- `time_seconds`
- `static_passed`
- `tests_passed`
- `review_passed`
- `failure_reason`

Aggregate report fields:

- `combo`
- `run_mode`
- `provider_models`
- `pass_rate`
- `impossible_detected`
- `avg_iterations`
- `avg_cost_usd`
- `avg_time_seconds`
- `total_cost_usd`
- `tasks`

## Latest Benchmark Results

Latest local fixture rerun:

| Combo | Run Mode | Pass Rate | Impossible Detected | Avg Iterations | Avg Time | Cost |
|---|---|---:|---:|---:|---:|---:|
| A | fixture | 12/12 | yes | 1.0000 | 2.566s | $0.00 |
| B | fixture | 12/12 | yes | 1.0000 | 2.567s | $0.00 |

## Paired Comparison

The repo now includes a paired report comparison command:

```bash
uv run python -m src compare-eval \
  --left reports/combo_a_full.json \
  --right reports/combo_b_full.json \
  --output reports/comparison_a_vs_b_fixture.json
```

Latest comparison summary:

- pass-rate delta: `0.0`
- iteration delta: `0.0`
- time delta: `0.000999s` in favor of combo `A`
- paired time p-value: `0.387695`

There are also live same-task comparison artifacts:

```bash
uv run python -m src compare-eval \
  --left reports/combo_a_live_task03.json \
  --right reports/combo_nvidia_live_task03.json \
  --output reports/comparison_a_vs_nvidia_live_task03.json

uv run python -m src compare-eval \
  --left reports/combo_a_live_task03.json \
  --right reports/combo_nvidia_mistral_live_task03.json \
  --output reports/comparison_a_vs_nvidia_mistral_live_task03.json

uv run python -m src compare-eval \
  --left reports/combo_nvidia_mistral_live_task03.json \
  --right reports/combo_groq_live_task03.json \
  --output reports/comparison_nvidia_vs_groq_live_task03.json
```

The older live comparison is intentionally kept as raw evidence: Gemini hit
free-tier quota on retry, while an earlier NVIDIA model returned malformed
diffs through all 5 iterations. The newer NVIDIA Mistral task-03 artifact
passed, but the Gemini side of the same-task comparison is still the older
quota-limited run.

## Retrieval Recall Suite

The retrieval suite contains 18 labeled questions over the pinned `httpx`
checkout.

Latest local rerun:

| Method | Query Count | Avg Precision | Avg Recall | Wins |
|---|---:|---:|---:|---:|
| Tree navigator | 18 | 0.5741 | 0.8444 | 18/18 |
| Grep-style baseline | 18 | 0.1528 | 0.3185 | 0/18 |

## Live Provider Evidence

The committed full benchmark artifacts are still fixture-mode, but live proof
is no longer missing:

- `reports/provider_smoke_live.json` records successful live smoke calls for
  both Gemini and NVIDIA.
- `reports/provider_stage_smoke_nvidia_mistral.json` records successful NVIDIA
  live calls across planning, context ranking, error parsing, test analysis, and
  review routes.
- `reports/provider_stage_smoke_groq.json` records successful Groq live calls
  across the same routed stages, using the cheap 8B route for cheap stages and
  the 70B route for heavy stages.
- `reports/combo_a_live_smoke.json` records a real Gemini `--live` coding run
  that completed one benchmark task end-to-end with passing verification and
  non-zero tracked cost.
- `reports/combo_nvidia_mistral_live_task03.json` records a real NVIDIA NIM
  `--live` coding run that completed task 03 end-to-end with static, pytest,
  and reviewer checks passing.
- `reports/combo_nvidia_mistral_live_task08_multifile.json` records a real
  NVIDIA NIM `--live` coding run that completed the task-08 multi-file stress
  case in 2 iterations with static, pytest, and reviewer checks passing.
- `reports/combo_groq_live_task03.json` records a real Groq `--live` coding
  run that completed task 03 end-to-end with static, pytest, and reviewer
  checks passing.
- `reports/combo_nvidia_llama70b_live_task07_multifile.json` and
  `reports/combo_nvidia_llama70b_live_task08_multifile.json` are preserved
  multi-file attempts that did not pass.
- `reports/combo_groq_live_task08_multifile.json` is also preserved. Groq
  improved over NVIDIA by creating the new `httpx/_cache.py` module, but the
  export patch against `httpx/__init__.py` still did not apply cleanly within
  5 iterations.
- `reports/combo_a_live_task08_multifile.json` is preserved as a Gemini
  quota-limited task-08 attempt, not counted as a passing artifact.
- `reports/combo_a_live_task03.json`,
  `reports/combo_nvidia_live_task03.json`, and
  `reports/comparison_a_vs_nvidia_live_task03.json` preserve the current
  stricter live same-task comparison attempt.

## Report Labels

Reports use the following submission labels:

- `FIXTURE_PASS`: deterministic offline benchmark evidence. Useful for
  reproducibility, but not live model proof.
- `LIVE_PASS`: a real provider completed the coding task end-to-end.
- `SMOKE_PASS`: a real provider answered the routed stage, but did not perform
  a full coding task.
- `LIVE_ATTEMPT_FAILED_NOT_CLAIMED`: a failed live run kept for honesty. It is
  not counted as a benchmark pass or provider success.

The failed multi-file reports include the `submission_status` field directly
inside the JSON artifact. The full report index is in `reports/README.md`.

## Honest Reading

- Benchmark reproducibility is good now.
- Retrieval evaluation coverage is broader than before.
- Comparison artifacts are real now, not implied.
- Cost evidence is aggregated in `reports/submission_cost_summary.json`, which
  keeps live report spend separate from `$0.00` fixture evidence.
- Full live benchmark coverage is still thinner than fixture coverage. The repo
  proves multi-provider connectivity, selected live end-to-end coding runs,
  including the task-08 multi-file stress case, and preserves failed live
  attempts without counting them as passes.
