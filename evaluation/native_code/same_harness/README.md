# Same-harness native engine comparison

Measured results: [English report](../../../docs/en/rfcs/0000-native-git-code-understanding-same-harness.md)
and [中文报告](../../../docs/zh/rfcs/0000-native-git-code-understanding-same-harness.md).
The 36-run cohort scores OFF 10/12, CodeGraph 11/12 and native 11/12. Native
increases median paired time by 24.1% and input tokens by 34.4% against CodeGraph;
equal pass totals do not establish noninferiority or an efficiency advantage.

This experiment replaces the engine below the frozen worktree5 optimized
integration. It reuses the exact reference `agent_worker.py`, including its
PydanticAI tools, prompts, model settings, preparation, limits, test execution and
answer scoring. `worker.py` injects `NativeAdapter` only for the native arm.

The three conditions are OFF, optimized CodeGraph, and the native engine behind
the same optimized integration. Each of the original six tasks runs twice per
condition, in the original serial rotation. All three conditions are rerun; the
previous report is historical context rather than a concurrent control.

The integration retains its source capture, freshness checks, exact-file filter,
same-name relationship guard, prepared evidence selection and byte limits.
`policy.py` translates the frozen `engine.cjs` policy; deterministic fixtures
compare their outputs, including errors, ambiguity, cycles, diamond paths and
result limits. Native extraction, lexical/import resolution, SQLite storage and
search ranking come from the previously delivered wheel without changes.

The shared policy deliberately retains the CodeGraph-specific same-name guard.
Results therefore measure replacement under that integration, not the native
service's unrestricted relationship coverage, own context builder or incremental
cache behavior. Native evidence uses the original public response schema;
resolved relationships map to `tree-sitter`, candidates to `heuristic`.

The reference is `/data/codex-tmp/codegraph-comprehensive-20260921`. The independent
run directory is `/data/codex-tmp/native-code-same-harness-20260922`. Neither the
reference evidence nor worktree5 is modified. Credential values are never copied
into evidence. The existing `.env` is read by the unchanged configuration loader.

## Reproduction

Use a fresh output directory. Install the frozen native wheel into an isolated
Python 3.14 environment under `<output>/native-venv`, with the pinned parser and
Pydantic dependencies. The performed installation uses a `.pth` dependency path
to the existing worktree4 Python 3.14 site-packages; the installed native wheel
takes precedence. For byte-identical September 22 replay, supply the native source
from commit `fda17147c35058f7f4c495e68a820940d7635305` to `--native-source`;
the published telemetry module has a license-header-only change.
`setup.py` verifies all 15 native module bytes and records
parser dependency hashes. Keep the same worktree5 Agent interpreter to preserve
its PydanticAI dependency versions.

```bash
python evaluation/native_code/same_harness/setup.py \
  --reference /data/codex-tmp/codegraph-comprehensive-20260921 \
  --output /data/codex-tmp/native-code-same-harness-20260922 \
  --native-source /home/jingshun.tq/project/CE/teingi/worktree4/powercontext \
  --agent-python /home/jingshun.tq/project/CE/teingi/worktree5/powercontext/.venv/bin/python

PYTHONPATH=<output>/integration/src <agent-python> <output>/bridge/preflight.py --output <output>
<agent-python> <output>/bridge/run.py --output <output>
```

The controller stops at incomplete prior attempts rather than overwriting them.
Ordinary task failures, schema validation failures and timeouts remain in the
cohort. Infrastructure errors are reported explicitly. No successful-only retry
selection or treatment changes are permitted during the formal run.

Scores use the original fixed tests and exact target/caller locations. Passing
those tests is not a claim of production patch quality. Report the independent
permission-boundary repair check separately from the preregistered test score.
Model-returned token counts are observed usage, not billed prices; unavailable
request usage remains unknown. Task timing includes preparation but excludes
indexing and final independent tests, matching the reference worker.

## Scoring and evidence

The executed September 22 wrapper omitted registration of the dynamically loaded
reference module in `sys.modules`. Pydantic consequently could not resolve the
analysis answer's `Location` type after the Agent returned its final text. This
does not affect the model's string output type, prompts or tool schemas. The raw
answer is saved before that validation, so it remains available for uniform
offline scoring. The executed wrapper is retained under the evidence directory's
`bridge/`; never replace it with a corrected delivery copy.

`rescore.py` registers the byte-identical reference module, verifies tool schema
equality and checks the three gold answers plus incorrect, missing and ambiguous
answer fixtures. After every scheduled run has finished, it scores all 18 fixed
analysis answers using the original parser and exact criteria. It does not make
model calls or modify raw records. All 18 repair records remain unchanged.
Execution failures without a final answer remain failures.

```bash
PYTHONPATH=<output>/integration/src <agent-python> \
  evaluation/native_code/same_harness/rescore.py --output <output>
<agent-python> evaluation/native_code/same_harness/audit.py --output <output>
```

Use `corrected-summary.json` and `corrected-agent-runs.csv` for the September 22
primary results. Keep `runs/`, the raw `final-summary.json`,
`scorer-import-diagnostic.json` and `scorer-correction.json` alongside them. The
correction records raw result hashes and every before/after analysis grade.
`final-audit.json` verifies cohort completeness, frozen files, model identity,
source/test integrity and preparation budgets independently of answer grading.

The original `repair_quality.py`, with only its integration source path changed,
performs the supplemental unreadable-file check after timed runs. Its outcome is
reported separately from the unchanged primary metric. Repair patches and
conversations are experiment artifacts, not changes applied to the user checkout.

The published helpers load the frozen integration API dynamically and support both
package imports and direct execution from a copied `bridge/` directory. Publication
validation replays all 13 policy fixtures, 12 scorer fixtures and 18 saved analysis
answers. `provenance.delivery_files` identifies the original delivery snapshot;
`provenance.publication_delivery` identifies the publication helpers. The executed
bridge and recorded cohort results remain unchanged. Native executable Python ASTs
are unchanged; the telemetry license header is recorded separately in provenance.
