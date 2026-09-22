"""Run the byte-identical reference worker with one injected engine adapter."""

import argparse
import asyncio
import importlib.util
import json
import sys
from importlib import import_module
from pathlib import Path
from typing import Any

if __package__:
    from .adapter import NativeAdapter
else:
    NativeAdapter = import_module("adapter").NativeAdapter


def load_worker(output, arm):
    specification = importlib.util.spec_from_file_location("reference_worker", output / "reference/agent_worker.py")
    if specification is None or specification.loader is None:
        raise ImportError("Cannot load the frozen reference worker")
    worker: Any = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = worker
    specification.loader.exec_module(worker)
    worker.OUT = output
    worker.PLAN = json.loads((output / "experiment-plan.json").read_text())
    configuration = json.loads((output / "configuration.json").read_text())
    worker.ENGINE = configuration["engine"]
    original_service = worker.CodeService

    def make_service(config):
        service = original_service(config)
        if arm == "native":
            service.adapter = NativeAdapter(config.provider, output)
        return service

    worker.CodeService = make_service
    return worker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--arm", choices=("off", "codegraph", "native"), required=True)
    parser.add_argument("--repeat", type=int, required=True)
    args = parser.parse_args()
    worker = load_worker(args.output, args.arm)
    task = next(task for task in worker.PLAN["tasks"] if task["id"] == args.task)
    configuration = json.loads((args.output / "configuration.json").read_text())
    with worker.server_settings_context(
        env_file=Path(configuration["env_file"]), data_dir=args.output / "provider-config"
    ) as settings:
        asyncio.run(worker.run(task, args.arm, args.repeat, settings.inference.generation_model))


if __name__ == "__main__":
    main()
