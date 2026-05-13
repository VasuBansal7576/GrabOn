# Reports Evidence Index

This directory contains passing submission evidence and intentionally preserved
failed live attempts. Failed attempts are kept because they are useful debugging
evidence, but they do not count as successful benchmark results.

## Status Legend

| Label | Meaning |
|---|---|
| FIXTURE_PASS | Deterministic offline benchmark evidence. Counts for reproducible harness/scoring, not live provider proof. |
| LIVE_PASS | Real provider completed a coding task end-to-end with verification. |
| SMOKE_PASS | Real provider answered routed stage calls, but did not complete a coding task. |
| RETRIEVAL_PASS | Retrieval eval passed against labeled recall data. |
| PARTIAL | Useful evidence with a known limitation. |
| LIVE_ATTEMPT_FAILED | Failed live run kept as raw evidence. Does not count as a pass. |

## Submission Evidence

| File | Label | Counts Toward | Notes |
|---|---|---|---|
| `combo_a_full.json` | FIXTURE_PASS | Offline benchmark harness | 12/12 deterministic fixture run. |
| `combo_b_full.json` | FIXTURE_PASS | Offline benchmark harness | 12/12 deterministic fixture run. |
| `comparison_a_vs_b_fixture.json` | FIXTURE_PASS | Two-combo comparison | Compares fixture reports with paired stats. |
| `retrieval_recall.json` | RETRIEVAL_PASS | Retrieval requirement | 18-query tree-vs-grep recall report. |
| `provider_stage_smoke_nvidia_mistral.json` | SMOKE_PASS | Live provider routing | NVIDIA routes planning, ranking, parsing, analysis, review. |
| `provider_stage_smoke_groq.json` | SMOKE_PASS | Live provider routing | Groq routes cheap and capable stages. |
| `provider_smoke_live.json` | SMOKE_PASS | Live provider routing | Gemini + NVIDIA smoke evidence. |
| `provider_stage_smoke_live.json` | SMOKE_PASS | Live provider routing | Gemini + NVIDIA routed stage evidence. |
| `combo_a_live_smoke.json` | LIVE_PASS | Gemini live coding | One task passed end-to-end. |
| `combo_nvidia_mistral_live_task03.json` | LIVE_PASS | NVIDIA live coding | Task 03 passed end-to-end. |
| `combo_groq_live_task03.json` | LIVE_PASS | Groq live coding | Task 03 passed end-to-end with non-zero tracked cost. |
| `comparison_nvidia_vs_groq_live_task03.json` | LIVE_PASS | Live provider comparison | Compares two passing live task-03 runs. |
| `submission_cost_summary.json` | PARTIAL | Cost evidence | Aggregates report-level cost; provider dashboard spend is still manual. |

## Preserved Failed Live Attempts

Each file in this table has `submission_status:
LIVE_ATTEMPT_FAILED_NOT_CLAIMED` at the top of the JSON.

| File | Label | Failure Reason |
|---|---|---|
| `combo_a_live_task03.json` | LIVE_ATTEMPT_FAILED | Gemini hit free-tier quota during task 03. |
| `combo_a_live_task08_multifile.json` | LIVE_ATTEMPT_FAILED | Gemini hit free-tier quota during task 08. |
| `combo_nvidia_live_task03.json` | LIVE_ATTEMPT_FAILED | Older NVIDIA run exhausted retries with malformed/TODO patches. |
| `combo_groq_live_task08_multifile.json` | LIVE_ATTEMPT_FAILED | Groq task 08 exhausted 5 iterations; export/new-file diff did not apply cleanly. |
| `combo_nvidia_llama70b_live_task07_multifile.json` | LIVE_ATTEMPT_FAILED | NVIDIA timed out during generation. |
| `combo_nvidia_llama70b_live_task08_multifile.json` | LIVE_ATTEMPT_FAILED | NVIDIA exhausted retries with corrupt diffs. |
| `combo_nvidia_mistral_live_task08_multifile.json` | LIVE_ATTEMPT_FAILED | NVIDIA Mistral timed out during generation. |
