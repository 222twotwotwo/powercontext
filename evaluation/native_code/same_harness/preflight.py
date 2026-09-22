"""Check policy parity, real adapter behavior and unchanged task baselines."""

import argparse
import asyncio
import hashlib
import json
import subprocess
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Any

if __package__:
    from .adapter import NativeAdapter
    from .policy import KINDS, PolicyError, query_graph
    from .rescore import validate_scorer
    from .worker import load_worker
else:
    NativeAdapter = import_module("adapter").NativeAdapter
    _policy = import_module("policy")
    KINDS, PolicyError, query_graph = _policy.KINDS, _policy.PolicyError, _policy.query_graph
    validate_scorer = import_module("rescore").validate_scorer
    load_worker = import_module("worker").load_worker


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str))


class FixtureGraph:
    def __init__(self, fixture):
        self.fixture = fixture

    def node(self, identifier):
        return next((n for n in self.fixture["nodes"] if n["id"] == identifier), None)

    def by_name(self, name):
        return [n for n in self.fixture["nodes"] if n["name"] == name]

    def in_file(self, path):
        return [n for n in self.fixture["nodes"] if n["filePath"] == path]

    def edges(self, identifier, outgoing):
        return [e for e in self.fixture["edges"] if e["source" if outgoing else "target"] == identifier]

    def search(self, query, path, limit):
        return [
            n
            for n in self.fixture["nodes"]
            if query in n["name"]
            and n["kind"] in KINDS
            and n["language"] == "python"
            and (not path or n["filePath"] == path)
        ][:limit]


def policy_parity(output, configuration):
    folder = output / "preflight/policy"
    folder.mkdir(parents=True, exist_ok=True)
    nodes = []
    for index, (name, path) in enumerate(
        [
            ("root", "app.py"),
            ("left", "app.py"),
            ("right", "app.py"),
            ("test_join", "tests/test_app.py"),
            ("duplicate", "one.py"),
            ("duplicate", "two.py"),
        ]
    ):
        nodes.append(
            {
                "id": str(index),
                "name": name,
                "qualifiedName": name,
                "filePath": path,
                "language": "python",
                "kind": "function",
                "startLine": index + 1,
                "endLine": index + 2,
                "signature": "def " + name + "():",
            }
        )
    edges = [
        {"source": source, "target": target, "kind": "calls", "line": 20 + index, "provenance": "tree-sitter"}
        for index, (source, target) in enumerate(
            [
                ("1", "0"),
                ("2", "0"),
                ("3", "1"),
                ("3", "2"),
                ("0", "1"),
                ("4", "0"),
                ("missing", "0"),
            ]
        )
    ]
    fixture = {"nodes": nodes, "edges": edges}
    save(folder / "fixture.json", fixture)
    (folder / "fixture.cjs").write_text("""const fixture = require('./fixture.json');
const graph = {
 getNode: id => fixture.nodes.find(n => n.id === id),
 getNodesByName: name => fixture.nodes.filter(n => n.name === name),
 getNodesInFile: path => fixture.nodes.filter(n => n.filePath === path),
 getIncomingEdges: id => fixture.edges.filter(e => e.target === id),
 getOutgoingEdges: id => fixture.edges.filter(e => e.source === id),
 getStats: () => ({nodeCount: fixture.nodes.length}),
 searchNodes: (query, options) => fixture.nodes.filter(n => n.name.includes(query)
   && options.kinds.includes(n.kind) && options.languages.includes(n.language))
   .slice(0, options.limit).map(node => ({node})),
 close: () => {},
};
module.exports = {CodeGraph: {open: async () => graph}, setLogger: () => {}, silentLogger: {}};
""")
    target = {"path": "app.py", "qualified_name": "root", "start_line": 1, "limit": 20}
    operations = [
        ({"kind": "symbols", "query": "root", "limit": 20}, False),
        ({"kind": "symbols", "query": "root", "limit": 20}, True),
        ({"kind": "symbols", "query": "duplicate", "limit": 20}, True),
        ({"kind": "symbols", "query": "duplicate", "path": "two.py", "limit": 1}, False),
        ({**target, "kind": "callers"}, False),
        ({**target, "kind": "callers", "limit": 1}, False),
        ({**target, "kind": "callees"}, False),
        ({**target, "kind": "impact", "depth": 1}, False),
        ({**target, "kind": "impact", "depth": 3}, False),
        ({"kind": "affected_tests", "changed_paths": ["app.py"], "limit": 20}, False),
        ({"kind": "affected_tests", "changed_paths": ["missing.py"], "limit": 20}, False),
        ({**target, "kind": "callers", "start_line": 99}, False),
        ({"kind": "callers", "path": "one.py", "qualified_name": "duplicate", "start_line": 5, "limit": 20}, False),
    ]
    node = Path(configuration["engine"]).parent.parent / "node"
    javascript = output / "integration/src/powercontext/builtin/code/engine.cjs"
    results = []
    for operation, prepare in operations:
        payload = {"command": "query", "root": str(folder), "operation": operation, "prepare": prepare}
        raw = subprocess.check_output(
            [str(node), "--disable-warning=ExperimentalWarning", str(javascript), str(folder / "fixture.cjs")],
            input=json.dumps(payload),
            text=True,
        )
        expected = json.loads(raw)
        try:
            actual = {"result": query_graph(FixtureGraph(fixture), operation, prepare)}
        except PolicyError as error:
            actual = {"error": str(error)}
        results.append(
            {
                "operation": operation,
                "prepare": prepare,
                "equal": actual == expected,
                "javascript": expected,
                "python": actual,
            }
        )
    save(folder / "results.json", results)
    assert all(row["equal"] for row in results), "Shared selection policy differs from engine.cjs"
    return {"passed": True, "cases": len(results)}


async def check_adapters(output, worker, configuration):
    # This preflight runs against the frozen worktree5 API via PYTHONPATH.
    config: Any = import_module("powercontext.builtin.code.config")
    models: Any = import_module("powercontext.builtin.code.models")
    services: Any = import_module("powercontext.builtin.code.service")
    runtime_models: Any = import_module("powercontext.builtin.runtime.models")
    prepared: Any = import_module("powercontext.builtin.runtime.prepared_context")

    results = {}
    for arm in ("codegraph", "native"):
        service = services.CodeService(
            config.CodeConfig(
                enabled=True,
                repositories={"eval": output / "corpus"},
                cache_dir=output / f"preflight/cache-{arm}",
                provider=config.CodeGraphConfig(executable=configuration["engine"]),
            )
        )
        if arm == "native":
            service.adapter = NativeAdapter(service.config.provider, output)
        began = monotonic()
        indexed = await service.index("eval")
        result = {"index_seconds": monotonic() - began, "index": indexed.model_dump(mode="json"), "prepared": []}
        assert indexed.status == "ready"
        for task in worker.PLAN["tasks"]:
            began = monotonic()
            try:
                response = await service.prepare("eval", task["prompt"])
                built = prepared.PreparedContextBuilder().build_scopes_result(
                    request=runtime_models.PrepareContextRequest(
                        query=task["prompt"], include_code=True, max_bytes=8000
                    ),
                    current_scope_id="eval",
                    code_response=response,
                    code_omission="code_query_unfocused" if response is None else None,
                )
                text = built.context.content or ""
                assert len(text.encode()) <= 8000
                item = {
                    "task": task["id"],
                    "seconds": monotonic() - began,
                    "names": [i.location.qualified_name for i in built.code_items if i.location],
                    "bytes": len(text.encode()),
                    "response": response.model_dump(mode="json") if response else None,
                }
                (output / f"preflight/{arm}-{task['id']}-prepared.md").write_text(text)
            except Exception as error:
                item = {
                    "task": task["id"],
                    "seconds": monotonic() - began,
                    "error": getattr(error, "code", type(error).__name__),
                }
            result["prepared"].append(item)
        probe = await service.query(
            "eval",
            models.CodeQueryRequest.model_validate(
                {
                    "operation": {"kind": "symbols", "query": "fit_context_text_item", "limit": 20},
                }
            ),
        )
        assert any(item.location and item.location.qualified_name == "fit_context_text_item" for item in probe.items)
        result["known_symbol"] = probe.model_dump(mode="json")
        results[arm] = result
        save(output / "preflight/adapters.json", results)
    return results


async def check_tasks(output, worker):
    rows = []
    for task in worker.PLAN["tasks"]:
        if task["kind"] != "coding":
            continue
        root = Path(task["root"])
        folder = output / "preflight" / task["id"]
        folder.mkdir(parents=True, exist_ok=True)
        worker.git(root, "restore", "--source=" + task["head"], "--worktree", "--", "src")
        path = root / task["path"]
        original = path.read_text()
        assert original.count(task["before"]) == 1
        baseline = await worker.check(task, folder, "baseline")
        try:
            path.write_text(original.replace(task["before"], task["after"], 1))
            seeded = await worker.check(task, folder, "seeded")
        finally:
            path.write_text(original)
        rows.append({"task": task["id"], "baseline": baseline, "seeded": seeded})
        save(output / "preflight/tasks.json", rows)
        assert baseline["exit_code"] == 0 and seeded["exit_code"] != 0
    return [{"task": row["task"], "baseline_pass": True, "seeded_fail": True} for row in rows]


async def run(output):
    configuration = json.loads((output / "configuration.json").read_text())
    worker = load_worker(output, "off")
    scorer = validate_scorer(worker, worker.PLAN["tasks"])
    print(json.dumps({"scorer": scorer}), flush=True)
    policy = policy_parity(output, configuration)
    print(json.dumps({"policy_parity": policy}), flush=True)
    tasks = await check_tasks(output, worker)
    print(json.dumps({"tasks": tasks}), flush=True)
    adapters = await check_adapters(output, worker, configuration)
    for arm, result in adapters.items():
        print(
            json.dumps(
                {
                    "arm": arm,
                    "index_seconds": result["index_seconds"],
                    "prepared": [
                        {k: row.get(k) for k in ("task", "bytes", "names", "error")} for row in result["prepared"]
                    ],
                }
            ),
            flush=True,
        )
    with worker.server_settings_context(
        env_file=Path(configuration["env_file"]), data_dir=output / "provider-config"
    ) as settings:
        model = settings.inference.generation_model
        name = model if isinstance(model, str) else getattr(model, "model_name", None)
        assert name in {"qwen3.7-plus", "openai:qwen3.7-plus"}, "Configured model changed"
    save(
        output / "preflight.json",
        {
            "passed": True,
            "policy": policy,
            "scorer": scorer,
            "tasks": tasks,
            "model": name,
            "adapters_known_symbol_passed": ["codegraph", "native"],
            "reference_worker_sha256": hashlib.sha256((output / "reference/agent_worker.py").read_bytes()).hexdigest(),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args().output.resolve()))
