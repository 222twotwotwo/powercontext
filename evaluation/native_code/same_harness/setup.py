"""Freeze the existing six-task experiment without modifying its source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def git(root, *arguments):
    return subprocess.check_output(["git", "-C", str(root), *arguments], text=True).strip()


def clone(source, destination, head):
    subprocess.run(["git", "clone", "--shared", "--no-checkout", str(source), str(destination)], check=True)
    git(destination, "checkout", "--detach", head)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--native-source", type=Path, required=True)
    parser.add_argument("--agent-python", type=Path, required=True)
    args = parser.parse_args()
    reference, output = args.reference.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "experiment-plan.json").exists():
        raise RuntimeError("This experiment has already been initialized")
    original = json.loads((reference / "experiment-plan.json").read_text())
    manifest = json.loads((reference / "evaluation-scripts-manifest.json").read_text())
    for name, expected in manifest.items():
        if digest(reference / name) != expected:
            raise RuntimeError(f"Frozen reference script changed: {name}")
    head = original["corpus_head"]
    source = reference / "optimized"
    if git(source, "rev-parse", "HEAD") != head or git(source, "status", "--porcelain"):
        raise RuntimeError("The frozen optimized integration is not clean")
    archive = output / "reference"
    archive.mkdir()
    for name in (
        *manifest,
        "EXPERIMENT_PLAN.md",
        "snapshot.json",
        "final-summary.json",
        "agent-runs.csv",
        "aggregate_results.py",
        "repair_quality.py",
    ):
        shutil.copy2(reference / name, archive / name)
    bridge = output / "bridge"
    bridge.mkdir()
    for name in (
        "adapter.py",
        "engine.py",
        "policy.py",
        "worker.py",
        "run.py",
        "preflight.py",
        "rescore.py",
        "seal.py",
    ):
        shutil.copy2(Path(__file__).with_name(name), bridge / name)
    shutil.copy2(Path(__file__).with_name("protocol.json"), output / "protocol.json")
    aggregate = (reference / "aggregate_results.py").read_text()
    aggregate = aggregate.replace('"original"', '"codegraph"').replace('"optimized"', '"native"')
    aggregate = aggregate.replace("final-union-schema-with-object-normalization", "same-harness-native-engine-1")
    (output / "aggregate_results.py").write_text(aggregate)
    clone(source, output / "integration", head)
    plan = json.loads(json.dumps(original))
    plan["arms"] = ["off", "codegraph", "native"]
    for name in {Path(task["root"]).name for task in plan["tasks"]}:
        clone(source, output / name, head)
    for task in plan["tasks"]:
        task["root"] = str(output / Path(task["root"]).name)
    # Every task field, prompt, seed and oracle except its local root is retained.
    for old, new in zip(original["tasks"], plan["tasks"], strict=True):
        assert {k: v for k, v in old.items() if k != "root"} == {k: v for k, v in new.items() if k != "root"}
    save(output / "experiment-plan.json", plan)
    native_python = output / "native-venv" / "bin" / "python"
    site = output / "native-venv/lib/python3.14/site-packages"
    installed = site / "powercontext/builtin/code"
    native_hashes = {}
    for path in sorted((args.native_source / "src/powercontext/builtin/code").glob("*.py")):
        counterpart = installed / path.name
        if digest(path) != digest(counterpart):
            raise RuntimeError(f"Installed native engine differs: {path.name}")
        native_hashes[path.name] = digest(path)
    dependency_files = json.loads(
        subprocess.check_output(
            [
                str(native_python),
                "-c",
                "import tree_sitter,tree_sitter_python,json;from pathlib import Path;"
                "print(json.dumps([str(p) for m in (tree_sitter,tree_sitter_python) "
                "for p in Path(m.__file__).parent.rglob('*') if p.is_file() and p.suffix in {'.py','.so'}]))",
            ],
            text=True,
        )
    )
    identity_files = [
        str(native_python.resolve()),
        *(str(path) for path in sorted(installed.glob("*.py"))),
        *dependency_files,
        *(str(bridge / name) for name in ("adapter.py", "engine.py", "policy.py")),
    ]
    save(output / "backend.json", {"python": str(native_python), "identity_files": identity_files})
    configuration = {
        "reference": str(reference),
        "agent_python": str(args.agent_python),
        "native_python": str(native_python),
        "env_file": "/home/jingshun.tq/project/CE/teingi/worktree5/powercontext/.env",
        "engine": "/data/codex-tmp/pr1624-merge-92d25166/verified-engine/codegraph-linux-x64/bin/codegraph",
        "model": "qwen3.7-plus",
    }
    save(output / "configuration.json", configuration)
    files = git(output / "integration", "ls-files", "-z").split("\0")
    save(
        output / "freeze.json",
        {
            "reference_script_hashes": manifest,
            "reference_worker_byte_identical": digest(archive / "agent_worker.py") == manifest["agent_worker.py"],
            "integration_head": head,
            "integration_tree": git(source, "rev-parse", "HEAD^{tree}"),
            "integration_files": {name: digest(output / "integration" / name) for name in files if name},
            "native_modules": native_hashes,
            "native_dependency_files": {name: digest(Path(name)) for name in dependency_files},
            "env_sha256": digest(Path(configuration["env_file"])),
            "task_fields_equal_except_root": True,
        },
    )
    print(json.dumps({"output": str(output), "runs": plan["runs"], "native_modules": len(native_hashes)}))


if __name__ == "__main__":
    main()
