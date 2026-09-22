---
title: Native engine and CodeGraph under the same harness
description: Thirty-six real runs preserving worktree5 tasks, model, tools, budgets and automatic preparation while replacing the backend engine.
---

# Native engine and CodeGraph under the same harness

Measured on 2026-09-22, Beijing time.

**The native engine runs successfully in the same six-task worktree5 experiment, but this cohort does not establish an advantage over CodeGraph.** Complete passes across 36 runs are OFF **10/12**, CodeGraph **11/12**, and native **11/12**. The two ON arms fail different tasks; equal totals do not establish per-task equivalence or noninferiority.

Against CodeGraph, native median paired task time **increases 24.1%**, input tokens **increase 34.4%**, and uncached input **increases 5.8%**. Time increases 25.6% in the ten pairs where both pass. Preparation delivers the target in **4/12 versus 6/12**, with **three native timeouts and one unavailable cache**. These results support continued explicit experimentation and work on integration costs, without justifying a default replacement.

## Primary results

| Metric | OFF | CodeGraph | Native |
| --- | --- | --- | --- |
| Complete passes | 10/12 | 11/12 | 11/12 |
| Complete repair passes | 5/6 | 6/6 | 6/6 |
| Repair artifacts passing fixed tests | 6/6 | 6/6 | 6/6 |
| Complete analysis passes | 5/6 | 5/6 | 5/6 |
| Mean strict recall in Agent analysis answers | 97.22% | 83.33% | 95.83% |
| Median task seconds | 65.119 | 75.654 | 77.649 |
| Median task + index seconds | 65.119 | 80.131 | 98.934 |
| Median preparation seconds | 0.000 | 3.252 | 4.509 |
| Median input tokens | 159,060.5 | 128,643.5 | 95,473.5 |
| Median uncached input | 28,663.0 | 30,147.5 | 28,069.0 |
| Median executed tools | 17.5 | 17.0 | 13.0 |

A loader defect is corrected uniformly for every fixed analysis answer, without model reruns; see the scoring-correction section. Timing, usage and tool records remain unchanged. Each arm has one symlink patch failing the supplemental permission boundary, so 6/6 artifact test passes do not imply regression-free repairs.

## Tasks and paired comparisons

Cells show complete passes; median task seconds; median input tokens.

| Task | OFF | CodeGraph | Native |
| --- | --- | --- | --- |
| Default Topic Memory repair | 1/2; 100.5 s; 399.7k | 2/2; 87.0 s; 252.9k | 2/2; 72.6 s; 130.4k |
| UTF-8 byte-budget repair | 2/2; 71.0 s; 159.1k | 2/2; 58.9 s; 56.0k | 2/2; 58.8 s; 82.4k |
| Untracked symlink repair | 2/2; 125.6 s; 279.8k | 2/2; 93.2 s; 186.8k | 2/2; 148.8 s; 260.0k |
| Budget function callers | 2/2; 39.7 s; 27.1k | 2/2; 46.4 s; 71.3k | 2/2; 89.7 s; 77.4k |
| Lexical normalization callers | 1/2; 53.8 s; 70.9k | 1/2; 70.3 s; 74.6k | 2/2; 55.6 s; 46.9k |
| Automatic eligibility callers | 2/2; 62.4 s; 170.8k | 2/2; 84.4 s; 174.9k | 1/2; 99.6 s; 264.6k |

| Comparison | Pairs | Gains/losses | Faster | Time change | Input change | Uncached change |
| --- | --- | --- | --- | --- | --- | --- |
| off->codegraph | 12 | +2 / −1 | 4/12 | +12.1% | -27.6% | -13.7% |
| off->native | 12 | +2 / −1 | 6/12 | +7.5% | -4.4% | +13.1% |
| codegraph->native | 12 | +1 / −1 | 4/12 | +24.1% | +34.4% | +5.8% |

Paired percentages are medians of within-pair ratios, not ratios of arm medians. Native has a lower group median input count but a higher median paired ratio; these are different statistics and are not interchangeable.

## Retained failures and repair quality

| Run | Failure |
| --- | --- |
| topic-default-0-off | Exhausted 24 model requests; artifact still passed 84 tests |
| lexical-callers-0-codegraph | UnexpectedModelBehavior after invalid graph arguments; no final answer |
| lexical-callers-1-off | MemoryService.search start line reported as 436 instead of 412; 5/6 strict matches |
| eligibility-callers-1-native | _RelationalTriggers._sources reported as _RelationalSources._sources; 3/4 strict matches |

All 18 patches are retained. The supplemental probe makes an ordinary untracked Python file unreadable under UID 1001. The baseline and all first-repeat symlink patches reject indexing; all second-repeat patches instead succeed and classify that file as a `symlink_or_submodule` omission. Broad `OSError` handling causes these three regressions. The fixed tests miss this boundary, and native replacement does not eliminate the error.

## Preparation and tool adoption

| Metric | OFF | CodeGraph | Native |
| --- | --- | --- | --- |
| Runs with prepared code | 0 | 8 | 6 |
| Runs with prepared target | 0 | 6 | 4 |
| Graph attempts | 0 | 4 | 0 |
| Executed graph queries | 0 | 0 | 0 |
| Runs exposed to code evidence | 0 | 8 | 6 |
| Preparation timeouts | 0 | 0 | 3 |
| Preparation cache unavailable | 0 | 0 | 1 |

All four CodeGraph attempts fail before service execution: the model supplies a string operation instead of the required object. Three retry prompts are recorded; another failure terminates the Agent. Native makes no active graph attempts. Automatic preparation still calls the actual engines, but neither a delivered snippet nor a correct final answer independently establishes causality. The shared unfocused-query policy skips both eligibility repetitions in both ON arms.

## Index, query cost and coverage diagnostics

| Engine | Fresh-cache index median s, n=4 | Reuse median s, n=8 | Files inside corpus index cache | Logical MiB |
| --- | --- | --- | --- | --- |
| codegraph | 29.706 | 1.353 | 2 | 85.10 |
| native | 34.954 | 0.853 | 1640 | 162.39 |

| Diagnostic engine | Prompt | Total prepare s | Index copy s | Engine subprocess s |
| --- | --- | --- | --- | --- |
| codegraph | budget-callers | 3.182 | 0.288 | 0.702 |
| codegraph | lexical-callers | 3.824 | 0.165 | 1.195 |
| native | budget-callers | 4.687 | 1.143 | 1.676 |
| native | lexical-callers | 4.347 | 1.542 | 1.034 |

Diagnostics run serially after the cohort, with no model calls and only one observation per engine/prompt. They do not reproduce the timeout/cache failure, erase formal failures or establish the cache error root cause. Some capture/identity stages overlap, so stage times cannot be summed. Native index copying is a visible cost; subprocess time includes Python startup/imports, not just SQL. A fresh application cache does not imply a cold OS page cache.

Native produces facts for 823/823 Python files. Of these, 490 contain 3,936 `unsupported_scope` diagnostics for lambdas, comprehensions and generator expressions; there are no `parse_error` diagnostics. The bridge maps any extraction diagnostic to the old protocol’s `parse_failures`, hence its raw value of 490. These files retain supported extraction while some scopes are skipped; they are neither completely absent nor evidence of complete relationship coverage. Raw fields remain intact with this separate explanation.

## Total observed usage

| Arm | Input | Cache reads | Uncached input | Output |
| --- | --- | --- | --- | --- |
| off | 2,214,698 | 1,837,568 | 377,130 | 43,781 |
| codegraph | 1,633,100 | 1,293,696 | 339,404 | 38,292 |
| native | 1,723,512 | 1,364,736 | 358,776 | 48,352 |

## Conditions and comparison

All three arms use the worktree5 optimized integration at `a677359cd0ae80f164d317b4573ed9a983e22f42`, tree `aa98af2228ac09abb2a2a80065d16183dee4d4ca`. OFF disables code preparation and the graph tool. CodeGraph uses the original optimized CodeGraph 1.6.0 integration. Native replaces only the backend adapter, using the delivered native extraction, resolution, SQLite storage and search implementation.

| Condition | Fixed value |
| --- | --- |
| Tasks | Original 3 seeded repairs and 3 direct-caller analyses, twice per arm |
| Agent | Byte-identical PydanticAI worker, SHA-256 `dc5a19b1460baf83185aaaa6b3d5032c6a0a4af398dd85588906e87a7bfdd911` |
| Model | `qwen3.7-plus`, temperature 0, 5,000 output tokens per response |
| Limits | 24 model requests, 600,000 cumulative tokens, 360-second Agent timeout |
| Tools | Original listing, search, reading, replacement and fixed tests; both ON arms expose the same additional `query_code` schema |
| Code budgets | 5-second queries; 8,000 UTF-8 bytes for preparation, 16,000 for graph responses, 24,000 for generic tool output |
| Preparation | Same symbol focus, unfocused-query omission and `PreparedContextBuilder`; history retrieval and generative recall gate disabled |
| Schedule | Original rotation within task/repeat; 36 serial runs, without concurrent regression or diagnostic workloads |
| Source | Frozen corpus; only local root paths differ in task fields, prompts, seeds and oracles |

Both controls are rerun. The previous worktree5 report's 10/12, 10/12 and 12/12 are historical observations, not concurrent controls or pooled results. This cohort reuses its six-task Agent experiment; it does not repeat that report's HTTP, Hook, vector database or complete retrieval measurements.

## Engine boundary

The native wheel has SHA-256 `488c8fad08977c444bd4e702f53b686ad0d242b3b4b552ca1fd7f943d14427fc`. All 15 native module files match the delivered workspace source. An isolated Python 3.14 environment installs that wheel, with recorded parser versions and dependency hashes. The Agent uses the same worktree5 interpreter and PydanticAI dependencies. A seal covers 1,737 input files and is checked before every run.

The adapter translates the original `engine.cjs` definition selection, same-name relationship guard, caller expansion, traversal and limits into Python. Thirteen deterministic fixtures match JavaScript results and errors, covering ambiguity, file filtering, cycles, diamond paths and limits. Native code supplies indexed symbols and edges, resolution decisions and search ranking.

The shared integration retains source capture, freshness and cache verification, per-query index copies, snippet hydration and byte budgets. Native `facts/` and `source/` files remain in the index and incur the shared scanning and copying costs. These results do not measure the native service's direct immutable-index queries or incremental synchronization. The retained same-name guard can also discard correctly resolved native edges, so this does not establish the native engine's maximum relationship coverage.

## Scoring, time and usage

A complete repair requires normal Agent completion, unchanged tests and passing original fixed tests. Topic Memory and UTF-8 tasks each run 84 tests; the symlink task runs 11. Analysis requires the exact target and complete caller set, including path, qualified name and definition start line, with unchanged source/tests. The three oracles contain 2, 6 and 4 direct callers. All three repair baselines pass and their planted defects fail before formal runs.

Artifact test passes are reported separately: exhausting the request budget while producing a passing patch remains a primary failure. Symlink patches also undergo the original unreadable ordinary-file check, reported separately without rewriting primary scores. Neither check establishes production patch quality. Patch inspection is by this assistant, not an independent human reviewer.

Task time follows the original worker: preparation, model requests and tools, excluding indexing, process startup and final independent tests. Index time is separate. Paired changes use the median of task/repeat ratios. Tokens are service-reported cumulative usage; uncached input equals input minus cache reads. They are neither unique context length nor billed cost. Cache effects, service load and a host without CPU isolation limit performance conclusions.

## Uniform analysis-scoring correction

The experiment wrapper omitted `sys.modules` registration when loading the original worker dynamically. Pydantic therefore could not resolve the analysis answer's `Location` forward reference after the model had returned its final text. The original worker bytes did not change. Its model output type is a string; analysis validation happens only after the model run. The raw final text was saved in `answer_text` before validation.

The sealed runtime stayed unchanged during all 36 runs. After completion, all 18 fixed analysis answers are scored offline with the correctly registered, identical original worker. There are no new model requests, answer edits, changed criteria or outcome-selected retries. Execution failures without final answers remain failures; all 18 repair records stay unchanged. Raw records and failed raw grades are retained; primary tables use the separate `corrected-summary.json`.

Preflight confirms identical tool schemas and acceptance of all three gold answers, while rejecting incorrect qualified names, missing answers and ambiguous double answers. `scorer-correction.json` records each before/after grade and raw record hash. `final-audit.json` checks complete analysis coverage, unchanged model outputs/usage and unchanged repairs. The delivered wrapper fixes registration and adds these scoring checks to preflight; the originally executed wrapper remains archived separately.

## Limits

The 36 runs cover only six independent tasks: three repairs and three analyses. Repeats do not increase the independent task count. These are known regressions and explicit-symbol questions, not a blind new-repository benchmark or native Codex/MCP host evaluation. They describe behavior and failure locations under this integration, without establishing general superiority, noninferiority, billing savings or a default-on release gate.

The earlier native repair result of 0/23 under another historical-task protocol remains in the [A/B/C report](0000-native-git-code-understanding-experiment.md). Its tasks, tools and budgets differ; subtracting those scores cannot establish an engine improvement.

## Evidence and delivery

The local result snapshot is `.venv/evaluation/native_code/results/2026-09-22-same-harness.json`, outside version control; adapters and reproduction instructions are in `evaluation/native_code/same_harness/`. Full local evidence is under `/data/codex-tmp/native-code-same-harness-20260922/`.

| File | Contents |
| --- | --- |
| corrected-summary.json / corrected-agent-runs.csv | Primary aggregate and run-level data |
| runs/ / corrected-runs/ / scorer-correction.json | Raw conversations, patches, outputs and uniform scoring correction |
| formal-freeze.json / final-audit.json | 1,737 sealed files, cohort and correction integrity audits |
| repair-quality.json / patch-inspection.json | Real permission-boundary probes and patch inspection |
| query-diagnostics.json / native-coverage-diagnostic.json | Separate query-stage and partial-coverage diagnostics |
| delivery-preflight.json | Original scorer positive/negative checks for the delivered wrapper, without model calls |

Integrity checks pass: all 36 records are present, actual models are `qwen3.7-plus`, tests and analysis source remain unchanged, sealed inputs and `.env` remain unchanged, and correction affects only analysis grading fields. Production engine code is not retuned for this cohort; worktree5 and historical evidence remain read-only. No business database is created; experiment caches are retained for verification.
