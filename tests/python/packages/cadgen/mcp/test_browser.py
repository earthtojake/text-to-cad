"""The CAD Viewer link for an app that cannot show CAD views: read from `cadgen viewer --json`."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from cadgen.mcp.browser import ViewerUnavailable, model_link, viewer_url

# Stands in for `cadgen viewer --json`: says what the real one says, then either exits (it reused a
# Viewer) or goes on serving until the test lets it go (it started one).
FAKE = r"""
import json, os, pathlib, sys, time
mode, marker = sys.argv[1], pathlib.Path(sys.argv[2])
marker.write_text(f"{os.getpid()}\n{os.getcwd()}", encoding="utf-8")
if mode == "reused":
    print("Reusing CAD Viewer at http://127.0.0.1:3245/ (serving here, pid 1)")
    print("CAD Viewer URL: http://127.0.0.1:3245/")
if mode != "silent":
    print(json.dumps({"url": "http://127.0.0.1:3245/", "port": 3245, "action": mode}), flush=True)
while mode == "started" and not marker.with_suffix(".done").exists():
    time.sleep(0.01)
"""


class ViewerUrlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.folder = self.tmp / "models"
        self.folder.mkdir()

    def launch(self, mode: str) -> tuple[list[str], Path]:
        marker = self.tmp / f"{mode}.pid"
        return [sys.executable, "-c", FAKE, mode, str(marker)], marker

    def test_a_reused_viewer_is_read_past_its_narration(self) -> None:
        command, marker = self.launch("reused")
        self.assertEqual(viewer_url(str(self.folder), command=command), "http://127.0.0.1:3245/")
        self.assertEqual(marker.read_text(encoding="utf-8").splitlines()[1], os.path.realpath(self.folder))

    def test_a_started_viewer_is_left_serving(self) -> None:
        command, marker = self.launch("started")
        self.addCleanup(marker.with_suffix(".done").touch)
        self.assertEqual(viewer_url(str(self.folder), command=command), "http://127.0.0.1:3245/")
        pid = int(marker.read_text(encoding="utf-8").splitlines()[0])
        os.kill(pid, 0)  # still running: the Viewer outlives the call that started it

    def test_a_launcher_that_prints_no_url_is_a_failure(self) -> None:
        command, _ = self.launch("silent")
        with self.assertRaises(ViewerUnavailable):
            viewer_url(str(self.folder), command=command)

    def test_the_link_opens_the_model_by_its_path_under_the_folder(self) -> None:
        model = self.folder / "arm parts" / "link #2.step"
        self.assertEqual(model_link("http://127.0.0.1:3245/", str(self.folder), str(model)),
                         "http://127.0.0.1:3245/?file=arm%20parts/link%20%232.step")


if __name__ == "__main__":
    unittest.main()
