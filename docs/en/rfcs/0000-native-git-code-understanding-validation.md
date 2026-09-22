---
title: Native code understanding implementation and live acceptance
description: Implementation coverage, real model and database validation, and measured performance and release boundaries.
---

# Native code understanding implementation and live acceptance

Date: 2026-09-21. See the [design](0000-native-git-code-understanding.md) and [repository code workflow](../docs/workflows/repository-code.md).

The implementation supports indexing a local Python repository, locating definitions, querying relationships, reading source, synchronizing edits, and inspecting impact. Live SQLite, OceanBase, HTTP/MCP, generation and embedding models, and Codex Hook have passing evidence, including combined history/code context. One model-argument failure and its passing targeted rerun are retained. The capability remains experimental and disabled by default. Ten-file synchronization exceeds its performance target; graph and answer quality still require independent human review.

## Delivered scope

| Capability | Implementation and behavior |
| --- | --- |
| Code understanding | Tree-sitter Python definitions, references and imports; conservative alias, relative import, re-export and lexical resolution; static, candidate and unknown outcomes remain distinct |
| Retrieval and evidence | `map`, `symbols`, `explore`, `callers`, `callees`, `impact`, `affected_tests`, `read`; file hashes, ranges, snippet hashes and relationship witnesses |
| Updates | Content-based change detection, reused syntax facts and global relationship resolution; `changes` and `impact_changes` preserve evidence from deleted code |
| Consistency | Worktree checks before and after queries; stale results fail with `code_changed`; incompatible baselines fail with `baseline_unavailable`; failed builds preserve the published generation |
| Interfaces | Local CLI, Runtime, Python Client, HTTP and PowerContext MCP `query_code`; indexing and synchronization remain local operator actions |
| Context | `include_code=false` by default; one `explore` when enabled, at most four transient code entries within a shared budget, with existing historical section selection preserved |
| Hosts | Explicit Codex and Claude Code Hook opt-in; Codex Scope binding includes the new tool |
| Operations | Stage tracing, aggregate counts and RSS diagnostics; local `clear` respects active readers and other Scopes; path boundaries expose omitted-edge counts only |

Production code lives in `src/powercontext/builtin/code/`, with context assembly in `src/powercontext/builtin/runtime/prepared_code.py`. Production indexing requires no CodeGraph, Node.js, generation model or embeddings. The CodeGraph Node adapter exists only in `evaluation/native_code/` for real-engine comparisons.

Local indexing is verified on Linux and uses POSIX locks, process resource limits and SQLite FTS5. Structural support is initially UTF-8 Python. Dynamic dispatch, reflection and implicit framework relationships may remain unknown. Suggested tests do not replace the project's required test set.

## Tables and data boundaries

The business database receives **zero new tables**. Each code cache has three logical tables:

| Table | Purpose |
| --- | --- |
| `code_nodes` | Files and symbols |
| `code_edges` | Relationships with resolution evidence |
| `code_search_fts` | Full-text search over names, paths, signatures and docstrings |

SQLite FTS5 also maintains five internal shadow tables; they are not additional business entities. Manifests, extraction facts, diagnostics and source files publish with each generation. Inspection of two live-test code caches and one SQLite business database confirmed three logical cache tables and no business `code_*` tables.

Operators configure repository bindings; HTTP callers cannot supply arbitrary server paths. Caches live outside repositories and are isolated by Scope and binding. Tests cover denied Scopes, access revocation, symlinks, credential files, Git clean filters, same-size/same-mtime changes, damaged caches and FIFO files.

## Live service acceptance

The final delivery source was tested with the real generation model, embeddings and isolated databases configured in `.env`. The code-only scenario passed **two tests in 163.94 seconds**. The first combined history/code run had **one pass and one failure in 119.29 seconds**: OceanBase passed; SQLite had already passed HTTP context assembly, but the model omitted a character in the Scope ID of a subsequent MCP call. The harness rejected that argument before calling the tool, so the Hook had not yet run. That failure was retained, and the same SQLite scenario passed a targeted rerun: **one test in 62.86 seconds**. Product code and parameter assertions were unchanged. These are not presented as one failure-free test invocation.

| Final scenario | SQLite | OceanBase |
| --- | --- | --- |
| Code-only HTTP, real-model MCP, installed Codex Hook | Passed; Hook 2.342 seconds | Passed; Hook 4.581 seconds |
| Combined history/code HTTP, real-model MCP, installed Codex Hook | Targeted rerun passed; Hook 2.598 seconds | First run passed; Hook 1.351 seconds |

The combined scenario:

1. Wrote historical Memory through the configured embedding service and retrieved HTTP context containing both history and code.
2. Required the real model, through MCP, to find a randomized identifier in a temporary repository and cite its source, proving that tool output influenced the answer.
3. Ran the installed Codex Hook through the plugin's `uv run --frozen --quiet --project … python hooks/recall.py` command, with a six-second request timeout, an eight-second HTTP budget and a ten-second process deadline, verifying one code block.
4. Used a code-only Hook assembly; history retention was checked by the HTTP combined-context step. Model consumption of a historical constraint is tested separately in the B0/B1 experiment below.
5. Stopped the service and, for OceanBase, dropped the temporary database and verified its absence in the system catalog.

Hook runtime installation/setup was timed separately, ranging from 0.052 to 0.239 seconds across the four passing scenarios. Dependencies were cached locally; these are not cold network-installation timings.

During acceptance, the embedding provider returned HTTP 400 `model_price_error`, blocking an earlier combined replay; failure and cleanup records remain in `live-acceptance-delivery/`. At 23:30 Beijing time on 2026-09-21, a fixed-text probe succeeded with a 1,024-dimensional vector, followed by the passing combined scenarios above. Neither `.env` nor the configured model was changed. The probe is recorded in `embedding-delivery-probe.json`.

Delivery evidence is in `live-code-only-tight/`, `live-combined-tight/` and `live-combined-sqlite-retry/`. The first model-argument failure and all passing records are retained. All five test services stopped; both temporary OceanBase databases were dropped and verified absent. No acceptance data was written to shared business databases.

Claude Code Hook has automated regression coverage. Live host coverage here is the installed Codex Hook subprocess, with a separate model acceptance Agent for tool calls; it is not a complete native Codex autonomous-repair run. No independent seekdb instance was configured, so no live seekdb result is claimed.

Evidence is under `/data/codex-tmp/native-code-20260921/`; each scenario's `native-code-acceptance.json` includes outcomes and cleanup.

## Separate automatic-context experiment

One three-file workflow fixed the model, historical constraint, native engine and 4,000-byte budget. B0 used on-demand queries; B1 included automatic code context. Each arm ran three times.

| Observation | B0 | B1 |
| --- | --- | --- |
| Correct answers | 3/3 | 3/3 |
| Random historical constraint retained | 3/3 | 3/3 |
| Follow-up tool calls | 10, 10, 8 | 9, 9, 7 |
| Injected bytes | 748 | 2,459 |
| Mean task duration | 39.69 seconds | 39.48 seconds |

Automatic injection saved one subsequent query on average in this workflow, with similar duration. One workflow does not establish general benefit or justify enabling it by default. The `context-experiment.json` records under `context-experiment/` are kept separate from engine A/B/C scores.

## Correctness and regression evidence

| Check | Result and boundary |
| --- | --- |
| Focused native engine, PreparedContext, API/MCP and both Hook regressions | 201 passed; additional incremental/full equivalence, failed-publication preservation, FIFO corruption and combined-result truncation cases also passed |
| Delivery additions | Isolated delivery-source native engine, PreparedContext and API/MCP regression: 151 passed; actual OpenTelemetry error export and privacy: one additional pass; cycles/diamonds/nested tests and real Git worktree isolation: two additional passes |
| API contract | `make contract-test`: 48 passed; canonical OpenAPI and generated Python/JavaScript agree |
| Existing cross-component regressions | 83 passed and three skipped; the current MCP transport tool set also passed targeted validation |
| Final non-live full regression | 2,706 passed, 53 skipped, four failed: three used a system Node without the required type-transformation option, and one exceeded an existing ten-second process-start wait |
| Failure revalidation | Explicit Node 22 plus the process-start scenarios and complete integration-guidance evaluation module: 54 passed, one skipped; no product code change was needed |
| Python compatibility | Independent Python 3.11, 3.12 and 3.13 environments each passed 84 tests with one skip; primary regression used 3.14.6 |
| Packages | Isolated source snapshot built an sdist and wheel; all fifteen native module bytes match the workspace; installed Python 3.11 CLI index/status/query/sync/clear passed; an independent installation of only `powercontext[code]` indexed, queried and cleared its cache |
| Documentation | `make docs-test` completed static generation and internal-link checks |
| Types and style | Changed code passed Ruff and scoped type checks; other `make check` hooks passed, while whole-project typing retains four `scripts.*` import diagnostics also reproduced on the unchanged baseline |

These runs overlap and are not added into a total pass count. The full run covers the main implementation; delivery regressions cover cache clearing, tracing and path-boundary counts. One additional public-behavior regression passed for optimized literal-path and glob exclusions. Full-run failures and targeted passes are both retained; targeted success is not described as a failure-free full run. The user's pre-existing untracked `tests/test_sdist.py` was excluded from the full-run command.

One additional SQLite capability-failure check passed: a real SQLite authorizer denied FTS5 virtual-table creation, and build/query operations returned 503 while status reported a missing index and retained the storage failure in `last_build`. This simulates unavailable FTS at the storage boundary without replacing the actual SQLite engine.

A small source-labeled static fixture contains eleven expected call relationships and negative cases for same names, lexical shadowing and dynamic receivers. Static precision/recall and affected-test recall@20 were all 1.0. Labels are source-defined and still await independent human audit; these numbers describe only that fixture.

Evaluation citation-delivery regression passed **nine tests**, covering Markdown, `L` and prose `lines` citations, separate ranges, and invalid-range rejection. The A/B/C report discloses the post-run evaluator correction and source identities.

The final delivery-source native test file passed **37 tests**, including explicit SQLite connection cleanup after index transactions. Performance measurements use that delivery build and the same 1,536-file corpus; raw records are in `performance-final/results.json`. Another host-load window observed 40.73-second indexing and 17.68-second synchronization; differences are not attributed to the connection-close fix.

## Performance and release judgment

Measurements used a fixed 1,536-file PowerContext capture on Linux with 16 visible CPUs and Python 3.14.6. Complete queries include freshness checks. Other workloads were present, so these are local observations.

| Metric | Observation | Initial RFC target |
| --- | --- | --- |
| Cold index | 39.42 seconds | At most 60 seconds |
| Ten-file synchronization | **22.74 seconds**, ten files extracted and 1,526 facts reused | At most five seconds; missed |
| Query p50 / p95 | 0.92 / 1.83 seconds | p95 at most two seconds |
| Logical bytes of cache files | 411,280,913 bytes | Configured per-binding limit |
| Parent / largest-child max RSS | 343,992 / 343,992 KiB | Separate observations, not additive simultaneous process-tree peak |

An earlier measurement of the same corpus observed 48.18 seconds for indexing and 34.39 seconds for synchronization. Host load differed, so the difference is not attributed to a specific optimization. Profiling attributes substantial synchronization cost to global relationship resolution and immutable-generation writes. The explicit functional loop is usable, but the five-second synchronization target is not a service guarantee. Automatic injection remains disabled by default.

Relative task quality and efficiency against CodeGraph and ordinary file tools are reported in the [A/B/C results](0000-native-git-code-understanding-experiment.md). Live service connectivity, the small static fixture and the single-workflow B0/B1 experiment do not substitute for engine comparison or independent human audit.

## Reproduce acceptance

Use a source environment with development dependencies and the `code` extra installed. Live tests call the model in the environment file and create, remove and verify an isolated temporary configured database. Choose a new evidence directory for `--basetemp`; pytest clears that directory.

```bash
TMPDIR=/data/codex-tmp .venv/bin/python -m pytest tests/builtin/test_native_code.py
make contract-test
TMPDIR=/data/codex-tmp .venv/bin/python -m pytest \
  tests/e2e/real_experience_skill/test_native_code.py \
  -k test_native_code_only_with_real_services --run-real-e2e \
  --real-e2e-env-file .env --basetemp /absolute/evidence/new-code-only-run
```

Use `-k test_native_code_with_real_services` for the combined history/code scenario, which needs a working embedding model. Use `-k test_native_code_automatic_context_controlled_experiment` for the independent B0/B1 experiment. Select a different evidence directory each time. Engine A/B/C preparation, execution, review and statistics commands are in `evaluation/native_code/README.md`.

## Evidence retention

The local evidence root is `/data/codex-tmp/native-code-20260921/`, containing contract/regression logs, live service reports, table audits, package checks, static-graph results and performance records. Verification packages use test version `0.0.0`; nothing was committed, pushed or published.

Final packages come from an isolated snapshot containing repository source and task files. Existing user presentations, reports and website build outputs were excluded from the final sdist. Temporary SQLite and graph caches remain as local evidence; external OceanBase test databases were removed and live acceptance servers stopped.
