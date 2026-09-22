# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""Require actual, nonempty, source-consistent A/B delivery before model experiments."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from evaluation.native_code.engines import Engine
from evaluation.native_code.prepare import git
from powercontext.builtin.code.capture import digest_bytes, source_lines


def fixture(root: Path) -> None:
    root.mkdir()
    (root / "leaf.py").write_text("def leaf():\n    return 'fixed-fixture-evidence'\n")
    (root / "entry.py").write_text("from leaf import leaf\n\ndef entry():\n    return leaf()\n")
    (root / "test_entry.py").write_text("from entry import entry\n\ndef test_entry():\n    assert entry()\n")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.name=Adapter Preflight", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")


def checked_query(engine: Engine, operation: dict[str, Any], *, required: bool = True) -> dict[str, Any]:
    started = time.monotonic()
    result = engine.query({"operation": operation})
    if result.get("error"):
        raise RuntimeError(f"Preflight query failed: {result['error']}")
    items = result["items"]
    if required and not items:
        raise RuntimeError("Preflight expected nonempty delivered source evidence")
    for item in items:
        path = Path(item["path"])
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError("Delivered path must be repository-relative")
        content = (engine.root / path).read_bytes()
        lines = source_lines(content.decode())
        snippet = "".join(lines[item["start_line"] - 1 : item["end_line"]])
        if digest_bytes(content) != item["file_sha256"] or digest_bytes(snippet.encode()) != item["snippet_sha256"]:
            raise RuntimeError("Delivered evidence does not match the captured source")
        if snippet != item["content"]:
            raise RuntimeError("Delivered source range differs from its content")
    return {"operation": operation, "seconds": time.monotonic() - started, "result": result}


def run(args: argparse.Namespace) -> None:
    args.output.mkdir(parents=True, exist_ok=False)
    input_root = args.output / "input"
    if args.repository:
        shutil.copytree(args.repository, input_root)
    else:
        fixture(input_root)
    report = {"status": "running", "source": "historical" if args.repository else "fixture", "arms": {}}
    manifests = {}
    try:
        for arm in "AB":
            output = args.output / arm
            output.mkdir()
            root = output / "workspace"
            shutil.copytree(input_root, root)
            engine = Engine(arm, root, output, library=args.codegraph, node=args.node)
            try:
                manifests[arm] = engine.manifest
                records = []
                query = "prepare_context" if args.repository else "entry"
                records.append(checked_query(engine, {"kind": "symbols", "query": query}))
                records.append(checked_query(engine, {"kind": "explore", "query": query}))
                prefix = "src/powercontext/client" if args.repository else "entry.py"
                records.append(checked_query(engine, {"kind": "symbols", "query": query, "path_prefix": prefix}))
                if any(not item["path"].startswith(prefix) for item in records[-1]["result"]["items"]):
                    raise RuntimeError("Path-scoped search escaped its prefix")
                if not args.repository:
                    symbol = next(item for item in records[0]["result"]["items"] if item["name"] == "entry")
                    for kind in ("callers", "callees", "impact"):
                        records.append(checked_query(engine, {"kind": kind, "symbol_id": symbol["symbol_id"]}))
                report["arms"][arm] = records
            finally:
                engine.close()
        if manifests["A"] != manifests["B"]:
            raise RuntimeError("A and B did not capture identical inputs")
        report["status"] = "passed"
    finally:
        (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"status": report["status"], "queries": {arm: len(rows) for arm, rows in report["arms"].items()}}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codegraph", type=Path, required=True)
    parser.add_argument("--node", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
