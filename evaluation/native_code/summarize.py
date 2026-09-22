# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""Paired task-cluster estimates, with failures, retries and missing usage retained."""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from evaluation.native_code.run import dump


def mean(values: Sequence[float]) -> float | None:
    return statistics.mean(values) if values else None


def interval(values: list[float]) -> dict[str, Any]:
    """Each value is one independent task's paired mean, never one repetition."""
    if not values:
        return {"tasks": 0, "estimate": None, "ci95": None}
    rng = random.Random(20260921)
    sampled = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(10000))
    return {"tasks": len(values), "estimate": mean(values), "ci95": [sampled[249], sampled[9749]]}


def usage_total(record: dict[str, Any], field: str) -> int | None:
    usage = record.get("usage")
    if not usage or any(item is None for item in usage):
        return None
    values = []
    for item in usage:
        if field == "uncached_prompt_tokens":
            prompt = item.get("prompt_tokens")
            cached = (item.get("prompt_tokens_details") or {}).get("cached_tokens")
            value = None if prompt is None or cached is None else prompt - cached
        elif field == "cached_prompt_tokens":
            value = (item.get("prompt_tokens_details") or {}).get("cached_tokens")
        else:
            value = item.get(field)
        if value is None:
            return None
        values.append(value)
    return sum(values)


def cost(records: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"runs": len(records), "statuses": dict(Counter(item["status"] for item in records))}
    for field in ("task_seconds", "wall_seconds", "cold_seconds", "tool_calls", "query_calls"):
        if field in {"tool_calls", "query_calls"}:
            values = [
                len(item.get("calls", []))
                if field == "tool_calls"
                else sum(call["tool"] == "query_code" for call in item.get("calls", []))
                for item in records
            ]
        else:
            values = [item[field] for item in records if field in item]
        result[field] = {"mean": mean(values), "observed_runs": len(values), "unknown_runs": len(records) - len(values)}
    for field in ("prompt_tokens", "cached_prompt_tokens", "uncached_prompt_tokens", "completion_tokens"):
        totals = [usage_total(item, field) for item in records]
        values = [item for item in totals if item is not None]
        result[field] = {
            "observed_sum": sum(values),
            "mean": mean(values),
            "observed_runs": len(values),
            "unknown_runs": len(totals) - len(values),
        }
    query_records = [item for item in records if any(call["tool"] == "query_code" for call in item.get("calls", []))]
    result["query_adoption_runs"] = len(query_records)
    result["query_successful_calls"] = sum(
        call["tool"] == "query_code" and not call["error"] for item in records for call in item.get("calls", [])
    )
    return result


def paired_estimates(records: list[dict[str, Any]], field: str, comparator: str) -> dict[str, Any]:
    pairs: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for item in records:
        pairs[item["id"], item["repeat"]][item["arm"]] = item
    tasks: dict[str, list[float]] = defaultdict(list)
    for (task, _), arms in pairs.items():
        if not {"B", comparator}.issubset(arms):
            continue
        left, right = arms["B"], arms[comparator]
        if field == "uncached_prompt_tokens":
            a, b = usage_total(left, field), usage_total(right, field)
        else:
            a, b = left.get(field), right.get(field)
        if a is None or b is None:
            continue
        difference = float(a) - float(b)
        if field in {"task_seconds", "uncached_prompt_tokens"}:
            if b <= 0:
                continue
            difference /= b
        tasks[task].append(difference)
    result = interval([statistics.mean(values) for values in tasks.values()])
    result["paired_repetitions"] = sum(map(len, tasks.values()))
    result["task_differences"] = {key: mean(values) for key, values in tasks.items()}
    result["unit"] = "relative_change" if field in {"task_seconds", "uncached_prompt_tokens"} else "absolute_difference"
    return result


def summarize(args: argparse.Namespace) -> None:
    selected = json.loads((args.experiment / "results.json").read_text())
    records = [item for item in selected if item["valid"]]
    all_attempts = [json.loads(path.read_text()) for path in sorted(args.experiment.glob("*/result.json"))]
    review_map: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    if args.review is not None:
        mapping = json.loads((args.review / "mapping.json").read_text())
        for review in json.loads((args.review / "results.json").read_text()):
            item = mapping[review["label"]]
            review_map[item["id"], item["arm"], item["repeat"], item["attempt"]] = review
    for record in records:
        if record["kind"] == "repair":
            record["success"] = (record.get("grade") or {}).get("status") == "passed"
            record["quality_score"] = float(record["success"])
        else:
            review = review_map.get((record["id"], record["arm"], record["repeat"], record["attempt"]), {})
            record["success"] = review.get("adequate")
            record["quality_score"] = review.get("score")
    triples: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        triples[record["id"], record["repeat"]].append(record)
    mutual = [
        record
        for triple in triples.values()
        if len(triple) == 3 and all(item["success"] is True for item in triple)
        for record in triple
    ]
    report: dict[str, Any] = {
        "valid_runs": len(records),
        "all_attempts": len(all_attempts),
        "invalid_selected_runs": len(selected) - len(records),
        "independent_human_audit": False,
        "currency_cost": "unknown: no verified provider prices; missing usage stays unknown",
        "bootstrap": "10000 resamples of independent tasks, seed 20260921; repetitions averaged within task",
        "arms": {},
        "per_task": {},
        "comparisons": {},
    }
    for arm in "ABC":
        report["arms"][arm] = {
            "valid_attempts": cost([item for item in records if item["arm"] == arm]),
            "all_attempts": cost([item for item in all_attempts if item["arm"] == arm]),
            "mutually_successful_triples": cost([item for item in mutual if item["arm"] == arm]),
        }
    for task in sorted({item["id"] for item in records}):
        task_records = [item for item in records if item["id"] == task]
        report["per_task"][task] = {
            arm: {
                "results": [
                    {key: item.get(key) for key in ("repeat", "attempt", "status", "success", "quality_score")}
                    for item in task_records
                    if item["arm"] == arm
                ],
                "cost": cost([item for item in task_records if item["arm"] == arm]),
            }
            for arm in "ABC"
        }
    for kind in ("repair", "understanding", "impact"):
        subset = [item for item in records if item["kind"] == kind]
        for comparator in ("A", "C"):
            key = f"{kind}:B-{comparator}"
            comparison: dict[str, Any] = {
                field: paired_estimates(subset, field, comparator)
                for field in ("success", "quality_score", "task_seconds", "uncached_prompt_tokens")
            }
            if kind == "repair":
                bound = comparison["success"]["ci95"]
                comparison["noninferiority"] = (
                    "interval_rule_met_only" if bound and bound[0] > -0.05 else "insufficient_evidence"
                )
                comparison["degenerate_interval"] = bool(bound and bound[0] == bound[1])
            report["comparisons"][key] = comparison
    report["mutual_success_comparisons"] = {
        f"B-{comparator}:{field}": paired_estimates(mutual, field, comparator)
        for comparator in ("A", "C")
        for field in ("task_seconds", "uncached_prompt_tokens")
    }
    dump(args.output, report)
    print(json.dumps({key: report[key] for key in ("valid_runs", "all_attempts", "invalid_selected_runs")}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    summarize(parser.parse_args())


if __name__ == "__main__":
    main()
