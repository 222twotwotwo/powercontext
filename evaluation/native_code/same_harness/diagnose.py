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

"""Measure query stages after the formal cohort; never alter primary outcomes."""

import argparse
import asyncio
import json
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Any

if __package__:
    from .adapter import NativeAdapter
else:
    NativeAdapter = import_module("adapter").NativeAdapter

# Load the frozen integration's API, not this checkout's native service API.
adapter_module: Any = import_module("powercontext.builtin.code.adapter")
service_module: Any = import_module("powercontext.builtin.code.service")
config_module: Any = import_module("powercontext.builtin.code.config")
CodeConfig, CodeGraphConfig = config_module.CodeConfig, config_module.CodeGraphConfig
CodeService = service_module.CodeService


def timed(function, name, events):
    def call(*args, **kwargs):
        began = monotonic()
        event = {"stage": name}
        try:
            return function(*args, **kwargs)
        except Exception as error:
            event["error"] = getattr(error, "code", type(error).__name__)
            raise
        finally:
            event["seconds"] = round(monotonic() - began, 6)
            events.append(event)

    return call


def timed_async(function, name, events):
    async def call(*args, **kwargs):
        began = monotonic()
        event = {"stage": name}
        try:
            return await function(*args, **kwargs)
        except Exception as error:
            event["error"] = getattr(error, "code", type(error).__name__)
            raise
        finally:
            event["seconds"] = round(monotonic() - began, 6)
            events.append(event)

    return call


def run(output):
    assert "EXPERIMENT_COMPLETE" in (output / "controller.log").read_text()
    configuration = json.loads((output / "configuration.json").read_text())
    plan = json.loads((output / "experiment-plan.json").read_text())
    results = []
    for arm in ("codegraph", "native"):
        service = CodeService(
            CodeConfig(
                enabled=True,
                repositories={"eval": output / "corpus"},
                cache_dir=output / f"cache-{arm}-corpus",
                provider=CodeGraphConfig(executable=configuration["engine"]),
            )
        )
        if arm == "native":
            service.adapter = NativeAdapter(service.config.provider, output)
        for task in (task for task in plan["tasks"] if task["kind"] == "analysis"):
            events = []
            originals = []
            for target, name, asynchronous in (
                (adapter_module, "_copy_index", False),
                (service_module, "capture_repository", True),
                (service_module, "index_digest", False),
                (service.adapter, "_identity", False),
                (service.adapter, "_invoke", True),
            ):
                original = getattr(target, name)
                originals.append((target, name, original))
                wrapper = timed_async if asynchronous else timed
                setattr(target, name, wrapper(original, name, events))
            row = {"arm": arm, "task": task["id"], "query_seconds": 5}
            began = monotonic()
            try:
                # Each loop drains its executor before another query starts.
                response = asyncio.run(service.prepare("eval", task["prompt"]))
                row["response"] = response.model_dump(mode="json") if response else None
            except Exception as error:
                row["error"] = getattr(error, "code", type(error).__name__)
            finally:
                row["seconds"] = round(monotonic() - began, 6)
                for target, name, original in originals:
                    setattr(target, name, original)
            row["stages"] = events
            results.append(row)
            print(json.dumps({key: value for key, value in row.items() if key != "response"}), flush=True)
    report = {
        "scope": "Post-cohort default-budget diagnostics only; no model calls or formal score changes.",
        "stage_times_overlap": True,
        "runs": results,
    }
    (output / "query-diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output.resolve())


if __name__ == "__main__":
    main()
