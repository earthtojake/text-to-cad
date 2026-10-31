"""The packages start their own processes as ``python -P -m cad…``.

``python -m`` puts the folder a process runs in first on its import path. Their
processes (the engine's build workers, its document readers and render processes, the
telemetry sender) run in a project or in the system temp folder: whatever other
programs, or on a shared ``/tmp`` other users, leave there must never stand in for
their own modules. ``-P`` keeps that folder off the path; PYTHONPATH and
the installation still apply. ``test_daemon_pool`` runs a worker beside a shadow package;
this pins every other launch to the same flag.
"""

from __future__ import annotations

import re
import unittest
from tests.python.support.paths import SOURCES

LAUNCH = re.compile(r'"-m",\s*f?"(?:cad|cad_server|cad_mcp|cadgen)\b')


class InternalLaunches(unittest.TestCase):
    def test_every_own_launch_keeps_its_working_folder_off_the_import_path(self) -> None:
        launches, unflagged = 0, []
        for source in SOURCES:
            for path in sorted(source.rglob("*.py")):
                if "_runtime" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8")
                for match in LAUNCH.finditer(text):
                    launches += 1
                    if not text[:match.start()].rstrip().endswith('"-P",'):
                        unflagged.append(f"{path.relative_to(source)}:{text.count(chr(10), 0, match.start()) + 1}")
        self.assertGreater(launches, 0, "found no launch to check: the pattern no longer matches the packages' source")
        self.assertEqual([], unflagged, "a launch of the packages' own without -P")


if __name__ == "__main__":
    unittest.main()
