"""Results by key (STORE.md §3, §4, ``store/results.py``): a model's record names the
key of everything its result was built from and the result is stored under it.

A source reverted to a state already built is a hit on that result, restored without a
run; a STEP deleted beside a current model is exported again without a run; a record
another producer built is rebuilt once; a stored result protects its tree while it
stands and is retired once another cadgen's.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")

from cadgen.daemon import executors  # noqa: E402

PLATE = """\
from cadgen import step
from cadgen import build123d as bd

SIZE = {size}


@step
def plate():
    return bd.Box(SIZE, 4.0, 2.0)
"""

FINISHED = """\
from cadgen import step
from cadgen import build123d as bd

SIZE = {size}


@step(materials={{
    "definitions": {{"finish": {{"name": "Finish", "baseColor": {colour!r}, "roughness": 0.5}}}},
    "assignments": [{{"targets": ["#plate"], "material": "finish"}}],
}})
def plate():
    shape = bd.Box(SIZE, 4.0, 2.0)
    shape.label = "plate"
    return shape
"""


class ResultKeys(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="result-keys-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plate = self.root / "plate.py"
        self.document = self.root / "plate.step"
        self.size(10.0)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.events: list[dict] = []
        executors.set_event_sink(self.events.append)
        self.addCleanup(executors.set_event_sink, None)

    def size(self, value: float) -> None:
        self.plate.write_text(PLATE.format(size=value), encoding="utf-8")

    def build(self) -> tuple[str, list[str]]:
        """``(outcome, the states the model went through)`` of one run."""
        from cadgen.cli._run_model import run_model_argv

        self.events.clear()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(run_model_argv([str(self.plate), "--json"]), 0, err.getvalue())
        outcome = next(line for line in out.getvalue().splitlines() if line.startswith('{"ok":'))
        return outcome, [e["state"] for e in self.events if e.get("state") in ("current", "done")]

    def record(self) -> dict:
        from cadgen.store.records import read_record

        record = read_record(self.plate)
        self.assertIsNotNone(record)
        return record

    def test_a_source_reverted_to_a_state_already_built_is_restored_not_rebuilt(self):
        from cadgen.store.results import read_result

        self.assertEqual(self.build()[1], ["done"])
        first = self.record()
        first_bytes = self.document.read_bytes()
        self.assertEqual(read_result(first["key"])["tree"], first["tree"], "the result is stored under its key")
        self.size(11.0)
        self.assertEqual(self.build()[1], ["done"])
        second = self.record()
        self.assertNotEqual(second["key"], first["key"])
        self.assertNotEqual(self.document.read_bytes(), first_bytes)
        # Back to the first source: its result stands in the index, so nothing runs.
        self.size(10.0)
        outcome, states = self.build()
        self.assertEqual(states, ["current"], "the reverted source ran its body again")
        self.assertIn('"outcome":"current"', outcome)
        restored = self.record()
        self.assertEqual((restored["key"], restored["tree"]), (first["key"], first["tree"]))
        self.assertEqual(self.document.read_bytes(), first_bytes, "the STEP is the first build's again")

    def test_a_restored_result_writes_its_own_sidecar_and_a_lost_one_is_written_again(self):
        """A model with a finish: its sidecar is a function of its record. A source brought
        back to a state already built gets that state's sidecar, bound to that state's
        STEP -- never the sidecar the other state left on disk -- whether the edit between
        changed the finish alone (the STEP kept) or the geometry too (the STEP written
        again); and a sidecar deleted beside a current model is written again from the
        record, with no run (gate clause 5)."""
        from cadgen._internal.source_sidecar import read_source_sidecar, source_sidecar_path

        def finished(size: float, colour: str) -> None:
            self.plate.write_text(FINISHED.format(size=size, colour=colour), encoding="utf-8")

        def sidecar() -> dict:
            return read_source_sidecar(self.document)

        finished(10.0, "#FF0000")
        self.assertEqual(self.build()[1], ["done"])
        red = self.record()
        red_bytes = self.document.read_bytes()
        self.assertEqual(sidecar()["appearance"], red["appearance"])
        # The finish alone: the record moves on and the STEP is kept.
        finished(10.0, "#0000FF")
        self.build()
        blue = self.record()
        self.assertNotEqual(blue["key"], red["key"])
        self.assertNotEqual(blue["appearance"], red["appearance"])
        self.assertEqual(sidecar()["appearance"], blue["appearance"])
        finished(10.0, "#FF0000")
        self.assertEqual(self.build()[1], ["current"])
        self.assertEqual(self.record()["key"], red["key"])
        self.assertEqual(sidecar()["appearance"], red["appearance"], "the restored result took the other state's sidecar")
        self.assertEqual(sidecar()["documentHash"], hashlib.sha256(self.document.read_bytes()).hexdigest())
        self.assertEqual(self.build()[1], ["current"], "the restore left the model owing a run")
        # The geometry and the finish: the STEP is written again, with the record's sidecar.
        finished(11.0, "#0000FF")
        self.assertEqual(self.build()[1], ["done"])
        self.assertNotEqual(self.document.read_bytes(), red_bytes)
        finished(10.0, "#FF0000")
        self.assertEqual(self.build()[1], ["current"])
        self.assertEqual(self.document.read_bytes(), red_bytes)
        self.assertEqual(sidecar()["appearance"], red["appearance"])
        self.assertEqual(sidecar()["documentHash"], hashlib.sha256(red_bytes).hexdigest())
        # A sidecar deleted beside a current model: written again from the record, no run.
        source_sidecar_path(self.document).unlink()
        self.assertEqual(self.build()[1], ["current"])
        self.assertEqual(sidecar()["appearance"], red["appearance"])
        self.assertEqual(sidecar()["documentHash"], hashlib.sha256(red_bytes).hexdigest())

    def test_a_deleted_step_is_exported_again_without_a_run(self):
        self.assertEqual(self.build()[1], ["done"])
        record = self.record()
        written = self.document.read_bytes()
        self.document.unlink()
        outcome, states = self.build()
        self.assertEqual(states, ["current"], "a missing STEP ran the body")
        self.assertIn('"outcome":"current"', outcome)
        self.assertEqual(self.document.read_bytes(), written)
        self.assertEqual(self.record()["key"], record["key"])

    def test_a_record_another_producer_built_is_rebuilt_once(self):
        from cadgen.store.index import remove_entry
        from cadgen.store.records import write_record

        self.assertEqual(self.build()[1], ["done"])
        record = self.record()
        # As an upgrade leaves them: the record keyed by the old producer, no result of this one.
        write_record(self.plate, {**record, "producer": {**record["producer"], "cadgen": "0.4.0"}})
        remove_entry("result", record["key"])
        self.assertEqual(self.build()[1], ["done"], "a record another cadgen built did not rebuild")
        self.assertEqual((self.record()["producer"], self.record()["key"]), (record["producer"], record["key"]))
        self.assertEqual(self.build()[1], ["current"])

    def test_a_stored_result_protects_its_tree_and_another_cadgens_is_retired(self):
        from cadgen.store import gc
        from cadgen.store.index import entry_path, iter_entries, read_entry, remove_entry, write_entry
        from cadgen.store.objects import has_object
        from cadgen.store.records import remove_record
        from cadgen.store.results import read_result

        self.assertEqual(self.build()[1], ["done"])
        record = self.record()
        tree, key = record["tree"], record["key"]
        # Every object is past the grace window, the record and the document entry are
        # gone: only the stored result names the tree.
        for folder in (self.root / "store" / "objects").rglob("*"):
            if folder.is_file():
                os.utime(folder, (time.time() - 7200, time.time() - 7200))
        remove_record(self.plate)
        for document, _path in list(iter_entries("document")):
            remove_entry("document", document)
        gc.collect(grace_seconds=0)
        self.assertTrue(has_object(tree), "the stored result did not protect its tree")
        self.assertIsNotNone(read_result(key))
        # Written by another cadgen a week ago: no build of this one asks for it again.
        entry = read_entry("result", key)
        write_entry("result", key, {**entry, "producer": {**entry["producer"], "cadgen": "0.4.0"}})
        old = time.time() - 8 * 24 * 3600
        os.utime(entry_path("result", key), (old, old))
        gc.collect(grace_seconds=0)
        self.assertIsNone(read_result(key), "another cadgen's result was not retired")
        self.assertFalse(has_object(tree), "the retired result's tree was not collected")


if __name__ == "__main__":
    unittest.main()
