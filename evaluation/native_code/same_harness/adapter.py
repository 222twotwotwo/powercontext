"""Inject only a native backend into the frozen worktree5 CodeService."""

from __future__ import annotations

import hashlib
import json
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Any

# These APIs belong to the frozen worktree5 integration, loaded via PYTHONPATH.
# They intentionally differ from the native package in the current checkout.
_adapter: Any = import_module("powercontext.builtin.code.adapter")
_errors: Any = import_module("powercontext.builtin.code.errors")
_process: Any = import_module("powercontext.builtin.code.process")
CodeGraphAdapter = _adapter.CodeGraphAdapter
EngineIdentity = _adapter.EngineIdentity
CodeUnavailableError = _errors.CodeUnavailableError
InvalidCodeRequestError = _errors.InvalidCodeRequestError
UnsupportedCodeCapabilityError = _errors.UnsupportedCodeCapabilityError
run_process = _process.run_process


class NativeAdapter(CodeGraphAdapter):
    """Retain the original build/query lifecycle, index copy and time budgets."""

    def __init__(self, config, experiment: Path):
        super().__init__(config)
        self.experiment = experiment
        self.backend = json.loads((experiment / "backend.json").read_text())

    def _identity(self, deadline):
        digest = hashlib.sha256()
        for name in self.backend["identity_files"]:
            path = Path(name)
            digest.update(name.encode() + b"\0")
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    if monotonic() >= deadline:
                        raise CodeUnavailableError("code_timeout")
                    digest.update(chunk)
        return EngineIdentity(
            node=Path(self.backend["python"]),
            module=self.experiment / "bridge" / "engine.py",
            version="powercontext-native-v1",
            digest=digest.hexdigest(),
        )

    async def _invoke(self, identity, payload, *, deadline):
        raw = await run_process(
            (str(identity.node), str(identity.module), "--deadline", str(deadline)),
            cwd=identity.module.parent,
            deadline=deadline,
            max_output_bytes=4 * 1024 * 1024,
            stdin=json.dumps(payload, ensure_ascii=False).encode(),
        )
        try:
            envelope = json.loads(raw)
        except ValueError:
            raise CodeUnavailableError("code_engine_output") from None
        error = envelope.get("error")
        if error == "invalid_code_target":
            raise InvalidCodeRequestError(error)
        if error == "unsupported_capability":
            raise UnsupportedCodeCapabilityError(error)
        if error is not None:
            raise CodeUnavailableError("code_timeout" if error == "code_timeout" else "code_engine_failed")
        if not isinstance(envelope.get("result"), dict):
            raise CodeUnavailableError("code_engine_output")
        return envelope["result"]
