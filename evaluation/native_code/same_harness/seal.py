"""Seal the experiment after deterministic checks and before model calls."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if (output / "formal-freeze.json").exists() or (output / "runs").exists():
        raise RuntimeError("Cannot reseal a started or frozen cohort")
    assert json.loads((output / "preflight.json").read_text())["passed"]
    configuration = json.loads((output / "configuration.json").read_text())
    initial = json.loads((output / "freeze.json").read_text())
    files = [
        output / name
        for name in (
            "experiment-plan.json",
            "protocol.json",
            "configuration.json",
            "backend.json",
            "aggregate_results.py",
            "reference/agent_worker.py",
            "reference/experiment-plan.json",
            "preflight.json",
        )
    ]
    files.extend((output / "bridge").glob("*.py"))
    files.extend(Path(name) for name in json.loads((output / "backend.json").read_text())["identity_files"])
    files.extend(output / "integration" / name for name in initial["integration_files"])
    env_file = Path(configuration["env_file"])
    assert hashlib.sha256(env_file.read_bytes()).hexdigest() == initial["env_sha256"]
    files.append(env_file)
    record = {
        "sealed_at": datetime.now(UTC).isoformat(),
        "files": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        "initial_freeze_sha256": hashlib.sha256((output / "freeze.json").read_bytes()).hexdigest(),
        "formal_runs_at_seal": 0,
    }
    (output / "formal-freeze.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(json.dumps({"sealed_files": len(record["files"]), "sealed_at": record["sealed_at"]}))


if __name__ == "__main__":
    main()
