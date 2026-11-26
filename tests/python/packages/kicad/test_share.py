"""A KiCad board shared by ``cad share`` where KiCad refills its pours, as on a person's computer: the share's view holds
the plot the board's page reads, its pours KiCad's refill of a copy (kicode's, in the environment of ``cad[kicad]``
the server makes, from uv's cache after the KiCad job's first), the person's file never written.

The real command, on this file's own engine, state and cache (the runner's), its refill on whatever the runner says,
against the share service itself (``apps/share/serve.mjs``, ``tests/python/support/share_service.py``). The board
is the KiCad suite's test board, written into a temporary folder.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon, share_service
from tests.python.support.kicad_board import BOARD, write_board
from tests.python.support.paths import SOURCE_PATH

NO_PROXY = {"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"}


class SharedRefill(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.given = engine_daemon.isolate(cls.addClassCleanup, started=False)
        # The engine refills a board's pours with KiCad before it plots it, as a person's does.
        cls.env = engine_daemon.watched({**os.environ, "CAD_KICAD_REFILL": "1", **NO_PROXY}, cls.addClassCleanup)
        cls.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="kicad-share-")))
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.origin = share_service.start(cls.addClassCleanup)
        patch = mock.patch.dict(os.environ, NO_PROXY)
        patch.start()
        cls.addClassCleanup(patch.stop)

    def test_a_shared_boards_view_is_its_plot_with_kicads_refill(self):
        from cad.engine.formats.kicad.poured import cached
        from cad.engine.ids import file_id

        board = write_board(self.folder)
        done = engine_daemon.run([sys.executable, "-m", "cad_server.cli", "share", str(board), "--yes", "--json"],
                                 env={**self.env, "PYTHONPATH": SOURCE_PATH, "CAD_SHARE_URL": self.origin,
                                      "CAD_TELEMETRY": "0", "CAD_UPDATE_CHECK": "0"}, cwd=self.folder)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        found = json.loads(done.stdout)
        # The view's plot is the one the board's page reads: KiCad's refill, which the engine keeps by the board's bytes.
        view = Path(self.given["CAD_CACHE_DIR"]) / "documents" / file_id(board) / "view"
        plot = (view / "plot.json").read_bytes()
        self.assertEqual(json.loads(plot)["pours"], {"refilled": True})
        self.assertEqual(plot, cached(board))
        pours = [item for layer in json.loads(plot)["sheets"][0]["layers"] for item in layer["items"] if item.get("pour")]
        self.assertTrue(pours, "the GND pour is drawn from KiCad's fill")
        # And it is what the share holds, as the service keeps it.
        shared = share_service.manifest(self.origin, found["id"])["view"]["plot.json"]
        self.assertEqual((shared["sha256"], shared["bytes"]), (hashlib.sha256(plot).hexdigest(), len(plot)))
        self.assertEqual(board.read_text(encoding="utf-8"), BOARD, "the person's file is never written")


if __name__ == "__main__":
    unittest.main()
