"""Public source builds preserve closure and STEP identity across memo hits."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory


FACTORY = """\
from cadgen import build123d as bd
from cadgen import memo

RADIUS = 1.5

@memo
def plate(width=30.0, *, holes=3):
    with bd.BuildPart() as p:
        bd.Box(width, 20, 6)
        for i in range(holes):
            with bd.Locations((-width/2 + 5 + i*(width-10)/(holes-1), 0, 0)):
                bd.Cylinder(RADIUS, 10, mode=bd.Mode.SUBTRACT)
    return p.part
"""

PARENT = """\
from cadgen import build123d as bd
from cadgen import step
from memo_geometry import plate

SHIFT = {shift}

@step
def assembly():
    parts = []
    for i in range(3):
        part = bd.Pos(i*45, SHIFT, 0) * plate(30.0, holes=3+i)
        part.label = 'plate-' + str(i)
        parts.append(part)
    return bd.Compound(children=parts, label='assembly')

if __name__ == '__main__':
    assembly()
"""


class MemoBuildTest(unittest.TestCase):
    def test_public_edits_disabled_cache_and_restarted_interpreter_match(self):
        from cadgen import memoization
        from cadgen.cli._run_model import run_model_argv
        from cadgen.store.gate import stale
        from cadgen.store.records import read_record

        with generated_cad_directory(prefix="cadgen-memo-build-") as folder:
            root = Path(folder)
            script = root / "assembly.py"
            helper = root / "memo_geometry.py"
            helper.write_text(FACTORY, encoding="utf-8")
            store = root / "store"
            env = {"CADGEN_CACHE_DIR": str(store), "CADGEN_DAEMON": "0",
                   "CADGEN_MEMO_CACHE": "1", "CADGEN_OP_MEMO": "1",
                   "CADGEN_OP_MEMO_DISK": "1"}

            def build(shift, *, cached=True):
                script.write_text(PARENT.format(shift=shift), encoding="utf-8")
                before = dict(memoization._stats)
                capture = io.StringIO()
                with mock.patch.dict(os.environ, {"CADGEN_MEMO_CACHE": "1" if cached else "0"}), contextlib.redirect_stdout(capture), contextlib.redirect_stderr(capture):
                    result = run_model_argv([str(script)])
                self.assertEqual(0, result, capture.getvalue())
                record = read_record(script)
                delta = {key: value - before[key] for key, value in memoization._stats.items()}
                return (root / "assembly.step").read_bytes(), record, delta

            with mock.patch.dict(os.environ, env), mock.patch.object(memoization, "_reuse_trusted", False):
                original, original_record, cold = build(0)
                placed, _record, warm = build(5)
                restored, restored_record, disabled = build(0, cached=False)
                self.assertEqual(3, cold["misses"])
                self.assertEqual(0, warm["hits"])
                self.assertEqual(3, warm["misses"])
                self.assertEqual(3, disabled["misses"])
                self.assertEqual(original, restored)
                self.assertEqual(original_record["tree"], restored_record["tree"])
                self.assertNotEqual(original, placed)
                closure_files = original_record["closure"]["files"]
                self.assertTrue(any(Path(path).name == "memo_geometry.py" for path in closure_files))

                # Only a fresh worker bootstrap has a reuse witness. Its first
                # run populates entries; the next interpreter has no recipes
                # or native handles and must use the verified disk result.
                script.write_text(PARENT.format(shift=5), encoding="utf-8")
                command = "from cadgen.daemon.worker import _warm_imports; _warm_imports(); from cadgen.cli._run_model import run_model_argv; from cadgen import memoization; import json,sys; result=run_model_argv([sys.argv[1], '--force']); print('MEMO_STATS='+json.dumps(memoization._stats)); raise SystemExit(result)"
                for expected_hits in (0, 3):
                    completed = subprocess.run([sys.executable, "-c", command, str(script)],
                                               capture_output=True, text=True, timeout=30,
                                               env={**os.environ, **env})
                    self.assertEqual(0, completed.returncode, completed.stderr[-4000:])
                    stats = json.loads(next(line.partition("=")[2] for line in completed.stdout.splitlines() if line.startswith("MEMO_STATS=")))
                    self.assertEqual(expected_hits, stats["hits"])
                    self.assertEqual(placed, (root / "assembly.step").read_bytes())

                helper.write_text(FACTORY.replace("RADIUS = 1.5", "RADIUS = 2.0"), encoding="utf-8")
                self.assertTrue(stale(script).stale)
                changed, changed_record, new_helper = build(5)
                self.assertEqual(3, new_helper["misses"])
                self.assertNotEqual(placed, changed)
                self.assertNotEqual(original_record["tree"], changed_record["tree"])
                self.assertFalse(stale(script).stale)


if __name__ == "__main__":
    unittest.main()
