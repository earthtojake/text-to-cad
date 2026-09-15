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

    def test_the_busy_count_qualifies_the_bound_count(self) -> None:
        # `(N busy)` sits inside `M bound`, so it counts busy BOUND workers. Counting
        # busy across the whole pool printed "5 bound (5 busy)" over rows showing three
        # idle and two busy, because a worker can be busy with no model bound.
        text = daemon_status._render({
            "pid": 4242,
            "startedAt": 0,
            "socket": "/tmp/cadgen.sock",
            "version": "0.5.0",
            "token": "abc",
            "workers": [
                {"pid": 1, "model": "/m/a.py", "busy": True, "extra": False, "jobs": 1},
                {"pid": 2, "model": "/m/b.py", "busy": True, "extra": False, "jobs": 1},
                {"pid": 3, "model": "/m/c.py", "busy": False, "extra": False, "jobs": 1},
                {"pid": 4, "model": "/m/d.py", "busy": False, "extra": False, "jobs": 1},
                {"pid": 5, "model": "/m/e.py", "busy": False, "extra": False, "jobs": 1},
                {"pid": 6, "model": "", "busy": True, "extra": False, "jobs": 1},
                {"pid": 7, "model": "", "busy": False, "extra": False, "jobs": 0},
                {"pid": 8, "model": "", "busy": False, "extra": False, "jobs": 0},
            ],
            "spares": 2,
            "jobsServed": 6,
            "imports": 8,
            "concurrent": 0,
            "recycles": 0,
            "crashes": 0,
        })
        self.assertIn("workers  5 bound (2 busy), 2 spare, 1 unbound busy", text)
        self.assertEqual(2, text.count("  busy  "), "two bound rows, and only two, say busy")
        self.assertEqual(3, text.count("  idle  "))

    def test_an_all_bound_pool_says_nothing_about_unbound_workers(self) -> None:
        text = daemon_status._render({
            "pid": 1,
            "startedAt": 0,
            "socket": "/tmp/cadgen.sock",
            "workers": [{"pid": 7, "model": "/m/a.py", "busy": True, "extra": False, "jobs": 3}],
            "spares": 0,
        })
        self.assertIn("workers  1 bound (1 busy), 0 spare", text)
        self.assertNotIn("unbound", text)


if __name__ == "__main__":
    unittest.main()
