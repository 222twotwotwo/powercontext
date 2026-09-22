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

"""Protect source-grounded evaluation from treating citation style as missing evidence."""

import pytest

from evaluation.native_code.review import evidence


@pytest.mark.parametrize(
    "citation",
    [
        "src/sample.py:2-3",
        "src/sample.py#L2-L3",
        "src/sample.py (L2-L3)",
        "**`src/sample.py` lines 2-3:**",
        "**File:** `src/sample.py`, lines 2–3",  # noqa: RUF001 - Preserve the observed citation format.
        "| `src/sample.py` L2-3 | relevant implementation |",
        "`src/sample.py` (lines 2—3)",
    ],
)
def test_equivalent_citation_styles_deliver_the_same_historical_source(tmp_path, citation):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/sample.py").write_text("first\nsecond\nthird\nfourth\n")
    references, truncated = evidence(tmp_path, citation)
    assert not truncated
    assert len(references) == 1
    assert references[0]["reference"] == "src/sample.py:2-3"
    assert [line for line in references[0]["source"].splitlines() if line] == ["2: second", "3: third"]
    assert "sha256" in references[0]


def test_citation_lists_keep_separate_ranges_and_open_ranges_stay_unknown(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/sample.py").write_text("first\nsecond\nthird\nfourth\n")
    references, _ = evidence(tmp_path, "`src/sample.py` lines 1, 3–4; L2, 4+")  # noqa: RUF001
    assert [r["reference"] for r in references] == [
        "src/sample.py:1-1",
        "src/sample.py:3-4",
        "src/sample.py:2-2",
        "src/sample.py:4+",
    ]
    assert references[-1]["error"] == "open_ended_line_range"
    assert "source" not in references[-1]


def test_invalid_citations_cannot_gain_source_through_format_normalization(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/sample.py").write_text("first\nsecond\n")
    references, _ = evidence(tmp_path, "`src/sample.py`, lines 9-10; `src/../outside.py` lines 1-2")
    assert [r["error"] for r in references] == ["invalid_line_range", "outside_source"]
    assert all("source" not in r for r in references)
