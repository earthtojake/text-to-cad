"""The analytics receiver takes every file kind the CAD apps send.

cadgen's analytics client names each file it counts by a kind (``FILE_KINDS``); the
docs site's receiver refuses a batch that names a kind outside its own closed list,
and a refused batch is dropped with every count in it. The two lists live in two
languages; this keeps them one list.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

REPO = Path(__file__).resolve().parents[3]
add_repo_path("packages/cadgen/src")

from cadgen.analytics import FILE_KINDS  # noqa: E402


def receiver_kinds() -> set[str]:
    text = (REPO / "apps/docs/src/lib/analytics/events.mjs").read_text(encoding="utf-8")
    match = re.search(r"const KINDS = new Set\(\[([^\]]*)\]\)", text)
    if match is None:
        raise AssertionError("apps/docs/src/lib/analytics/events.mjs has no `const KINDS = new Set([...])`")
    return set(re.findall(r"'([^']+)'", match.group(1)))


class AnalyticsKindsContractTest(unittest.TestCase):
    def test_the_receiver_takes_every_kind_the_client_sends(self) -> None:
        self.assertEqual(set(FILE_KINDS.values()), receiver_kinds())


if __name__ == "__main__":
    unittest.main()
