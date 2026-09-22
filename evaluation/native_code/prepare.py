# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""Capture historical cases and verify hidden regressions before model evaluation."""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any

from evaluation.native_code.isolation import run_tests

CASES = Path(__file__).with_name("cases.json")


def git(repository: Path, *arguments: str) -> bytes:
    return subprocess.run(["git", "-C", str(repository), *arguments], check=True, capture_output=True).stdout


def snapshot(repository: Path, commit: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    raw = git(repository, "archive", "--format=tar", commit)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not member.isfile():
                continue
            if "rfcs" in path.parts or path.parts[0] in {"reports", "presentations"}:
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
            target.chmod(member.mode & 0o777)
    git(destination, "init", "-q")
    git(destination, "add", ".")
    git(
        destination,
        "-c",
        "user.name=Native Code Evaluation",
        "-c",
        "user.email=evaluation@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-q",
        "-m",
        "Captured evaluation input",
    )


def prepare_case(repository: Path, output: Path, case: dict[str, Any]) -> dict[str, Any]:
    directory = output / case["id"]
    directory.mkdir(parents=True, exist_ok=True)
    fix = git(repository, "rev-parse", case["fix"]).decode().strip() if "fix" in case else None
    base = git(repository, "rev-parse", fix + "^" if fix else case["base"]).decode().strip()
    result = {**case, "base": base, "fix": fix}
    if not (directory / "input").exists():
        snapshot(repository, base, directory / "input")
    if fix is not None:
        hidden = directory / "hidden"
        hidden.mkdir(exist_ok=True)
        for selector in case["tests"]:
            filename = selector.split("::", 1)[0]
            destination = hidden / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(git(repository, "show", f"{fix}:{filename}"))
        if not (directory / "reference").exists():
            snapshot(repository, fix, directory / "reference")
        if not (directory / "baseline-check").exists():
            shutil.copytree(directory / "input", directory / "baseline-check")
        for target in (directory / "baseline-check", directory / "reference"):
            shutil.copytree(hidden, target, dirs_exist_ok=True)
        before = run_tests(directory / "baseline-check", case["tests"], timeout=300)
        after = run_tests(directory / "reference", case["tests"], timeout=300)
        (directory / "baseline.log").write_text(before["output"])
        (directory / "reference.log").write_text(after["output"])
        result["validation"] = {
            "baseline": before["status"],
            "reference": after["status"],
            "eligible": before["returncode"] == 1 and after["returncode"] == 0,
        }
    (directory / "case.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({"id": case["id"], "validation": result.get("validation")}), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=("pilot", "formal", "all"), default="all")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    cases = json.loads(CASES.read_text())["cases"]
    selected = [case for case in cases if args.phase == "all" or case["phase"] == args.phase]
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda case: prepare_case(args.repository, args.output, case), selected))
    (args.output / f"{args.phase}-cases.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
