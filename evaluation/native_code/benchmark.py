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

"""Measure real repository cold build, ten-file sync, and complete query latency."""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import time
from pathlib import Path

from evaluation.native_code.prepare import git
from powercontext.builtin.code import CodeConfig, CodeLimits, CodeQueryRequest, CodeRepositoryConfig, CodeService
from powercontext.builtin.code.capture import capture_repository


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    blobs, root = args.output / "capture", args.output / "repository"
    blobs.mkdir()
    root.mkdir()
    capture = capture_repository(
        CodeRepositoryConfig(root=args.repository, include_untracked=True, exclude=("reports/**", "presentations/**")),
        CodeLimits(),
        time.monotonic() + 120,
        content_dir=blobs,
    )
    for entry in capture.files:
        if entry.reason is not None or entry.sha256 is None:
            continue
        path = root / entry.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((blobs / entry.sha256).read_bytes())
    git(root, "init", "-q")
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Native Code Benchmark",
        "-c",
        "user.email=benchmark@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-qm",
        "Captured benchmark input",
    )
    service = CodeService(
        CodeConfig(
            enabled=True, cache_dir=args.output / "cache", repositories={"benchmark": CodeRepositoryConfig(root=root)}
        )
    )
    report = {
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "input_commit": capture.commit,
        "dirty": capture.dirty,
        "query_includes_freshness": True,
    }
    started = time.monotonic()
    report["cold_build"] = service.index("benchmark", full=True)
    report["cold_seconds"] = time.monotonic() - started
    changed = sorted((root / "src/powercontext").rglob("*.py"))[:10]
    for path in changed:
        path.write_bytes(path.read_bytes() + b"\n# Native code synchronization probe.\n")
    started = time.monotonic()
    report["sync"] = service.sync("benchmark")
    report["sync_seconds"] = time.monotonic() - started
    report["changed_files"] = [path.relative_to(root).as_posix() for path in changed]
    measurements = []
    for repetition in range(20):
        operation = "symbols" if repetition % 2 else "explore"
        query = ("prepare_context", "remember_memory", "SourceRef", "ScopeApplication")[repetition % 4]
        started = time.monotonic()
        result = service.query(
            "benchmark", CodeQueryRequest.model_validate({"operation": {"kind": operation, "query": query}})
        )
        measurements.append(
            {
                "operation": operation,
                "query": query,
                "seconds": time.monotonic() - started,
                "response_bytes": len(result.model_dump_json().encode()),
            }
        )
    durations = sorted(item["seconds"] for item in measurements)
    report.update(
        queries=measurements,
        query_p50=statistics.median(durations),
        query_p95=durations[18],
        parent_max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        largest_child_max_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        cache_bytes=sum(path.stat().st_size for path in (args.output / "cache").rglob("*") if path.is_file()),
    )
    (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {key: report[key] for key in ("cold_seconds", "sync_seconds", "query_p50", "query_p95", "cache_bytes")}
        )
    )


if __name__ == "__main__":
    main()
