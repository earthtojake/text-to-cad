"""The parts' kept measurements as the daemon holds them (``parts.Parts``): the folder a measuring process writes,
listed and held to its bounds, the least recently used going first, and a half-written file swept once no writer
can be left of it. No engine and no kernel: the folder alone, of the test's own."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path


class PartsBoundsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="engine-parts-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def entry(self, kind: str, name: str, size: int, when: float) -> Path:
        path = self.root / "parts" / kind / name[:2] / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        os.utime(path, (when, when))
        return path

    def test_the_least_recently_used_go_first_until_the_folder_holds_its_bounds(self) -> None:
        from cad_server.engine.parts import Parts

        now = time.time()
        oldest = self.entry("dfm-cnc", "aa11", 100, now - 50)
        read_again = self.entry("features", "bb22", 100, now - 40)
        younger = [self.entry("dfm-sheet", f"c{n}33", 100, now - 30 + n) for n in range(3)]
        os.utime(read_again, (now, now))  # a read sets its time again: the most recently used
        self.assertEqual(Parts(lambda: self.root, entries=10).bound(), (5, 500), "within its bounds: nothing goes")
        self.assertEqual(Parts(lambda: self.root, entries=3).bound(), (3, 300))
        self.assertFalse(oldest.exists())
        self.assertFalse(younger[0].exists())
        self.assertTrue(read_again.exists() and younger[1].exists() and younger[2].exists())
        self.assertFalse(oldest.parent.exists(), "a folder goes with its last entry")
        self.assertEqual(Parts(lambda: self.root, entries=10, budget=250).bound(), (2, 200), "and its bytes")
        self.assertTrue(read_again.exists() and younger[2].exists())

    def test_a_half_written_file_is_swept_only_once_no_writer_is_left_of_it(self) -> None:
        from cad_server.engine import parts

        now = time.time()
        kept = self.entry("dfm-cnc", "aa11", 10, now)
        writing = kept.with_name(f"{kept.name}.123.0a0b0c0d.tmp")
        left = kept.with_name(f"{kept.name}.456.0a0b0c0d.tmp")
        for path, when in ((writing, now - 5), (left, now - parts.STALE_SECONDS - 5)):
            path.write_bytes(b"{")
            os.utime(path, (when, when))
        self.assertEqual(parts.Parts(lambda: self.root).bound(), (1, 10), "a half-written file is no entry")
        self.assertTrue(writing.exists(), "one a process may be writing now")
        self.assertFalse(left.exists(), "one a stopped process left")
        self.assertTrue(kept.exists())

    def test_the_engine_s_registry_names_the_folder_and_none_keeps_nothing(self) -> None:
        from cad_server.engine.parts import Parts
        from cad_server.engine.registry import Folder, Registry

        self.entry("dfm-cnc", "aa11", 10, time.time())
        registry = Registry(self.root / "state", cache=Folder(self.root))
        self.assertEqual(Parts(lambda: registry).bound(), (1, 10))
        self.assertEqual(Parts(lambda: Registry(self.root / "state")).bound(), (0, 0), "no cache folder")
        self.assertEqual(Parts(None).bound(), (0, 0))

    def test_listings_asked_while_one_runs_run_once_more_after_it(self) -> None:
        from cad_server.engine.parts import Parts

        held = Parts(lambda: self.root, entries=1)
        self.entry("dfm-cnc", "aa11", 10, time.time() - 10)
        newest = self.entry("dfm-cnc", "bb22", 10, time.time())
        held.soon()
        held.soon()
        deadline = time.monotonic() + 30
        while (held.listing or held.held is None) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(held.held, (1, 10))
        self.assertTrue(newest.exists())


if __name__ == "__main__":
    unittest.main()
