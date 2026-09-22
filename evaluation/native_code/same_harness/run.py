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

"""Run all 36 same-harness conditions serially, retaining every failure."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def verify_freeze(output):
    frozen = json.loads((output / "formal-freeze.json").read_text())
    for name, expected in frozen["files"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Frozen experiment input changed: {name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    plan = json.loads((output / "experiment-plan.json").read_text())
    configuration = json.loads((output / "configuration.json").read_text())
    preflight = json.loads((output / "preflight.json").read_text())
    assert preflight["passed"]
    verify_freeze(output)
    schedule = []
    for repeat in range(plan["repeats"]):
        for index, task in enumerate(plan["tasks"]):
            arms = plan["arms"]
            shift = (index + repeat) % 3
            schedule.extend((task, arm, repeat) for arm in arms[shift:] + arms[:shift])
    (output / "schedule.json").write_text(
        json.dumps([{"task": task["id"], "arm": arm, "repeat": repeat} for task, arm, repeat in schedule], indent=2)
    )
    results = []
    for task, arm, repeat in schedule:
        verify_freeze(output)
        identifier = f"{task['id']}-{repeat}-{arm}"
        path = output / "runs" / identifier / "result.json"
        if path.exists():
            existing = json.loads(path.read_text())
            if "worker_exit" in existing:
                results.append(existing)
                continue
            raise RuntimeError(f"Unfinished attempt must be preserved and audited before resuming: {identifier}")
        environment = {k: v for k, v in os.environ.items() if not k.startswith("POWERCONTEXT_")}
        environment.update(PYTHONPATH=str(output / "integration/src"), TMPDIR=str(output))
        print(json.dumps({"event": "start", "id": identifier, "time": time.time()}), flush=True)
        with (output / f"{identifier}.log").open("w") as log:
            process = subprocess.Popen(
                [
                    configuration["agent_python"],
                    str(output / "bridge/worker.py"),
                    "--output",
                    str(output),
                    "--task",
                    task["id"],
                    "--arm",
                    arm,
                    "--repeat",
                    str(repeat),
                ],
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                exit_code = process.wait(timeout=1000)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                exit_code = 124
        result = (
            json.loads(path.read_text())
            if path.exists()
            else {
                "id": identifier,
                "task": task["id"],
                "kind": task["kind"],
                "arm": arm,
                "repeat": repeat,
            }
        )
        result["worker_exit"] = exit_code
        if "passed" not in result:
            result.update(passed=False, infrastructure_failure=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        results.append(result)
        (output / "agent-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(
            json.dumps(
                {
                    key: result.get(key)
                    for key in ("id", "passed", "worker_exit", "agent_seconds", "tools", "actual_models", "error_type")
                }
            ),
            flush=True,
        )
    print("EXPERIMENT_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
