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

"""Run repository tests with only their workspace and the Python runtime mounted."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_tests(workspace: Path, selectors: list[str], *, timeout: int = 180) -> dict[str, Any]:
    if not selectors or any(
        not item.startswith("tests/") or ".." in Path(item.split("::")[0]).parts for item in selectors
    ):
        raise ValueError("test selectors must remain below tests/")
    return run_python(
        workspace,
        [
            "-m",
            "pytest",
            "-p",
            "anyio",
            "-o",
            "addopts=",
            "-o",
            "cache_dir=/tmp/pytest-cache",
            "--basetemp",
            "/tmp/pytest",
            "-q",
            "--tb=short",
            "--disable-warnings",
            *selectors,
        ],
        timeout=timeout,
    )


def run_python(workspace: Path, arguments: list[str], *, timeout: int = 180) -> dict[str, Any]:
    """Internal sandbox executor; callers expose only tests and the fixed API generator."""
    executable = shutil.which("bwrap")
    if executable is None:
        raise RuntimeError("bubblewrap is required; unrestricted execution is not a fallback")
    command = [executable, "--unshare-all", "--die-with-parent", "--new-session"]
    interpreter = Path(sys.executable)
    linked_prefix = interpreter.readlink().parent.parent if interpreter.is_symlink() else Path(sys.base_prefix)
    runtime_paths = dict.fromkeys(("/usr", "/lib", "/lib64", sys.prefix, sys.base_prefix, str(linked_prefix)))
    for directory in runtime_paths:
        if Path(directory).exists():
            command += ["--ro-bind", directory, directory]
    if Path("/etc/ld.so.cache").exists():
        command += ["--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"]
    command += [
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/agent-home",
        "--bind",
        str(workspace.resolve()),
        "/workspace",
        "--tmpfs",
        "/workspace/.git",
        "--setenv",
        "HOME",
        "/agent-home",
        "--setenv",
        "TMPDIR",
        "/tmp",
        "--setenv",
        "PATH",
        sys.prefix + "/bin:/usr/bin:/bin",
        "--setenv",
        "PYTHONPATH",
        "/workspace/src:/workspace",
        "--setenv",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        "1",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--chdir",
        "/workspace",
        sys.executable,
        *arguments,
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
        )
    except subprocess.TimeoutExpired as error:
        output = error.stdout or b""
        return {
            "status": "timeout",
            "returncode": None,
            "output": output.decode(errors="replace") if isinstance(output, bytes) else output,
        }
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "output": result.stdout,
    }
