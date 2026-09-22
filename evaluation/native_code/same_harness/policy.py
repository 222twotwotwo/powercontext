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

"""Python translation of the frozen engine.cjs selection and traversal policy.

The graph supplies extraction, resolution and search ranking. This module keeps
the original preparation limits, ambiguity guard and output shape unchanged.
"""

from collections import deque

KINDS = {"function", "method", "class", "variable", "constant", "property"}


class PolicyError(Exception):
    pass


def location(node):
    return {
        "path": node["filePath"],
        "qualified_name": node["qualifiedName"].replace("::", "."),
        "start_line": node["startLine"],
        "end_line": node["endLine"],
    }


def definition(node):
    return {
        "kind": "definition",
        "path": node["filePath"],
        "location": location(node),
        "signature": node.get("signature", "")[:2048] or None,
    }


def ambiguous(graph, node):
    return (
        sum(other["language"] == "python" and other["kind"] == node["kind"] for other in graph.by_name(node["name"]))
        > 1
    )


def target(graph, operation):
    nodes = [
        node
        for node in graph.in_file(operation["path"])
        if node["qualifiedName"].replace("::", ".") == operation["qualified_name"]
        and node["startLine"] == operation["start_line"]
    ]
    if len(nodes) != 1:
        raise PolicyError("invalid_code_target")
    return nodes[0]


def relationship(edge, source, destination):
    provenance = edge.get("provenance")
    return {
        "kind": "calls",
        "method": provenance if provenance in {"tree-sitter", "scip", "heuristic"} else "unknown",
        "source": location(source),
        "target": location(destination),
        "call_line": edge.get("line") or None,
    }


def relations(graph, node, direction, limit):
    if ambiguous(graph, node):
        raise PolicyError("unsupported_capability")
    items, omitted = [], 0
    for examined, edge in enumerate(graph.edges(node["id"], direction == "callees"), 1):
        if examined > 1000:
            return {"items": items, "omitted": omitted, "truncated": True}
        if edge["kind"] != "calls":
            continue
        source, destination = graph.node(edge["source"]), graph.node(edge["target"])
        if not source or not destination or ambiguous(graph, source) or ambiguous(graph, destination):
            omitted += 1
            continue
        other = destination if direction == "callees" else source
        if other["language"] != "python":
            omitted += 1
            continue
        items.append(
            {
                **definition(other),
                "kind": "relationship",
                "relationships": [relationship(edge, source, destination)],
            }
        )
        if len(items) >= limit:
            break
    return {"items": items, "omitted": omitted, "truncated": len(items) >= limit}


def is_test(node):
    filename = node["filePath"].split("/")[-1]
    return (
        node["name"].startswith("test_")
        and node["kind"] in {"function", "method"}
        and (filename.startswith("test_") or filename.endswith("_test.py"))
    )


def traverse(graph, starts, depth, limit, tests_only):
    seen = set()
    selected = set() if tests_only else {node["id"] for node in starts}
    pending = deque()
    omitted = 0
    for node in starts:
        if len(seen) >= 500:
            break
        if ambiguous(graph, node):
            omitted += 1
            continue
        if node["id"] not in seen:
            seen.add(node["id"])
            pending.append((node, []))
    items, examined = [], 0
    truncated = len(starts) > 500
    while pending:
        node, witness = pending.popleft()
        if len(witness) >= depth:
            continue
        for edge in graph.edges(node["id"], False):
            examined += 1
            if examined > 1000 or len(seen) >= 500:
                return {"items": items, "omitted": omitted, "truncated": True}
            if edge["kind"] != "calls":
                continue
            caller = graph.node(edge["source"])
            if not caller or caller["language"] != "python" or ambiguous(graph, caller):
                omitted += 1
                continue
            path = [*witness, relationship(edge, caller, node)]
            if caller["id"] not in seen:
                seen.add(caller["id"])
                pending.append((caller, path))
                if len(path) >= depth and any(e["kind"] == "calls" for e in graph.edges(caller["id"], False)):
                    truncated = True
            if caller["id"] not in selected and (not tests_only or is_test(caller)):
                selected.add(caller["id"])
                items.append(
                    {
                        **definition(caller),
                        "kind": "test" if tests_only else "relationship",
                        "relationships": path,
                    }
                )
                if len(items) >= limit:
                    return {"items": items, "omitted": omitted, "truncated": True}
    return {"items": items, "omitted": omitted, "truncated": truncated}


def query_graph(graph, operation, prepare=False):
    kind = operation["kind"]
    limit = operation["limit"]
    if kind == "symbols":
        count = 16 if prepare else limit
        nodes = graph.search(operation["query"], operation.get("path"), count)
        items, omitted = [definition(node) for node in nodes], 0
        if prepare:
            for node in nodes[:4]:
                if ambiguous(graph, node):
                    omitted += 1
                    continue
                expanded = relations(graph, node, "callers", 4)
                items.extend(expanded["items"])
                omitted += expanded["omitted"]
            items = items[:16]
        return {"items": items, "omitted": omitted, "truncated": len(nodes) >= count}
    if kind in {"callers", "callees"}:
        return relations(graph, target(graph, operation), kind, limit)
    if kind == "impact":
        node = target(graph, operation)
        if ambiguous(graph, node):
            raise PolicyError("unsupported_capability")
        return traverse(graph, [node], operation["depth"], limit, False)
    if kind == "affected_tests":
        starts = []
        for path in operation["changed_paths"]:
            nodes = [n for n in graph.in_file(path) if n["language"] == "python" and n["kind"] in KINDS]
            if not nodes:
                raise PolicyError("invalid_code_target")
            starts.extend(nodes)
        return traverse(graph, starts, 5, limit, True)
    raise PolicyError("unsupported_capability")
