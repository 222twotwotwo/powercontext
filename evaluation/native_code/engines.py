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

"""Common capture, provenance renderer and freshness checks for real A/B engines."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from pathlib import Path
from typing import Any

from powercontext.builtin.code import CodeConfig, CodeLimits, CodeQueryRequest, CodeRepositoryConfig, CodeService
from powercontext.builtin.code.capture import capture_repository, digest_bytes, json_bytes, source_lines

MAX_BYTES = 16000
EXCLUDE = ("docs/**", "evaluation/**", "benchmark/**", "presentations/**", "reports/**")


class CodeGraphBridge:
    def __init__(self, library: Path, node: Path, output: Path) -> None:
        self.output = output
        self.sequence = 0
        self.log = (output / "codegraph.stderr.log").open("w")
        environment = {
            "PATH": str(node.parent) + ":/usr/bin:/bin",
            "HOME": str(output / "agent-home"),
            "TMPDIR": str(output),
            "CODEGRAPH_PARSE_WORKERS": "2",
        }
        self.process = subprocess.Popen(
            [str(node), str(Path(__file__).with_name("codegraph_runner.cjs")), str(library)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            env=environment,
        )
        self.pending = b""

    def call(self, request: dict[str, Any], *, timeout: float) -> dict[str, Any] | list[dict[str, Any]]:
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json_bytes(request) + b"\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b"\n" not in self.pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    self.close()
                    raise TimeoutError("CodeGraph deadline exceeded")
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise RuntimeError("CodeGraph exited without a response")
                self.pending += chunk
                if len(self.pending) > 64 * 1024 * 1024:
                    raise RuntimeError("CodeGraph raw response limit exceeded")
        line, self.pending = self.pending.split(b"\n", 1)
        self.sequence += 1
        (self.output / f"codegraph-wire-{self.sequence:04d}.json").write_bytes(line)
        result = json.loads(line)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["result"]

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.log.close()


class Engine:
    """Each instance owns one run's independent worktree capture and real index."""

    def __init__(self, arm: str, root: Path, output: Path, *, library: Path, node: Path) -> None:
        self.arm, self.root, self.output = arm, root, output
        self.policy = CodeRepositoryConfig(root=root, include_untracked=True, exclude=EXCLUDE)
        self.limits = CodeLimits()
        self.bridge = CodeGraphBridge(library, node, output) if arm == "A" else None
        self.service = CodeService(
            CodeConfig(enabled=True, cache_dir=output / "native-cache", repositories={"evaluation": self.policy})
        )
        self.fingerprint = ""
        self.manifest: dict[str, dict[str, Any]] = {}
        self.native_fingerprint = ""
        self.events: list[dict[str, Any]] = []
        self.count = 0
        try:
            self.refresh()
        except BaseException:
            if self.bridge is not None:
                self.bridge.close()
            raise

    def capture(self) -> dict[str, dict[str, Any]]:
        captured = capture_repository(self.policy, self.limits, time.monotonic() + 30)
        return {
            entry.path: {"sha256": entry.sha256, "size": entry.size}
            for entry in captured.files
            if entry.reason is None
            and (entry.path.endswith(".py") or Path(entry.path).name.lower().startswith("readme"))
        }

    def refresh(self) -> None:
        started = time.monotonic()
        manifest = self.capture()
        freshness_seconds = time.monotonic() - started
        if manifest == self.manifest and self.fingerprint:
            self.events.append({"event": "freshness", "seconds": freshness_seconds})
            return
        self.manifest = manifest
        self.fingerprint = digest_bytes(json_bytes(manifest))
        (self.output / f"manifest-{self.fingerprint}.json").write_bytes(json_bytes(manifest))
        indexed = time.monotonic()
        if self.arm == "A":
            assert self.bridge is not None
            raw = self.bridge.call({"action": "index", "root": str(self.root), "files": list(manifest)}, timeout=600)
        elif self.arm == "B":
            # Keep the native capture scope identical to the common manifest. Explicitly
            # exclude other tracked text files instead of silently indexing extra inputs.
            candidates = capture_repository(self.policy, self.limits, time.monotonic() + 30)
            exclusions = tuple(entry.path for entry in candidates.files if entry.path not in manifest)
            native_policy = self.policy.model_copy(update={"exclude": (*EXCLUDE, *exclusions)})
            self.service = CodeService(
                self.service.config.model_copy(update={"repositories": {"evaluation": native_policy}})
            )
            raw = self.service.sync("evaluation")
            self.native_fingerprint = raw["fingerprint"]
        else:
            raw = {"index": "ordinary_file_tools_only"}
        self.events.append(
            {
                "event": "index" if not self.events else "sync",
                "fingerprint": self.fingerprint,
                "freshness_seconds": freshness_seconds,
                "engine_seconds": time.monotonic() - indexed,
                "raw": raw,
            }
        )
        if self.capture() != manifest:
            raise RuntimeError("worktree changed while indexing")

    def query(self, request: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        self.refresh()
        expected = request.get("expected_fingerprint")
        if expected and expected != self.fingerprint:
            return {"error": "code_changed", "fingerprint": self.fingerprint}
        operation = request["operation"]
        deadline = started + 5
        if self.arm == "A":
            assert self.bridge is not None
            raw = self.bridge.call({"operation": operation}, timeout=max(0.001, deadline - time.monotonic()))
            nodes, edges = self._codegraph(raw)
        elif self.arm == "B":
            native = {"operation": operation, "max_bytes": 32768}
            if operation["kind"] in {"callers", "callees", "impact"}:
                native["expected_fingerprint"] = self.native_fingerprint
            response = self.service.query("evaluation", CodeQueryRequest.model_validate(native))
            raw = response.model_dump(mode="json")
            nodes, edges = raw["items"], []
        else:
            raise ValueError("graph tool is not exposed in baseline C")
        self.count += 1
        (self.output / f"raw-{self.count:04d}.json").write_bytes(json_bytes(raw))
        items = []
        for item in nodes:
            normalized = self._render(item, edges, operation.get("path_prefix", ""))
            if normalized is not None:
                items.append(normalized)
            if len(items) >= operation.get("limit", 20):
                break
        result = {
            "fingerprint": self.fingerprint,
            "items": items,
            "partial": False,
            "limitations": ["Static evidence only; verify source before edits or tests."],
        }
        while len(json_bytes(result)) > MAX_BYTES and result["items"]:
            result["items"].pop()
            result["partial"] = True
        if self.capture() != self.manifest:
            return {"error": "code_changed"}
        elapsed = time.monotonic() - started
        self.events.append(
            {"event": "query", "seconds": elapsed, "operation": operation, "raw_file": f"raw-{self.count:04d}.json"}
        )
        if elapsed > 5:
            return {"error": "query_timeout"}
        return result

    @staticmethod
    def _codegraph(raw: dict[str, Any] | list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if isinstance(raw, list):
            return [item.get("node", item) for item in raw], [item["edge"] for item in raw if "edge" in item]
        return raw.get("nodes", []), raw.get("edges", [])

    def _render(self, node: dict[str, Any], edges: list[dict[str, Any]], prefix: str) -> dict[str, Any] | None:
        path = node.get("path", node.get("filePath"))
        if isinstance(path, str) and Path(path).is_absolute():
            try:
                path = Path(path).relative_to(self.root).as_posix()
            except ValueError:
                return None
        if path not in self.manifest or (prefix and path != prefix and not path.startswith(prefix + "/")):
            return None
        start, end = node.get("start_line", node.get("startLine")), node.get("end_line", node.get("endLine"))
        if not isinstance(start, int) or not isinstance(end, int) or start < 1:
            return None
        content = (self.root / path).read_bytes()
        if digest_bytes(content) != self.manifest[path]["sha256"]:
            raise RuntimeError("code_changed")
        lines = source_lines(content.decode())
        selected = []
        for line in lines[start - 1 : min(end, start + 199)]:
            if sum(len(part.encode()) for part in selected) + len(line.encode()) > 2000:
                break
            selected.append(line)
        excerpt = "".join(selected)
        evidence_edges = node.get("witness_path") or [
            edge for edge in edges if node["id"] in {edge.get("source"), edge.get("target")}
        ]
        return {
            "symbol_id": node["id"],
            "kind": node["kind"],
            "name": node["name"],
            "path": path,
            "start_line": start,
            "end_line": start + len(selected) - 1 if selected else end,
            "file_sha256": self.manifest[path]["sha256"],
            "snippet_sha256": digest_bytes(excerpt.encode()),
            "content": excerpt,
            "relationships": evidence_edges,
            "resolution": node.get("resolution", "unspecified"),
        }

    def close(self) -> None:
        (self.output / "engine-events.json").write_bytes(json_bytes(self.events))
        if self.bridge is not None:
            self.bridge.close()
