# Native repository understanding evaluation

This opt-in harness compares the actual CodeGraph library (A), PowerContext's native Python engine (B), and bounded ordinary file tools (C). It is not a product dependency. CodeGraph is called through a local Node process, without MCP. All arms receive the same historical source snapshot, ordinary tools, task prompt, output budget, and model configuration.

Keep generated results, conversations, logs and caches outside version control. Local aggregate snapshots are stored under `.venv/evaluation/native_code/results/`; `evaluation/native_code/results/` is also ignored to prevent accidental commits. Experiment and validation reports are archived locally under `.venv/docs/{en,zh}/rfcs/`. The repository contains the evaluation code, task definitions, scoring criteria and core design.

The checked-in case catalog contains four independent protocol pilots and sixteen formal tasks: eight real historical repairs, four understanding tasks, and four impact tasks. Historical repair admission requires a failing baseline and a passing reference with the hidden regression suite. The reference and hidden tests remain outside model workspaces. Sub-agents, network access, Git history, and other checkouts are not exposed through tools. Repository test execution uses `bubblewrap`; unrestricted execution is not a fallback. Hidden grading restores trusted tests so model changes cannot suppress them.

Prerequisites: a source development installation (`uv sync --extra code`), Git, Linux `bubblewrap`, a local CodeGraph checkout with its built library and installed grammars, Node compatible with that checkout, and an explicitly authorized model endpoint. The environment file supplies inference settings. No production database is used for engine A/B/C evaluation.

```bash
python -m evaluation.native_code.prepare \
  --repository /absolute/powercontext \
  --output /absolute/evidence/cases --phase all

python -m evaluation.native_code.run \
  --cases /absolute/evidence/cases --output /absolute/evidence/pilot \
  --env-file /absolute/server.env --codegraph /absolute/codegraph \
  --node /absolute/node --phase pilot --repeats 1 --rounds 24

python -m evaluation.native_code.run \
  --cases /absolute/evidence/cases --output /absolute/evidence/formal \
  --env-file /absolute/server.env --codegraph /absolute/codegraph \
  --node /absolute/node --phase formal --repeats 3 --rounds 24 --jobs 2
```

Complete pilots and freeze `rubrics.json`, engine/runner/reviewer hashes, model settings, and budgets before formal execution. The formal schedule contains 144 valid runs when every paired triple completes. Seeded Latin rotation gives each arm each execution position once across three repetitions. A provider transport, timeout, rate-limit or service failure invalidates the complete triple; up to three attempts are retained. HTTP 400, including a provider rejecting the model's malformed tool arguments, is a valid model/protocol failure and is not retried away. Engine failures and ordinary task timeouts are also results. A failed triple after retries remains explicitly invalid.

Before admitting a run, verify both adapters on known source: nonempty results, relative paths, exact source hashes and ranges, path filtering, and relationship queries. `python -m evaluation.native_code.preflight --help` describes the deterministic adapter probe. The registered protocol uses two concurrent triples; local probes at higher concurrency exceeded the five-second query deadline. Protocol 5 also requires a nonempty `prepare_context` symbol query for each A/B run before starting the Agent. Its cost is included in setup, and its result is not delivered to the model. An adapter that silently drops every result invalidates the comparison; preserve that cohort and its costs separately instead of treating it as engine quality evidence.

The model has at most 24 response rounds and a 480-second investigation budget by default. Every tool response is bounded to 16000 UTF-8 bytes. Token usage is recorded after each model response; the harness reserves a final-answer turn before exhausting its 320000 aggregate prompt-token and 20000 completion-token admission budgets. A provider's in-flight response can cross an admission threshold; actual usage remains in the record. Missing usage fields are unknown, never zero. The same ending rule applies to every arm.

Each run retains the model conversation, usage, raw engine responses, captured manifest, engine timings, candidate changes, and hidden grading output. Source hashes and a common renderer prevent one arm from silently receiving different source ranges or a larger output budget. A/B use a common capture and before/after freshness check; native checks remain active and their cost is included. This does not imply that CodeGraph itself implements PowerContext's freshness contract. Native-only deletion/baseline semantics have separate acceptance tests.

`rubrics.json` fixes evidence-review criteria and release thresholds. Blind automated evidence review is separate from independent human review. A passing deterministic fixture or a small paired sample does not establish general repair non-inferiority. Report repair, understanding, and impact results separately; cluster confidence intervals by task, not by repeated run. Report all attempts and the mutually successful paired subset, including failures and timeouts. Do not report currency cost unless the actual provider prices and complete usage are available.

After the formal run, review answers against their cited historical source without exposing arm names or investigation traces, then calculate task-cluster intervals:

```bash
python -m evaluation.native_code.review \
  --experiment /absolute/evidence/formal --cases /absolute/evidence/cases \
  --output /absolute/evidence/blind-review --env-file /absolute/server.env
python -m evaluation.native_code.summarize \
  --experiment /absolute/evidence/formal --review /absolute/evidence/blind-review \
  --output /absolute/evidence/summary.json
python -m evaluation.native_code.audit \
  --experiment /absolute/evidence/formal --output /absolute/evidence/execution-audit.json
```

The automated review requires all four registered criteria, checked citations, and no major unsupported claim for its `adequate` flag. Missing answers fail; unavailable reviews remain unknown. Its strict source-range checks and the configured model can introduce grading error. Raw answers, excerpts and verdicts are retained for independent review. An interval meeting the numerical non-inferiority rule is only a sample statistic: degenerate intervals, small task counts, weak absolute success, and lack of independent human review prevent a general release claim.

The evidence reader accepts explicit colon/hash citations, Markdown-delimited paths followed by `L12` or prose `lines 12–20`, and separate comma-delimited ranges. Open-ended ranges remain unknown; it does not invent ranges for bare paths. The reviewer protocol records its own version and the citation-parser hash. If a parser defect is found after task execution, archive the original review and its costs, re-review every fixed answer under a separately recorded reviewer protocol, and disclose the correction without changing task records or repair grades.

The supplementary execution audit does not change frozen primary scores. It distinguishes unavailable tool names, argument errors, repairs without edits, nonempty graph responses, and source-range overlap with final citations. Overlap does not establish correctness or causal attribution. A provider request that returns no response has unknown token usage even if earlier requests returned complete usage: returned-response sums are observable lower bounds, and the audit marks the complete attempt total unknown. Do not interpret primary all-attempt observed token sums as complete billing totals.

Task time includes model investigation and its tool calls. The separate `cold_seconds` covers engine construction and its readiness probe. Recorded `wall_seconds` starts after copying the input workspace and ends before closing the engine; it includes engine setup, task execution and hidden grading when applicable. Input copying, queue waiting and engine teardown are outside that interval, so this field is not complete end-to-end evaluation cost.

Local deterministic checks can run without a model:

```bash
python -m evaluation.native_code.static_gold --output /absolute/evidence/static-gold
python -m evaluation.native_code.benchmark \
  --repository /absolute/powercontext --output /absolute/evidence/performance
```

The small static fixture has explicit source-defined labels and negative cases; its report identifies the pending independent human audit. The benchmark captures real current files into an isolated repository and measures cold build, ten-file synchronization, and full query latency including freshness checks. RSS is reported separately for the parent and largest child, not as a fabricated combined peak.

The opt-in `test_native_code_automatic_context_controlled_experiment` under `tests/e2e/real_experience_skill/test_native_code.py` is an independent B0/B1 experiment. It uses the same engine, historical constraint and total context budget, with three repetitions of one synthetic workflow. It checks real model answers, retention of the hidden historical constraint, and follow-up calls. Its results do not enter the engine A/B/C scores.
