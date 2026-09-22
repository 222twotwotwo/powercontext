"""Audit completed same-harness records without changing their scores."""

import argparse
import collections
import hashlib
import json
from pathlib import Path


def audit_correction(output, records):
    correction_path = output / "scorer-correction.json"
    if not correction_path.exists():
        return None
    correction = json.loads(correction_path.read_text())
    corrected = {row["id"]: row for row in json.loads((output / "corrected-agent-results.json").read_text())}
    changes = {row["id"]: row for row in correction["analysis_records"]}
    analysis_ids = {row["id"] for row in records if row["kind"] == "analysis"}
    checks = {
        "all_runs_retained": set(corrected) == {row["id"] for row in records},
        "all_analysis_regraded": set(changes) == analysis_ids and len(changes) == 18,
        "same_tool_schema": correction["tool_schema_equal"] is True,
        "registered_validator_complete": correction["registered_validator_complete"] is True,
        "scorer_positive_negative_fixtures": len(correction["preflight_cases"]) == 3
        and all(all(value for key, value in case.items() if key != "task") for case in correction["preflight_cases"]),
        "raw_records_unchanged": all(
            hashlib.sha256((output / "runs" / name / "result.json").read_bytes()).hexdigest()
            == change["raw_result_sha256"]
            for name, change in changes.items()
        ),
        "repair_records_unchanged": all(row == corrected.get(row["id"]) for row in records if row["kind"] == "coding"),
        "only_analysis_grades_changed": all(
            {
                key: value
                for key, value in row.items()
                if key not in {"answer", "agent_completed", "error_type", "http_status", "score", "passed"}
            }
            == {
                key: value
                for key, value in corrected.get(row["id"], {}).items()
                if key
                not in {
                    "answer",
                    "agent_completed",
                    "error_type",
                    "http_status",
                    "score",
                    "passed",
                    "evaluation_correction",
                }
            }
            for row in records
            if row["kind"] == "analysis"
        ),
    }
    return {"checks": checks, "passed": all(checks.values())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    plan = json.loads((output / "experiment-plan.json").read_text())
    seal = json.loads((output / "formal-freeze.json").read_text())
    changed = [
        name
        for name, expected in seal["files"].items()
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected
    ]
    expected = {
        f"{task['id']}-{repeat}-{arm}"
        for task in plan["tasks"]
        for repeat in range(plan["repeats"])
        for arm in plan["arms"]
    }
    records = [json.loads(path.read_text()) for path in sorted((output / "runs").glob("*/result.json"))]
    identifiers = [row["id"] for row in records]
    mismatches = []
    unknown_usage = []
    for record in records:
        identifier = record["id"]
        if record.get("worker_exit") != 0:
            mismatches.append({"id": identifier, "reason": "worker_failure", "exit": record.get("worker_exit")})
        if record.get("implementation") != str(output / "integration/src/powercontext/__init__.py"):
            mismatches.append({"id": identifier, "reason": "wrong_integration"})
        if record.get("tests_unchanged") is not True:
            mismatches.append({"id": identifier, "reason": "test_integrity"})
        if record["kind"] == "analysis" and record.get("source_unchanged") is not True:
            mismatches.append({"id": identifier, "reason": "analysis_source_integrity"})
        if record.get("actual_models") != ["qwen3.7-plus"]:
            mismatches.append({"id": identifier, "reason": "model_identity", "models": record.get("actual_models")})
        if record.get("prepared", {}).get("bytes", 0) > 8000:
            mismatches.append({"id": identifier, "reason": "preparation_budget"})
        if record["arm"] != "off" and not record.get("index", {}).get("ok"):
            mismatches.append({"id": identifier, "reason": "index_unavailable"})
        if record.get("error_type") in {"ModelHTTPError", "APIConnectionError", "APITimeoutError", "ModelAPIError"}:
            unknown_usage.append(identifier)
        if not record.get("usage") or record.get("usage", {}).get("output_tokens", 0) <= 0:
            unknown_usage.append(identifier)
    manifest_digests = collections.defaultdict(set)
    native_counts = []
    for arm in ("codegraph", "native"):
        for manifest in output.glob(f"cache-{arm}-*/*/generation-*/manifest.json"):
            value = json.loads(manifest.read_text())
            manifest_digests[arm].add(value["engine_digest"])
            if arm == "native":
                native_counts.append(
                    {
                        "cache": manifest.parent.parent.parent.name,
                        "included": len(value["snapshot"]["files"]),
                        "indexed": value["indexed_files"],
                        "parse_failures": value["parse_failures"],
                    }
                )
    result = {
        "expected_runs": len(expected),
        "actual_runs": len(records),
        "missing_ids": sorted(expected - set(identifiers)),
        "extra_ids": sorted(set(identifiers) - expected),
        "unique_ids": len(set(identifiers)) == len(identifiers),
        "frozen_files_unchanged": not changed,
        "changed_frozen_files": changed,
        "record_mismatches": mismatches,
        "possibly_incomplete_usage": sorted(set(unknown_usage)),
        "engine_digests": {arm: sorted(values) for arm, values in manifest_digests.items()},
        "native_coverage": native_counts,
        "failure_policy": "All 36 scheduled attempts retained. No outcome-selected retry or exclusion.",
    }
    result["complete"] = set(identifiers) == expected and result["unique_ids"] and not changed
    result["integrity_passed"] = result["complete"] and not mismatches
    corrected = audit_correction(output, records)
    if corrected is not None:
        result["scorer_correction"] = corrected
        result["integrity_passed"] = result["integrity_passed"] and corrected["passed"]
    (output / "final-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["integrity_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
