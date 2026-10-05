"""cadgen starts its own processes as ``python -P -m cadgen…``.

``python -m`` puts the folder a process runs in first on its import path. cadgen's
processes run in the system temp folder (the daemon, its workers, the store's gc, the
artifact producer) or in a project (a transient build, the Viewer): whatever other
programs, or on a shared ``/tmp`` other users, leave there must never stand in for
cadgen's own modules (STORE.md §9). ``-P`` keeps that folder off the path; PYTHONPATH and
the installation still apply. ``test_daemon_pool`` runs a worker beside a shadow package;
this pins every other launch to the same flag.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src" / "cadgen"
LAUNCH = re.compile(r'"-m",\s*f?"cadgen')


class InternalLaunches(unittest.TestCase):
    def test_every_cadgen_launch_keeps_its_working_folder_off_the_import_path(self) -> None:
        launches, unflagged = 0, []
        for path in sorted(SOURCE.rglob("*.py")):
            if "_runtime" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for match in LAUNCH.finditer(text):
                launches += 1
                if not text[:match.start()].rstrip().endswith('"-P",'):
                    unflagged.append(f"{path.relative_to(SOURCE)}:{text.count(chr(10), 0, match.start()) + 1}")
        self.assertGreater(launches, 0, "found no launch to check: the pattern no longer matches cadgen's source")
        self.assertEqual([], unflagged, "a cadgen launch without -P")


if __name__ == "__main__":
    unittest.main()
