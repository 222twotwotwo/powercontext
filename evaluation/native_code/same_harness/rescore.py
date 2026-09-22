"""Restore the reference validator's module namespace for every fixed answer.

The frozen model worker loaded its reference module without registering it in
sys.modules. Pydantic's forward reference to Location was consequently unresolved
when post-run answer validation began. Model prompts, tools and returned text are
unchanged. Raw runs remain intact; this creates a separately identified correction.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter


def reference_module(path, *, registered):
    name = "registered_reference_scorer" if registered else "unregistered_reference_scorer"
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(f"Cannot load reference scorer from {path}")
    module = importlib.util.module_from_spec(specification)
    if registered:
        sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def grade(module, task, record):
    result = copy.deepcopy(record)
    if "answer_text" in record:
        try:
            result["answer"] = module.decode_analysis_answer(record["answer_text"])
            result["agent_completed"] = True
            result.pop("error_type", None)
            result.pop("http_status", None)
        except (ValueError, TypeError) as error:
            result["agent_completed"] = False
            result["error_type"] = type(error).__name__
            result.pop("answer", None)
    answer = result.get("answer") or {}
    gold = {module.location_key(caller) for caller in task["gold_callers"]}
    actual = {module.location_key(caller) for caller in answer.get("callers", [])}
    matched = len(gold & actual)
    result["score"] = {
        "target_correct": answer.get("target") == task["gold_target"],
        "expected": len(gold),
        "returned": len(actual),
        "matched": matched,
        "precision": matched / len(actual) if actual else 0,
        "recall": matched / len(gold),
        "f1": 2 * matched / (len(gold) + len(actual)),
        "missing": sorted(gold - actual),
        "extra": sorted(actual - gold),
    }
    result["passed"] = (
        result["agent_completed"]
        and result["score"]["target_correct"]
        and actual == gold
        and result["source_unchanged"]
        and result["tests_unchanged"]
    )
    result["evaluation_correction"] = {
        "kind": "reference-module-registration",
        "raw_passed": record["passed"],
        "raw_agent_completed": record["agent_completed"],
        "raw_error_type": record.get("error_type"),
        "model_recalled": False,
        "criteria_changed": False,
    }
    return result


def validate_scorer(module, tasks):
    assert module.AnalysisAnswer.__pydantic_complete__
    cases = []
    for task in tasks:
        if task["kind"] != "analysis":
            continue
        callers = {
            module.location_key(c): {k: c[k] for k in ("path", "qualified_name", "start_line")}
            for c in task["gold_callers"]
        }
        answer = {"target": task["gold_target"], "callers": list(callers.values()), "limitations": "fixture"}
        record = {
            "answer_text": json.dumps(answer),
            "agent_completed": False,
            "passed": False,
            "source_unchanged": True,
            "tests_unchanged": True,
            "error_type": "PydanticUserError",
        }
        assert grade(module, task, record)["passed"]
        wrong_callers = copy.deepcopy(list(callers.values()))
        wrong_callers[0]["qualified_name"] += "_wrong"
        wrong = {**answer, "callers": wrong_callers}
        assert not grade(module, task, {**record, "answer_text": json.dumps(wrong)})["passed"]
        assert not grade(module, task, {**record, "answer_text": "No structured answer."})["passed"]
        assert not grade(module, task, {**record, "answer_text": json.dumps(answer) * 2})["passed"]
        cases.append(
            {
                "task": task["id"],
                "correct_passes": True,
                "wrong_name_rejected": True,
                "missing_answer_rejected": True,
                "ambiguous_answer_rejected": True,
            }
        )
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    plan = json.loads((output / "experiment-plan.json").read_text())
    reference = output / "reference/agent_worker.py"
    broken = reference_module(reference, registered=False)
    module = reference_module(reference, registered=True)
    assert TypeAdapter(broken.TransportOperation).json_schema() == TypeAdapter(module.TransportOperation).json_schema()
    cases = validate_scorer(module, plan["tasks"])
    correction = {
        "name": "reference-module-registration-1",
        "reference_worker_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "correction_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "unregistered_validator_complete": broken.AnalysisAnswer.__pydantic_complete__,
        "registered_validator_complete": module.AnalysisAnswer.__pydantic_complete__,
        "tool_schema_equal": True,
        "scope": "Every analysis answer; identical criteria; no model reruns; raw records retained.",
        "preflight_cases": cases,
    }
    if args.preflight_only:
        (output / "scorer-correction-preflight.json").write_text(json.dumps(correction, indent=2))
        print(json.dumps(correction, indent=2))
        return
    raw_paths = sorted((output / "runs").glob("*/result.json"))
    assert len(raw_paths) == plan["runs"]
    assert all("worker_exit" in json.loads(path.read_text()) for path in raw_paths)
    tasks = {task["id"]: task for task in plan["tasks"]}
    records = []
    changes = []
    for path in raw_paths:
        raw = json.loads(path.read_text())
        task = tasks[raw["task"]]
        corrected = grade(module, task, raw) if task["kind"] == "analysis" else raw
        folder = output / "corrected-runs" / raw["id"]
        folder.mkdir(parents=True)
        for artifact in path.parent.iterdir():
            if artifact.name != "result.json" and artifact.is_file():
                (folder / artifact.name).symlink_to(artifact)
        (folder / "result.json").write_text(json.dumps(corrected, ensure_ascii=False, indent=2))
        records.append(corrected)
        if task["kind"] == "analysis":
            changes.append(
                {
                    "id": raw["id"],
                    "raw_passed": raw["passed"],
                    "corrected_passed": corrected["passed"],
                    "raw_error": raw.get("error_type"),
                    "corrected_error": corrected.get("error_type"),
                    "raw_result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    correction["analysis_records"] = changes
    correction["analysis_count"] = len(changes)
    correction["repair_records_unchanged"] = True
    (output / "scorer-correction.json").write_text(json.dumps(correction, ensure_ascii=False, indent=2))
    (output / "corrected-agent-results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
    aggregate = (output / "aggregate_results.py").read_text()
    aggregate = aggregate.replace('(OUT / "runs")', '(OUT / "corrected-runs")')
    aggregate = aggregate.replace('"final-summary.json"', '"corrected-summary.json"')
    aggregate = aggregate.replace('"agent-runs.csv"', '"corrected-agent-runs.csv"')
    script = output / "aggregate-corrected.py"
    script.write_text(aggregate)
    exec(compile(aggregate, str(script), "exec"), {"__file__": str(script), "__name__": "__main__"})


if __name__ == "__main__":
    main()
