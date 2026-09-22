---
title: Native code understanding A/B/C results
description: Actual CodeGraph, native-engine and ordinary-file-tool runs on fixed public historical tasks, with quality and cost limits.
---

# Native code understanding A/B/C results

Native repository queries and product interfaces passed live acceptance, but this task experiment does not establish improved repair success or the non-inferiority and efficiency gates required for release. The capability remains experimental and disabled by default. See [functional acceptance](0000-native-git-code-understanding-validation.md) and the [repository workflow](../docs/workflows/repository-code.md).

## Protocol

The separate [same-harness report](0000-native-git-code-understanding-same-harness.md) holds the worktree5 integration protocol fixed while replacing the engine. Its tasks, tools and budgets differ from this experiment; results remain separate and are not pooled.

- Date: 2026-09-21; requested model `qwen3.7-plus`, temperature `0.2`, provider-default reasoning.
- A: actual CodeGraph `ba3c21e50d9129d2f5f3843ec3728868ae6d47a1` via a local Node library bridge; B: native Python engine; C: bounded ordinary file tools. Production has no CodeGraph dependency.
- 16 independent tasks × 3 repetitions × 3 arms: 8 historical repairs, 4 understanding tasks, 4 impact tasks. Four pilots are excluded. Repair baselines fail and reference patches pass the trusted hidden checks.
- Identical public historical input, empty read-only history, ordinary tools, prompts, and 16,000-byte renderer; Latin arm rotation. No network, Git history, other checkout or sub-agent tools in the model workspace.
- Per task: 24 response rounds, 480-second investigation budget, 320,000 prompt-token / 20,000 completion-token admission limits; each response allows 2,000 completion tokens. In-flight responses can cross admission limits. Provider requests use a 120-second timeout.
- Provider infrastructure failure invalidates the entire triple, with at most three retained attempts. Ordinary time/round/token limits and malformed model protocol are outcomes. Formal runner version: `native-code-evaluation-5`.
- Two triples run concurrently. Each A/B run must return a nonempty known-symbol result before the Agent starts; this readiness probe is charged to setup and withheld from the model.
- Executed attempts: **171**; selected valid runs: **141**; selected invalid runs: **3**. All original attempts remain in the evidence archive.

## Quality

| Task | A · CodeGraph | B · Native | C · Files |
| --- | --- | --- | --- |
| repair | 3/23 | 0/23 | 1/23 |
| understanding | 1/12 | 0/12 | 1/12 |
| impact | 1/12 | 0/12 | 0/12 |

Repair passes cover 2 independent task(s): `repair-archive-paths, repair-conditional-read`. Passing a registered hidden suite is not a claim that the generated patch is production-ready. The 7 passing attempts (including nonselected retries) have 0 trusted-test mismatches and 0 test-configuration changes in the grading audit; 4 are selected valid passes.

Understanding and impact use arm-blind automated review of the answer, four registered criteria and cited historical source ranges. A result is adequate only when all criteria and citation checks pass without major unsupported claims. Review states: `{"no_answer": 1, "reviewed": 71}`. This is not independent human review; the same configured model can make correlated grading errors.

| Task / pair | Success difference, pp [95% CI] | Independent tasks |
| --- | --- | --- |
| repair:B-A | -12.50 [-29.17, +0.00] | 8 |
| repair:B-C | -4.17 [-12.50, +0.00] | 8 |
| understanding:B-A | -8.33 [-25.00, +0.00] | 4 |
| understanding:B-C | -8.33 [-25.00, +0.00] | 4 |
| impact:B-A | -8.33 [-25.00, +0.00] | 4 |
| impact:B-C | +0.00 [+0.00, +0.00] | 4 |

The repair interval flags are `insufficient_evidence` for B−A and `insufficient_evidence` for B−C, against the registered −5 percentage-point margin. Both lower bounds are below the registered margin, so the numerical non-inferiority rule is not met. Impact B−C has all-zero success in both arms and a degenerate [0, 0] interval; this does not establish equivalent quality. Low absolute success and limited independent task coverage prevent a replacement or release claim.

The success table counts valid runs; comparison estimates average repetitions within each task and then weight tasks equally, so differences need not equal subtraction of the pooled proportions. Intervals use 10,000 bootstrap resamples of independent tasks, with repeated paired differences averaged within each task. The table reports percentage-point differences in success, not relative percentages. Understanding and impact each have only four independent tasks. Unknown reviews are retained as unknown and excluded from available-pair estimates. Comparisons describe admitted valid triples; service failures can depend on task difficulty and bias the retained cohort.

## Evaluation correction

The original reviewer missed explicit citations such as a Markdown-delimited file path followed by `lines 12–20` or `L12–20`, although the task prompt did not prescribe colon notation. This incorrectly made cited answers appear to lack evidence. Thirteen completed review records were archived and excluded; all 72 fixed answers were re-reviewed with unchanged criteria, model settings and task records using `native-code-evidence-review-2`. The repair grades and engine execution records did not change. This is a disclosed post-run evaluator correction, not the originally frozen reviewer.

Nine citation-delivery regressions passed. Across all answers, 37 gained previously omitted explicit ranges; answers with no extracted range decreased from 26 to 7. Open-ended, missing-file and invalid ranges remain explicit errors. Reviewer/parser hashes, retained partial-review usage and corrected-review usage are recorded under `review_correction` in the portable data; their source archive is `corrected-review-source/`. Review costs are separate from the Agent execution table. SDK retries and interrupted requests prevent a complete review billing total. Independent human review remains pending.

## Execution diagnostics

| Observation | A | B | C |
| --- | --- | --- | --- |
| Graph readiness passed / required | 47/47 | 47/47 | N/A |
| all_attempts | 57 | 57 | 57 |
| selected_valid_runs | 47 | 47 | 47 |
| repair_runs | 23 | 23 | 23 |
| repair_no_modified_files | 19 | 21 | 18 |
| runs_with_unknown_tool_calls | 1 | 4 | 2 |
| query_requested_runs | 9 | 10 | 0 |
| query_nonempty_runs | 8 | 10 | 0 |
| query_cited_range_overlap_runs | 7 | 8 | 0 |
| Graph calls, selected valid runs | 25 | 30 | 0 |
| Graph calls without reported errors | 22 | 30 | 0 |
| Reported graph tool errors, including argument errors | 3 | 0 | 0 |

Unknown tool names, wrong arguments and exhausted budgets are valid failures of this fixed Agent setup. These counts can overlap and do not isolate one cause. Nonempty graph delivery and overlap between delivered source ranges and final citations indicate use; neither proves correctness or causal benefit. C has no graph tool.

| Arm | Status counts |
| --- | --- |
| A | {"completed": 45, "infrastructure_error": 4, "round_limit": 3, "token_limit": 5} |
| B | {"completed": 45, "infrastructure_error": 3, "round_limit": 3, "token_limit": 6} |
| C | {"completed": 40, "infrastructure_error": 7, "round_limit": 6, "token_limit": 4} |

## Cost

| Observation, all attempts | A | B | C |
| --- | --- | --- | --- |
| Mean task seconds | 96.26 | 93.88 | 97.70 |
| Task-time observed runs | 53 | 54 | 50 |
| Mean wall seconds, including grading | 160.23 | 147.81 | 123.92 |
| Mean index/setup seconds, including readiness | 41.76 | 32.58 | 0.91 |
| Observed prompt tokens | 14697840 | 15445050 | 13762485 |
| Observed cached prompt tokens | 10797696 | 11025280 | 9989632 |
| Observed uncached prompt tokens | 3900144 | 4419770 | 3772853 |
| Observed completion tokens | 265034 | 264780 | 263444 |
| Attempts with incomplete usage | 4 | 3 | 7 |

Task time measures investigation and tools. Index/setup time covers engine construction and the per-run readiness probe, separately from task time. The recorded wall interval starts after input-workspace copying and ends before engine cleanup; it includes engine setup, task execution and hidden grading when applicable. Input copying, queue waiting and engine cleanup are outside that interval. Runs shared the host with other work, so these are local observations. Attempts with missing task time are excluded from that mean; the observed-run count is shown, and the mean does not represent complete failure cost. Returned-response token sums are lower bounds when a request returns no usage; incomplete requests are not free. Verified provider prices are unavailable, so currency cost is unknown.

The mutually successful triple subset is reported separately:

| Pair / metric | Relative change, % [95% CI] | Independent tasks |
| --- | --- | --- |
| B-A:task_seconds | unknown | 0 |
| B-A:uncached_prompt_tokens | unknown | 0 |
| B-C:task_seconds | unknown | 0 |
| B-C:uncached_prompt_tokens | unknown | 0 |

This subset is selected by outcome and cannot replace all-attempt costs or the quality gate. No general efficiency claim follows from a faster unsuccessful task.

## Discarded comparison and retained costs

Protocol 4 produced 159 attempts but was invalidated: the renderer dropped CodeGraph's absolute source paths, while native queries exceeded the deadline. All delivered graph responses were empty or errors. Those runs cannot compare engine quality. Their conversations, token observations and 46 partial automated reviews remain under `formal/` and `formal-review/`; their usage is included separately in the portable data as `discarded_comparison`, with no mixing into Protocol 5 quality or cost estimates. Adapter fixture and historical-source probes passed before this protocol began.

## Evidence

Portable aggregates, protocol and per-task statistics are in `evaluation/native_code/results/2026-09-21.json`. Local raw evidence is under `/data/codex-tmp/native-code-20260921/`: `formal-2/`, `formal-2-review/`, `formal-2-summary.json`, and `formal-2-audit.json`. `formal-2/frozen-source/` preserves the exact engine and runner files matching the protocol hashes. The raw archive includes conversations, engine responses, source manifests, candidate workspaces and hidden grading logs.

The evaluated native build includes operational tracing, cache clearing and path-boundary counts. The delivery build also explicitly closes SQLite connections after index transactions, removing reliance on garbage collection. Extraction, resolution, ranking and evidence rendering are unchanged. Scores and execution costs belong to the archived protocol build; delivery source hashes are recorded separately in delivery_build and validated with resource regression and package acceptance. Raw evidence remains local; portable aggregates do not replace independent inspection.
