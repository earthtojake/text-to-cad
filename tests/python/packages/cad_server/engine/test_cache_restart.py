"""The engine's document cache after a restart: a restarted engine answers every verb of a document
it saved -- page, export, snapshot, inspect, cad_show -- with nothing run; a document whose code
changed since is answered as its last run, and nothing reruns; and a cache file that does not read is
dropped and written again. On a class engine of the file's own (``cache_fixtures.CacheCase``), with an engine, a
state and a cache folder of its own (``CAD_ENGINE_DIR``, ``CAD_STATE_DIR``, ``CAD_CACHE_DIR``)."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import cache_fixtures, opengl
from tests.python.support.cache_fixtures import await_


class CacheRestartTest(cache_fixtures.CacheCase):
    def test_a_restart_answers_every_verb_from_the_cache_and_an_edit_reruns_nothing(self) -> None:
        ident = self.write("cube")
        self.run_script("cube")
        live = {kind: self.folder / f"live.{kind}" for kind in ("xbf", "glb")}
        self.assertEqual(self.cli("export", ident, *map(str, live.values())).returncode, 0)
        self.cached(ident)
        self.assertEqual(self.cli("stop").returncode, 0)
        (self.project / "cube.ran").unlink()

        inspected = self.cli("inspect", ident, "--json")  # starts the engine afresh
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["closure"]["source"]["function"], "cube")
        self.assertEqual(json.loads(inspected.stdout)["summary"]["state"]["state"], "held")
        cold = {kind: self.folder / f"cold.{kind}" for kind in ("xbf", "glb")}
        exported = self.cli("export", ident, *map(str, cold.values()))
        self.assertEqual(exported.returncode, 0, exported.stderr)
        for kind in cold:
            self.assertEqual(cold[kind].read_bytes(), live[kind].read_bytes(), f"the {kind} is the live export's")
        from cad.engine.render import context

        if opengl.draws(context.available(), "the cold snapshot is drawn by OCCT"):
            snapped = self.cli("snapshot", ident, str(self.folder / "cold.png"))
            self.assertEqual(snapped.returncode, 0, snapped.stderr)
            self.assertGreater((self.folder / "cold.png").stat().st_size, 0)
        # Inspection no longer prefetches meshes. The first page does, and their status
        # fields appear asynchronously: wait for those before comparing two page reads.
        def meshed_page():
            status, structure = self.page(ident)
            return (status, structure) if status == 200 and all(
                "unmeshed" in part for part in structure["prototypes"]) else None

        status, structure = await_(meshed_page, "the page's prefetched meshes")
        self.assertEqual(status, 200)
        self.assertEqual(structure["closure"]["source"]["function"], "cube")
        listed = self.ask({"op": "status"})
        (row,) = [row for row in listed["models"] if row["id"] == ident]
        self.assertEqual((row["state"], row["held"]), ("held", "memory and disk"))
        self.assertEqual([Path(worker["script"]).name for worker in listed["workers"]], ["documents"])
        from cad_server.mcp.server import _say_not_held

        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.engine)}):
            self.assertIsNone(_say_not_held(ident), "cad_show shows it, with nothing to add")
        self.assertFalse(self.ran("cube"), "nothing ran the script")

        # The code changes: every surface answers the document of its last run, as it did, and says
        # nothing of the edit -- when to run the code again is the agent's call; nothing reruns.
        self.write("cube", width=5.0)
        (self.project / "cube.ran").unlink(missing_ok=True)
        self.assertEqual(self.page(ident), (status, structure), "the page reads the last run, as before")
        inspected = self.cli("inspect", ident)
        self.assertEqual((inspected.returncode, inspected.stderr), (0, ""))
        self.assertTrue(inspected.stdout.splitlines()[1].startswith("state       held (in memory and disk), cached, "
                                                                    "built "), inspected.stdout)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": str(self.engine)}):
            self.assertIsNone(_say_not_held(ident))
        self.assertFalse(self.ran("cube"), "nothing reran it")

    def corrupt(self, ident: str) -> None:
        """The document's cache file broken where its bytes are read, its size and its head (the writer
        and the closure a build compares) as they were: what an earlier test of this left behind."""
        path = self.file(ident)
        data = bytearray(path.read_bytes())
        from cad.engine import previous

        kept = data.find(previous._PREFIX)
        kept = data.find(b"\x00", kept) if kept >= 0 else 0
        self.assertLess(kept + 64, len(data) - 1024, "room past the head to break")
        data[-1024:] = bytes(1024)
        path.write_bytes(bytes(data))

    def test_a_cache_file_that_does_not_read_is_dropped_and_written_again(self) -> None:
        ident = self.said()
        self.assertIn("the body ran", self.run_script("cube").stderr)
        meta = self.cached(ident)
        whole = self.file(ident).read_bytes()
        self.assertEqual(self.cli("stop").returncode, 0)
        self.corrupt(ident)
        # After a restart, a verb that reads it fails once, says why and what builds it again, and drops
        # the file: it is not offered again, broken, after every restart.
        out = self.folder / "cube.step"
        exported = self.cli("export", ident, str(out))
        self.assertEqual(exported.returncode, 2, exported.stderr)
        self.assertIn(f"the engine's cache of {ident} does not read", exported.stderr)
        self.assertIn(f"run `cad run {self.project / 'cube.py'}` to build it again", exported.stderr)
        self.assertFalse(out.exists())
        self.assertNotIn("cache", self.record(ident))
        self.assertFalse(self.file(ident).exists())
        self.assertIn("the body ran", self.run_script("cube").stderr)
        self.assertEqual(self.cached(ident, meta["revision"])["bytes"], len(whole), "written again, whole")
        # A build that finds it broken (no verb read it first) runs the body, and the file is written again.
        self.assertEqual(self.cli("stop").returncode, 0)
        self.corrupt(ident)
        self.assertIn("the body ran", self.run_script("cube").stderr)
        self.cached(ident, meta["revision"])
        self.assertEqual(self.cli("stop").returncode, 0)
        self.assertEqual(self.cli("export", ident, str(out)).returncode, 0, "the next restart reads it")
        self.assertGreater(out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
