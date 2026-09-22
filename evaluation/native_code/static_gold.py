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

"""Source-defined static graph checks, independent of either engine's output."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from evaluation.native_code.prepare import git
from powercontext.builtin.code import CodeConfig, CodeQueryRequest, CodeQueryResult, CodeRepositoryConfig, CodeService

FILES = {
    "pkg/__init__.py": "from .base import leaf as public\n",
    "pkg/base.py": "def leaf():\n    return 1\n\ndef duplicate():\n    return 2\n",
    "pkg/alias.py": "from . import public as leaf_alias\n\ndef entry():\n    return leaf_alias()\n",
    "pkg/bridge.py": "from .alias import entry\n\ndef run():\n    return entry()\n",
    "pkg/cycle.py": "def left():\n    return right()\n\ndef right():\n    return left()\n",
    "pkg/diamond.py": "from .base import leaf\n\ndef west():\n    return leaf()\n\ndef east():\n    return leaf()\n\ndef top():\n    return west() + east()\n",
    "pkg/nested.py": "from .base import leaf\n\ndef outside():\n    def inside():\n        return leaf()\n    return inside()\n",
    "pkg/receiver.py": "class Known:\n    def method(self):\n        return 1\n\ndef invoke(target):\n    return target.method()\n",
    "pkg/shadow.py": "from .base import leaf\n\ndef call(leaf):\n    return leaf()\n",
    "pkg/other.py": "def leaf():\n    return -1\n",
    "tests/test_graph.py": "from pkg.bridge import run\n\ndef test_entry():\n    assert run()\n",
}
EXPECTED = {
    ("pkg/alias.py:entry", "pkg/base.py:leaf"),
    ("pkg/bridge.py:run", "pkg/alias.py:entry"),
    ("pkg/cycle.py:left", "pkg/cycle.py:right"),
    ("pkg/cycle.py:right", "pkg/cycle.py:left"),
    ("pkg/diamond.py:west", "pkg/base.py:leaf"),
    ("pkg/diamond.py:east", "pkg/base.py:leaf"),
    ("pkg/diamond.py:top", "pkg/diamond.py:west"),
    ("pkg/diamond.py:top", "pkg/diamond.py:east"),
    ("pkg/nested.py:outside", "pkg/nested.py:inside"),
    ("pkg/nested.py:inside", "pkg/base.py:leaf"),
    ("tests/test_graph.py:test_entry", "pkg/bridge.py:run"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output / "repository"
    root.mkdir(parents=True, exist_ok=False)
    for path, content in FILES.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git(root, "init", "-q")
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Static Evidence",
        "-c",
        "user.email=static@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-qm",
        "Source-defined gold fixture",
    )
    service = CodeService(
        CodeConfig(
            enabled=True, cache_dir=args.output / "cache", repositories={"gold": CodeRepositoryConfig(root=root)}
        )
    )
    service.index("gold")
    predicted, candidates, raw = set(), set(), []
    for path, content in FILES.items():
        for node in ast.walk(ast.parse(content)):
            if not isinstance(node, ast.FunctionDef):
                continue
            search = service.query(
                "gold",
                CodeQueryRequest.model_validate(
                    {
                        "operation": {"kind": "symbols", "query": node.name, "path_prefix": path},
                    }
                ),
            )
            assert isinstance(search, CodeQueryResult)
            symbol = next(item for item in search.items if item["name"] == node.name and item["kind"] != "file")
            result = service.query(
                "gold",
                CodeQueryRequest.model_validate(
                    {
                        "operation": {"kind": "callees", "symbol_id": symbol["id"], "depth": 1},
                        "expected_fingerprint": search.fingerprint,
                    }
                ),
            )
            assert isinstance(result, CodeQueryResult)
            raw.append(result.model_dump(mode="json"))
            for item in result.items:
                pair = (f"{path}:{node.name}", f"{item['path']}:{item['name']}")
                (predicted if item.get("resolution") == "resolved_static" else candidates).add(pair)
    status = service.status("gold")
    tests = service.query(
        "gold",
        CodeQueryRequest.model_validate(
            {
                "operation": {"kind": "affected_tests", "paths": ["pkg/base.py"], "limit": 20},
                "expected_fingerprint": status.fingerprint,
            }
        ),
    )
    assert isinstance(tests, CodeQueryResult)
    report = {
        "label_source": "explicit source-defined expectations; independent human audit pending",
        "expected": sorted(EXPECTED),
        "predicted_static": sorted(predicted),
        "candidates": sorted(candidates),
        "false_positive": sorted(predicted - EXPECTED),
        "missing": sorted(EXPECTED - predicted),
        "static_precision": len(predicted & EXPECTED) / len(predicted) if predicted else None,
        "static_recall": len(predicted & EXPECTED) / len(EXPECTED),
        "affected_tests_recall_at_20": float(
            any(item["path"] == "tests/test_graph.py" and item.get("witness_path") for item in tests.items)
        ),
        "affected_tests_count": len(tests.items),
        "raw": raw,
    }
    (args.output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "static_precision",
                    "static_recall",
                    "affected_tests_recall_at_20",
                    "false_positive",
                    "missing",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
