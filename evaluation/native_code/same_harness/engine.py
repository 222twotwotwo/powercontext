"""Run the frozen native extractor/resolver/index under the worktree5 adapter."""

from __future__ import annotations

import argparse
import json
import sys
from importlib import import_module
from pathlib import Path

from powercontext.builtin.code.capture import check_deadline, digest_bytes, json_bytes, write_private
from powercontext.builtin.code.errors import CodeError
from powercontext.builtin.code.extract import extraction_key
from powercontext.builtin.code.process import extract_jobs
from powercontext.builtin.code.resolve import PythonResolver
from powercontext.builtin.code.store import create_graph, node_by_id, open_graph, search_nodes

if __package__:
    from .policy import KINDS, PolicyError, query_graph
else:
    _policy = import_module("policy")
    KINDS, PolicyError, query_graph = _policy.KINDS, _policy.PolicyError, _policy.query_graph


def build(root: Path, deadline: float):
    index = root / ".codegraph"
    index.mkdir(mode=0o700, exist_ok=True)
    for name in ("source", "facts"):
        (index / name).mkdir(mode=0o700)
    jobs = []
    for path in sorted(root.rglob("*.py")):
        check_deadline(deadline)
        if index in path.parents:
            continue
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        digest = digest_bytes(content)
        destination = index / "source" / digest
        if not destination.exists():
            write_private(destination, content)
        jobs.append(
            {
                "path": relative,
                "language": "python",
                "sha256": digest,
                "extraction_key": extraction_key(relative, digest, "python"),
            }
        )
    if jobs:
        extract_jobs(index, jobs, deadline, memory_bytes=1024**3, parse_seconds=5)
    facts = [json.loads((index / "facts" / f"{entry['extraction_key']}.json").read_bytes()) for entry in jobs]
    edges, diagnostics = PythonResolver(facts, ("src", "."), deadline).resolve()
    create_graph(index / "graph.sqlite", [node for fact in facts for node in fact["nodes"]], edges, deadline)
    result = {
        "indexed_files": len(facts),
        "parse_failures": sum(bool(fact["errors"]) for fact in facts),
        "unresolved_references": sum(map(len, diagnostics.values())),
        "files": [{"path": fact["path"], "errors": len(fact["errors"])} for fact in facts],
    }
    write_private(index / "build.json", json_bytes(result))
    # Retain native facts and content blobs as part of the indexed generation.
    # The shared service monitors all cache files while this build is running.
    return result


def graph_node(node):
    return {
        **node,
        "filePath": node["path"],
        "qualifiedName": node["qualified_name"],
        "startLine": node["start_line"],
        "endLine": node["end_line"],
    }


class NativeGraph:
    """Translate storage fields; native search supplies its original ranking."""

    def __init__(self, connection, deadline):
        self.connection = connection
        self.deadline = deadline

    def _nodes(self, clause, parameters):
        check_deadline(self.deadline)
        rows = self.connection.execute("SELECT payload FROM code_nodes WHERE " + clause, parameters)
        return [graph_node(json.loads(row[0])) for row in rows]

    def node(self, identifier):
        check_deadline(self.deadline)
        node = node_by_id(self.connection, identifier)
        return graph_node(node) if node else None

    def by_name(self, name):
        return self._nodes("name = ?", (name,))

    def in_file(self, path):
        return self._nodes("path = ? ORDER BY start_line, rowid", (path,))

    def edges(self, identifier, outgoing):
        check_deadline(self.deadline)
        field = "source_id" if outgoing else "target_id"
        rows = self.connection.execute(
            f"SELECT payload FROM code_edges WHERE {field} = ? ORDER BY rowid", (identifier,)
        )
        return [
            {
                **edge,
                "source": edge["source_id"],
                "target": edge["target_id"],
                "provenance": "tree-sitter" if edge["resolution"] == "resolved_static" else "heuristic",
            }
            for row in rows
            for edge in [json.loads(row[0])]
        ]

    def search(self, query, path, limit):
        check_deadline(self.deadline)
        count = self.connection.execute("SELECT COUNT(*) FROM code_nodes").fetchone()[0]
        # Match CodeGraph's definition-kind filter and exact-file restriction
        # without allowing file nodes to consume the requested result limit.
        nodes = search_nodes(self.connection, query, path or "", count)
        return [
            graph_node(node)
            for node in nodes
            if node["kind"] in KINDS and node["language"] == "python" and (not path or node["path"] == path)
        ][:limit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    payload = json.load(sys.stdin)
    root = Path(payload["root"])
    try:
        if payload["command"] == "build":
            result = build(root, args.deadline)
        else:
            with open_graph(root / ".codegraph" / "graph.sqlite", args.deadline) as connection:
                result = query_graph(NativeGraph(connection, args.deadline), payload["operation"], payload["prepare"])
        print(json.dumps({"result": result}, ensure_ascii=False))
    except (CodeError, PolicyError) as error:
        print(json.dumps({"error": error.code if isinstance(error, CodeError) else str(error)}))


if __name__ == "__main__":
    main()
