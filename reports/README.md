# Reports Evidence Index

This directory contains both green submission evidence and intentionally
preserved red live attempts. The red files are not hidden because they are useful
debugging evidence, but they do not count as successful benchmark results.

## Status Legend

| Label | Meaning |
|---|---|
| GREEN FIXTURE | Deterministic offline benchmark evidence. Counts for reproducible harness/scoring, not live provider proof. |
| GREEN LIVE | Real provider completed a coding task end-to-end with verification. |
| GREEN SMOKE | Real provider answered routed stage calls, but did not complete a coding task. |
| GREEN RETRIEVAL | Retrieval eval passed against labeled recall data. |
| YELLOW | Useful evidence with a known limitation. |
| RED PRESERVED | Failed live run kept as raw evidence. Does not count as a pass. |

## Submission Evidence

| File | Label | Counts Toward | Notes |
|---|---|---|---|
| `combo_a_full.json` | GREEN FIXTURE | Offline benchmark harness | 12/12 deterministic fixture run. |
| `combo_b_full.json` | GREEN FIXTURE | Offline benchmark harness | 12/12 deterministic fixture run. |
| `comparison_a_vs_b_fixture.json` | GREEN FIXTURE | Two-combo comparison | Compares fixture reports with paired stats. |
| `retrieval_recall.json` | GREEN RETRIEVAL | Retrieval requirement | 18-query tree-vs-grep recall report. |
| `provider_stage_smoke_nvidia_mistral.json` | GREEN SMOKE | Live provider routing | NVIDIA routes planning, ranking, parsing, analysis, review. |
| `provider_stage_smoke_groq.json` | GREEN SMOKE | Live provider routing | Groq routes cheap and capable stages. |
| `provider_smoke_live.json` | GREEN SMOKE | Live provider routing | Gemini + NVIDIA smoke evidence. |
| `provider_stage_smoke_live.json` | GREEN SMOKE | Live provider routing | Gemini + NVIDIA routed stage evidence. |
| `combo_a_live_smoke.json` | GREEN LIVE | Gemini live coding | One task passed end-to-end. |
| `combo_nvidia_mistral_live_task03.json` | GREEN LIVE | NVIDIA live coding | Task 03 passed end-to-end. |
| `combo_groq_live_task03.json` | GREEN LIVE | Groq live coding | Task 03 passed end-to-end with non-zero tracked cost. |
| `comparison_nvidia_vs_groq_live_task03.json` | GREEN LIVE | Live provider comparison | Compares two green live task-03 runs. |
| `submission_cost_summary.json` | YELLOW | Cost evidence | Aggregates report-level cost; provider dashboard spend is still manual. |

## Preserved Red Evidence

Each file in this table has `submission_status:
RED_PRESERVED_FAILURE_NOT_A_PASS` at the top of the JSON.

| File | Label | Why It Is Red |
|---|---|---|
| `combo_a_live_task03.json` | RED PRESERVED | Gemini hit free-tier quota during task 03. |
| `combo_a_live_task08_multifile.json` | RED PRESERVED | Gemini hit free-tier quota during task 08. |
| `combo_nvidia_live_task03.json` | RED PRESERVED | Older NVIDIA run exhausted retries with malformed/TODO patches. |
| `combo_groq_live_task08_multifile.json` | RED PRESERVED | Groq task 08 exhausted 5 iterations; export/new-file diff did not apply cleanly. |
| `combo_nvidia_llama70b_live_task07_multifile.json` | RED PRESERVED | NVIDIA timed out during generation. |
| `combo_nvidia_llama70b_live_task08_multifile.json` | RED PRESERVED | NVIDIA exhausted retries with corrupt diffs. |
| `combo_nvidia_mistral_live_task08_multifile.json` | RED PRESERVED | NVIDIA Mistral timed out during generation. |

