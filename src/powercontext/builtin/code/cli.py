# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

"""Local maintenance and JSON queries for explicitly configured repositories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from powercontext.builtin.code.errors import CodeError
from powercontext.builtin.code.models import CodeQueryRequest
from powercontext.builtin.code.service import CodeService
from powercontext.server.configuration import ServerConfigurationError, server_settings_context

app = typer.Typer(name="code", help="Index and query a configured local Git worktree.", no_args_is_help=True)
ScopeOption = Annotated[str, typer.Option("--scope", help="Scope with an operator-configured repository binding.")]
EnvironmentOption = Annotated[Path | None, typer.Option("--env-file", help="Authoritative Server environment file.")]


def _read_request(path: Path | None) -> CodeQueryRequest:
    if path is None or path.stat().st_size > 64 * 1024:
        raise CodeError("invalid_code_request", status=422)
    return CodeQueryRequest.model_validate_json(path.read_bytes())


def _run(operation: str, scope_id: str, env_file: Path | None, request_file: Path | None = None) -> None:
    try:
        with server_settings_context(env_file=env_file) as settings:
            service = CodeService(settings.code)
            if operation in {"index", "sync"}:
                result = service.index(scope_id, full=operation == "index")
            elif operation == "clear":
                result = service.clear(scope_id)
            elif operation == "status":
                result = service.status(scope_id).model_dump(mode="json", by_alias=True)
            else:
                request = _read_request(request_file)
                result = service.query(scope_id, request).model_dump(mode="json", by_alias=True)
    except CodeError as error:
        typer.echo(json.dumps({"error": {"code": error.code}}, ensure_ascii=False), err=True)
        raise typer.Exit(1) from None
    except (OSError, ValidationError, ServerConfigurationError):
        typer.echo('{"error":{"code":"invalid_code_configuration_or_request"}}', err=True)
        raise typer.Exit(2) from None
    typer.echo(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


@app.command()
def index(scope: ScopeOption, env_file: EnvironmentOption = None) -> None:
    """Build a complete index and atomically publish it."""
    _run("index", scope, env_file)


@app.command()
def sync(scope: ScopeOption, env_file: EnvironmentOption = None) -> None:
    """Reuse unchanged syntax facts and rebuild all relationships."""
    _run("sync", scope, env_file)


@app.command()
def status(scope: ScopeOption, env_file: EnvironmentOption = None) -> None:
    """Report index availability and verify current worktree freshness."""
    _run("status", scope, env_file)


@app.command()
def query(
    scope: ScopeOption,
    request_file: Annotated[Path, typer.Option("--request-file", help="Strict JSON code query request.")],
    env_file: EnvironmentOption = None,
) -> None:
    """Run a bounded query without implicitly building an index."""
    _run("query", scope, env_file, request_file)


@app.command()
def clear(scope: ScopeOption, env_file: EnvironmentOption = None) -> None:
    """Unpublish the configured cache and collect generations without active readers."""
    _run("clear", scope, env_file)
