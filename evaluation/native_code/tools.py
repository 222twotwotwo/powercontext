# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""Identical bounded file tools; no shell, network, history, or sub-agent tools."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path, PurePosixPath
from typing import Any

from evaluation.native_code.engines import Engine
from evaluation.native_code.isolation import run_python, run_tests
from powercontext.builtin.code.capture import digest_bytes, source_lines


def _tool(name: str, description: str, properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(required),
                "additionalProperties": False,
            },
        },
    }


def tool_schema(arm: str, *, repair: bool) -> list[dict[str, Any]]:
    string = {"type": "string"}
    tools = [
        _tool(
            "list_files", "List repository-relative files matching a glob, capped at 100 paths.", {"pattern": string}
        ),
        _tool(
            "read_file",
            "Read source lines with exact file hash and line numbers; maximum 200 lines and 16000 bytes.",
            {"path": string, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
            ("path",),
        ),
        _tool(
            "grep",
            "Find a literal string in repository files; return at most 40 matching source lines.",
            {"query": string, "pattern": string},
            ("query",),
        ),
    ]
    if repair:
        tools += [
            _tool(
                "write_file",
                "Replace one repository source or test file with UTF-8 content.",
                {"path": string, "content": string},
                ("path", "content"),
            ),
            _tool(
                "edit_file",
                "Replace one exact, unique literal substring in a source or test file.",
                {"path": string, "old_text": string, "new_text": string},
                ("path", "old_text", "new_text"),
            ),
            _tool(
                "generate_api",
                "Run the repository's fixed scripts/generate_api.py in isolation after editing canonical OpenAPI.",
                {},
            ),
            _tool(
                "run_tests",
                "Run specified public pytest test paths in an isolated, network-free environment.",
                {"selectors": {"type": "array", "items": string, "maxItems": 5}},
                ("selectors",),
            ),
        ]
    if arm in {"A", "B"}:
        tools.append(
            _tool(
                "query_code",
                'Search symbols, explore code or follow static relationships. Source remains authoritative; static relationships can be incomplete. operation must be a JSON object, e.g. {"kind":"symbols","query":"prepare_context"}. Reuse returned symbol_id for callers/callees/impact and pass the returned fingerprint as expected_fingerprint.',
                {
                    "operation": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string", "enum": ["symbols", "explore", "callers", "callees", "impact"]},
                            "query": string,
                            "symbol_id": string,
                            "path_prefix": string,
                            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                            "depth": {"type": "integer", "minimum": 1, "maximum": 3},
                        },
                        "required": ["kind"],
                        "additionalProperties": False,
                    },
                    "expected_fingerprint": string,
                },
                ("operation",),
            )
        )
    return tools


class WorkspaceTools:
    def __init__(self, root: Path, engine: Engine, *, repair: bool) -> None:
        self.root, self.engine, self.repair = root.resolve(), engine, repair
        self.modified: set[str] = set()

    def path(self, name: str) -> Path:
        pure = PurePosixPath(name)
        if (
            not name
            or pure.is_absolute()
            or any(part in {"..", ".git", ".codegraph", ".venv"} or part.startswith(".env") for part in pure.parts)
        ):
            raise ValueError("path is outside the allowed repository source surface")
        result = self.root.joinpath(*pure.parts)
        if not result.resolve().is_relative_to(self.root) or any(
            part.is_symlink() for part in (result, *result.parents)
        ):
            raise ValueError("symlinks and paths outside the workspace are unavailable")
        return result

    def files(self, pattern: str = "*") -> list[str]:
        result = []
        for path in self.root.rglob("*"):
            name = path.relative_to(self.root).as_posix()
            if not path.is_file() or not fnmatch.fnmatchcase(name, pattern):
                continue
            try:
                self.path(name)
            except ValueError:
                continue
            if "__pycache__" in path.parts or path.stat().st_size > 2 * 1024 * 1024:
                continue
            result.append(name)
        return sorted(result)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "query_code":
            return self.engine.query(arguments)
        if name == "list_files":
            paths = self.files(arguments.get("pattern", "*"))
            return {"paths": paths[:100], "partial": len(paths) > 100}
        if name == "read_file":
            path = self.path(arguments["path"])
            raw = path.read_bytes()
            lines = source_lines(raw.decode())
            start = max(1, arguments.get("start_line", 1))
            end = min(arguments.get("end_line", start + 199), start + 199, len(lines))
            return {
                "path": arguments["path"],
                "file_sha256": digest_bytes(raw),
                "start_line": start,
                "end_line": end,
                "content": "".join(lines[start - 1 : end]),
            }
        if name == "grep":
            query = arguments["query"]
            if not query or len(query) > 512:
                raise ValueError("query must contain 1-512 literal characters")
            matches = []
            for path in self.files(arguments.get("pattern", "*")):
                try:
                    lines = source_lines(self.path(path).read_text())
                except UnicodeError:
                    continue
                for number, line in enumerate(lines, 1):
                    if query in line:
                        matches.append({"path": path, "line": number, "text": line[:400]})
                        if len(matches) >= 40:
                            return {"matches": matches, "partial": True}
            return {"matches": matches, "partial": False}
        if name == "write_file" and self.repair:
            path = self.path(arguments["path"])
            if path.suffix not in {".py", ".yaml", ".yml", ".toml", ".json", ".md"}:
                raise ValueError("unsupported source file type")
            content = arguments["content"].encode()
            if len(content) > 512 * 1024:
                raise ValueError("file exceeds write budget")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.modified.add(arguments["path"])
            return {"path": arguments["path"], "bytes_written": len(content)}
        if name == "run_tests" and self.repair:
            selectors = arguments["selectors"]
            if not 1 <= len(selectors) <= 5:
                raise ValueError("provide 1-5 public test selectors")
            for selector in selectors:
                self.path(selector.split("::", 1)[0])
            return run_tests(self.root, selectors, timeout=90)
        if name == "edit_file" and self.repair:
            path = self.path(arguments["path"])
            content = path.read_text()
            old = arguments["old_text"]
            if not old or content.count(old) != 1:
                raise ValueError("old_text must match exactly once")
            return self.call(
                "write_file", {"path": arguments["path"], "content": content.replace(old, arguments["new_text"], 1)}
            )
        if name == "generate_api" and self.repair:
            return run_python(self.root, ["scripts/generate_api.py"], timeout=90)
        raise ValueError("tool is not available")


def encode_result(value: dict[str, Any], maximum: int = 16000) -> str:
    """Bound every tool's full JSON output without emitting invalid JSON fragments."""
    while True:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) <= maximum:
            return encoded
        shortened = False
        for key in ("content", "output"):
            if isinstance(value.get(key), str) and value[key]:
                lines = source_lines(value[key])
                value[key] = "".join(lines[:-1]) if len(lines) > 1 else ""
                if key == "content" and "start_line" in value:
                    value["end_line"] = value["start_line"] + max(0, len(lines) - 2)
                shortened = True
                break
        if not shortened:
            for key in ("matches", "paths", "items"):
                if value.get(key):
                    value[key].pop()
                    shortened = True
                    break
        value["partial"] = True
        if not shortened:
            return '{"error":"output_budget_exceeded"}'
