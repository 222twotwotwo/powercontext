# Copyright (c) 2026 OceanBase.
# Licensed under the Apache License, Version 2.0.

"""Read explicit repository line citations without prescribing Markdown style."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import NamedTuple

_LINES = r"(?P<start>\d+)(?:[ \t]*[-–—:][ \t]*L?(?P<end>\d+))?(?P<open>\+)?"
_REFERENCE = re.compile(
    r"(?<![\w./-])(?P<path>(?:src|tests|integrations|openapi|scripts)/[\w./-]+)"
    r"[`*]*[ \t]*(?:[:#][ \t]*L?|\([ \t]*(?:lines?[ \t]+)?L?|,?[ \t]+(?:lines?[ \t]+|L))" + _LINES,
    re.IGNORECASE,
)
_CONTINUATION = re.compile(r"[ \t]*(?:,|;|and\b|、)[ \t]*(?:lines?[ \t]+)?L?" + _LINES, re.IGNORECASE)


class Citation(NamedTuple):
    path: str
    start: int
    end: int | None


def extract_references(answer: str) -> Iterator[Citation]:
    """Yield each explicit range; an open-ended range stays unknown, never shortened."""
    for match in _REFERENCE.finditer(answer):
        name = match["path"]
        while match:
            start = int(match["start"])
            end = None if match["open"] else int(match["end"] or match["start"])
            yield Citation(name, start, end)
            match = _CONTINUATION.match(answer, match.end())
