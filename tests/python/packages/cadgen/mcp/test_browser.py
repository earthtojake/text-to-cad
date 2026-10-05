"""The CAD Viewer link for an app that cannot show CAD views: read from `cadgen viewer --json`."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from cadgen.mcp.browser import LAUNCH, ViewerUnavailable, model_link, viewer_url

# Stands in for `cadgen viewer --json --detach`: says what the real one says, then exits, whether it
# reused a Viewer or started one in the background.
FAKE = r"""
import json, os, pathlib, sys
mode, marker = sys.argv[1], pathlib.Path(sys.argv[2])
marker.write_text(f"{os.getpid()}\n{os.getcwd()}", encoding="utf-8")
if mode == "reused":
    print("Reusing CAD Viewer at http://127.0.0.1:3245/ (pid 1, started in /somewhere)")
    print("CAD Viewer URL: http://127.0.0.1:3245/")
if mode != "silent":
    print(json.dumps({"url": "http://127.0.0.1:3245/", "port": 3245, "action": mode}), flush=True)
"""


class ViewerUrlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def launch(self, mode: str) -> tuple[list[str], Path]:
        marker = self.tmp / f"{mode}.pid"
        return [sys.executable, "-c", FAKE, mode, str(marker)], marker

    def started_in(self, marker: Path) -> str:
        # Resolved: macOS reports /private/var for /var, Windows a short 8.3 name for a long one.
        return os.path.realpath(marker.read_text(encoding="utf-8").splitlines()[1])

    def test_a_reused_viewer_is_read_past_its_narration_and_runs_from_home(self) -> None:
        command, marker = self.launch("reused")
        self.assertEqual(viewer_url(command=command), "http://127.0.0.1:3245/")
        # The Viewer opens any model by its absolute path: where it starts only decides how a
        # developer's relative links resolve.
        self.assertEqual(self.started_in(marker), os.path.realpath(os.path.expanduser("~")))
        command, marker = self.launch("reused")
        viewer_url(cwd=str(self.tmp), command=command)
        self.assertEqual(self.started_in(marker), os.path.realpath(self.tmp))

    def test_a_started_viewer_runs_detached_from_the_launch(self) -> None:
        # The launch returns once the Viewer answers; the Viewer runs on in its own session and
        # writes to its own log, never into a pipe this server stopped reading.
        self.assertIn("--detach", LAUNCH)
        command, _ = self.launch("started")
        self.assertEqual(viewer_url(command=command), "http://127.0.0.1:3245/")

    def test_a_launcher_that_prints_no_url_is_a_failure(self) -> None:
        command, _ = self.launch("silent")
        with self.assertRaises(ViewerUnavailable):
            viewer_url(command=command)

    def test_the_link_opens_the_model_by_its_absolute_path(self) -> None:
        model = os.path.join(os.sep, "work", "arm parts", "link #2?&%.step")
        expected = "/work/arm%20parts/link%20%232%3F%26%25.step"
        self.assertEqual(model_link("http://127.0.0.1:3245/", model), f"http://127.0.0.1:3245/?file={expected}")
        # A drive keeps its colon, readable as it is typed.
        self.assertEqual(model_link("http://127.0.0.1:3245/", "C:/models/a.step"),
                         "http://127.0.0.1:3245/?file=C:/models/a.step")


if __name__ == "__main__":
    unittest.main()
