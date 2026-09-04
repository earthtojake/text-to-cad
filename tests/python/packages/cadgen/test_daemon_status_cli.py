"""`cadgen daemon status` renders the pool's lifetime job COUNT, not the job ledger.

The status payload carries two things spelled alike: ``jobs`` is the ledger
(every job's state and phase -- a list, the CAD Viewer's progress feed) and
``jobsServed`` is how many jobs the pool has run. The human rendering once read
the former and printed ``totals [] jobs``.
"""

from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.cli import daemon_status  # noqa: E402


class StatusRendering(unittest.TestCase):
    def test_totals_line_counts_jobs_served(self) -> None:
        text = daemon_status._render({
            "pid": 4242,
            "startedAt": 0,
            "socket": "/tmp/cadgen.sock",
            "version": "0.5.0",
            "token": "abc",
            "workers": [{"pid": 7, "model": "/m/a.py", "busy": False, "extra": False, "jobs": 3}],
            "spares": 2,
            "jobsServed": 3,
            "imports": 4,
            "concurrent": 0,
            "recycles": 0,
            "crashes": 0,
            "jobs": [{"model": "/m/a.py", "state": "done"}],
        })
        self.assertIn("totals   3 jobs, 4 imports", text)
        self.assertNotIn("[", text.split("totals")[1])


if __name__ == "__main__":
    unittest.main()
