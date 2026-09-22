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
