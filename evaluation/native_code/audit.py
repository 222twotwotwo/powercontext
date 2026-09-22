# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Supplementary execution diagnostics; does not change frozen primary scores."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.native_code.citations import extract_references
from evaluation.native_code.run import dump
from evaluation.native_code.tools import tool_schema


def usage(record: dict[str, Any]) -> dict[str, Any]:
    """An unreturned provider request has unknown usage, even after earlier success."""
    responses = record.get("usage", [])
    unreturned = record["status"] in {"infrastructure_error", "model_protocol_error"}
    result: dict[str, Any] = {"returned_responses": len(responses), "unreturned_request": unreturned}
    for field in ("prompt_tokens", "cached_prompt_tokens", "uncached_prompt_tokens", "completion_tokens"):
        known = []
        unknown = 0
        for response in responses:
            if response is None:
                value = None
            elif field in {"cached_prompt_tokens", "uncached_prompt_tokens"}:
                cached = (response.get("prompt_tokens_details") or {}).get("cached_tokens")
                prompt = response.get("prompt_tokens")
                value = (
                    cached
                    if field == "cached_prompt_tokens"
                    else (prompt - cached if prompt is not None and cached is not None else None)
                )
            else:
                value = response.get(field)
            if value is None:
                unknown += 1
            else:
                known.append(value)
        result[field] = {
            "observed_in_returned_responses": sum(known),
            "responses_with_missing_field": unknown,
            "total": None if unreturned or unknown else sum(known),
        }
    return result


def query_delivery(directory: Path, answer: str) -> dict[str, int]:
    path = directory / "conversation.json"
    if not path.exists():
        return {"responses": 0, "nonempty_responses": 0, "items": 0, "cited_range_overlaps": 0}
    messages = json.loads(path.read_text())
    names: dict[str, str] = {}
    counts = Counter(responses=0, nonempty_responses=0, items=0, cited_range_overlaps=0)
    references = [(name, start, end) for name, start, end in extract_references(answer) if end is not None]
    for message in messages:
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or []:
                names[call["id"]] = call.get("function", {}).get("name", "")
        if message.get("role") != "tool" or names.get(message.get("tool_call_id", "")) != "query_code":
            continue
        counts["responses"] += 1
        try:
            content = json.loads(message.get("content", ""))
        except (ValueError, TypeError):
            continue
        items = content.get("items", []) if isinstance(content, dict) else []
        if not isinstance(items, list):
            continue
        counts["nonempty_responses"] += bool(items)
        counts["items"] += len(items)
        for item in items:
            start, end = item.get("start_line"), item.get("end_line")
            if not isinstance(start, int) or not isinstance(end, int):
                continue
            counts["cited_range_overlaps"] += any(
                path == item.get("path") and left <= end and right >= start for path, left, right in references
            )
    return dict(counts)


def key(record: dict[str, Any]) -> tuple[str, int, int, str]:
    return record["id"], record["repeat"], record["attempt"], record["arm"]


def audit(experiment: Path, output: Path) -> None:
    selected = json.loads((experiment / "results.json").read_text())
    selected_keys = {key(record) for record in selected if record["valid"]}
    records: list[dict[str, Any]] = []
    for path in sorted(experiment.glob("*/result.json")):
        record = json.loads(path.read_text())
        available = {item["function"]["name"] for item in tool_schema(record["arm"], repair=record["kind"] == "repair")}
        calls = record.get("calls", [])
        entry: dict[str, Any] = {
            **{name: record[name] for name in ("id", "kind", "repeat", "attempt", "arm", "status")},
            "selected_valid_run": key(record) in selected_keys,
            "grade": record.get("grade"),
            "modified_paths": record.get("modified_paths"),
            "unknown_tool_calls": dict(Counter(call["tool"] for call in calls if call["tool"] not in available)),
            "tool_error_types": dict(Counter(call["error"] for call in calls if call.get("error"))),
            "query_available": record["arm"] in {"A", "B"},
            "query_calls": sum(call["tool"] == "query_code" for call in calls),
            "query_successful_calls": sum(call["tool"] == "query_code" and not call.get("error") for call in calls),
            "query_delivery": query_delivery(path.parent, record.get("answer") or ""),
            "usage": usage(record),
        }
        records.append(entry)
    arms = {}
    for arm in "ABC":
        attempts = [record for record in records if record["arm"] == arm]
        valid = [record for record in attempts if record["selected_valid_run"]]
        repairs = [record for record in valid if record["kind"] == "repair"]
        complete_totals = {}
        for field in ("prompt_tokens", "cached_prompt_tokens", "uncached_prompt_tokens", "completion_tokens"):
            totals = [record["usage"][field]["total"] for record in attempts]
            complete_totals[field] = {
                "observed_in_returned_responses": sum(
                    record["usage"][field]["observed_in_returned_responses"] for record in attempts
                ),
                "incomplete_attempts": sum(value is None for value in totals),
                "all_attempts_total": None if any(value is None for value in totals) else sum(totals),
            }
        arms[arm] = {
            "all_attempts": len(attempts),
            "selected_valid_runs": len(valid),
            "repair_runs": len(repairs),
            "repair_no_modified_files": sum(record["modified_paths"] == [] for record in repairs),
            "repair_modified_paths_unknown": sum(record["modified_paths"] is None for record in repairs),
            "runs_with_unknown_tool_calls": sum(bool(record["unknown_tool_calls"]) for record in valid),
            "query_available": arm in {"A", "B"},
            "query_requested_runs": sum(record["query_calls"] > 0 for record in valid),
            "query_nonempty_runs": sum(record["query_delivery"]["nonempty_responses"] > 0 for record in valid),
            "query_cited_range_overlap_runs": sum(
                record["query_delivery"]["cited_range_overlaps"] > 0 for record in valid
            ),
            "usage_all_attempts": complete_totals,
        }
    dump(
        output,
        {
            "purpose": "Supplementary execution and usage completeness audit; frozen primary scores remain unchanged.",
            "limitations": [
                "Tool errors can coexist with other blockers; counts do not establish the cause of a failed repair.",
                "Citation overlap records shared source ranges, not correctness or causal attribution to the graph.",
                "Unreturned provider requests have unknown usage; observed returned-response sums are lower bounds.",
            ],
            "arms": arms,
            "runs": records,
        },
    )
    print(json.dumps({"audited_attempts": len(records), "selected_valid_runs": len(selected_keys)}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit(args.experiment, args.output)


if __name__ == "__main__":
    main()
