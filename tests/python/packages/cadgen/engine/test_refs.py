"""References to geometry: ``cadgen inspect`` resolves a ref -- a part's label or an occurrence's
path (``hand/finger.2``), and an element's name or ordinal -- by name in the latest build; a model
never reads a file its own build writes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from cadgen.engine import build as engine_build
from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"

HAND = """
import build123d as bd
from cadgen.engine import xbf


@xbf("XBF/hand.xbf")
def hand():
    palm = bd.Box(30, 20, 5)
    palm.label = "palm"
    finger = bd.Box(4, 4, 20) - bd.Pos(0, 0, 8) * bd.Cylinder(1, 10)
    finger.label = "finger"
    fingers = [finger.moved(bd.Location((x, 0, 12))) for x in (-10, 0, 10)]
    return bd.Compound(children=[palm, *fingers], label="hand")
"""


class _Folder(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-select-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.restart()
        self.addCleanup(self.restart)

    def restart(self) -> None:
        """What a new worker holds: nothing."""
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        engine_build._BUILT.clear()

    def write(self, name: str, text: str) -> Path:
        script = self.folder / name
        script.write_text(textwrap.dedent(text), encoding="utf-8")
        os.utime(script, ns=(time.time_ns(), time.time_ns()))
        return script

    def build(self, name: str, text: str | None = None) -> list[dict]:
        script = self.write(name, text) if text is not None else self.folder / name
        return engine_build.build(script, cwd=self.folder)

    def built(self, name: str, text: str | None = None) -> dict:
        (report,) = self.build(name, text)
        self.assertTrue(report["ok"], report.get("error"))
        return report


class ReadAndPlaceTest(_Folder):
    def test_a_read_of_a_file_the_build_writes_is_refused_when_the_memo_holds_it(self) -> None:
        """The refusal comes before the memo: a read the memo holds from a build that did not
        write the file is refused once the build writes it. (Each body is edited so that it runs:
        an unchanged one is replayed, and reads nothing.)"""
        writer = """
            import build123d as bd
            from cadgen.engine import step, xbf


            @xbf("XBF/plate.xbf")
            @step("plate.step")
            def plate():
                return bd.Box(30, 20, 4)
        """
        reads = """
            from pathlib import Path
            import build123d as bd
            from cadgen.engine import read_step, read_xbf, step, xbf

            HERE = Path(__file__).resolve().parent
            {plate}

            @xbf("XBF/from_xbf.xbf")
            def from_xbf():
                return read_xbf(HERE / "XBF/plate.xbf"){tail}


            @xbf("XBF/from_step.xbf")
            def from_step():
                return read_step(HERE / "plate.step"){tail}
        """
        self.built("writer.py", writer)
        self.assertTrue(all(report["ok"] for report in self.build("reads.py", reads.format(plate="", tail=""))),
                        "another script's files: read, and held by the memo")
        plate = "\n            ".join(textwrap.dedent(writer).split("\n\n\n", 1)[1].strip().splitlines())
        refused = self.build("reads.py", reads.format(plate=plate, tail=".moved(bd.Location((0, 0, 1)))"))
        self.assertEqual([report["ok"] for report in refused], [True, False, False])
        self.assertIn("read_xbf", refused[1]["error"])
        self.assertIn("read_step", refused[2]["error"])
        for report in refused[1:]:
            self.assertIn("this build writes it (reads.py::plate)", report["error"])

    def test_a_child_model_s_second_placement_measures_as_its_first(self) -> None:
        reports = self.build("pegs.py", """
            import build123d as bd
            from cadgen.engine import xbf


            @xbf("XBF/peg.xbf")
            def peg():
                return bd.Cylinder(2, 10)


            @xbf("XBF/rack.xbf")
            def rack():
                first, second = peg().shape, peg().shape.moved(bd.Location((10, 0, 0)))
                if abs(second.volume - first.volume) > 1e-6:
                    raise ValueError(f"the second placement measures {second.volume}, not {first.volume}")
                return bd.Compound(children=[first, second], label="rack")
        """)
        self.assertEqual([report["ok"] for report in reports], [True, True], [r.get("error") for r in reports])


class WhereTest(unittest.TestCase):
    """``cadgen inspect`` resolves the same grammar, through a daemon of the test's own."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="engine-where-")).resolve()
        cls.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        cls.env = engine_daemon.started({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(cls.state),
                                         "CADGEN_ENGINE_MESH": "inline"}, cls.addClassCleanup)
        (cls.folder / "hand.py").write_text(textwrap.dedent(HAND), encoding="utf-8")
        (report,) = engine_build.build(cls.folder / "hand.py", cwd=cls.folder)
        assert report["ok"], report

    @classmethod
    def tearDownClass(cls) -> None:
        subprocess.run([sys.executable, "-m", "cadgen.engine", "stop"], cwd=cls.folder, env=cls.env,
                       capture_output=True, timeout=120)
        shutil.rmtree(cls.folder, ignore_errors=True)
        shutil.rmtree(cls.state, ignore_errors=True)

    def where(self, ref: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, "-m", "cadgen.cli", "inspect", "XBF/hand.xbf", ref], cwd=self.folder,
                                 env=self.env)

    def test_where_takes_an_occurrence_path(self) -> None:
        done = self.where("hand/finger.2/face 1")
        self.assertEqual(done.returncode, 0, done.stderr)
        face = json.loads(done.stdout)
        self.assertEqual((face["path"], face["kind"], face["ordinal"], face["part"]), ("hand/finger.2", "face", 1, "finger"))
        self.assertEqual(face["ref"], f"hand/finger.2/{face['name']}")
        self.assertEqual([round(value, 6) for value in face["centroid"]], [-2.0, 0.0, 12.0], "where finger 2 stands")
        # The line the viewer copies -- the file, its canonical ref -- names the same element.
        copied = self.where(f"{self.folder / 'XBF/hand.xbf'}#{face['ref']}")
        self.assertEqual(copied.returncode, 0, copied.stderr)
        self.assertEqual({k: v for k, v in json.loads(copied.stdout).items() if k != "made_by"},
                         {k: v for k, v in face.items() if k != "made_by"})
        weighed = json.loads(self.where("hand/finger.3").stdout)
        self.assertEqual((weighed["ref"], weighed["parts"], weighed["path"]), ("hand/finger.3", 1, "hand/finger.3"))
        self.assertEqual(json.loads(self.where("hand").stdout)["unweighed"],
                         ["hand/palm", "hand/finger.1", "hand/finger.2", "hand/finger.3"])
        for ref, said in (("finger", "finger names 3 occurrences in hand.xbf: hand/finger.1, hand/finger.2, "
                                     "hand/finger.3"),
                          ("finger_2/face 1", "hand.xbf has no part or assembly finger_2"),
                          ("hand/finger.2/face 99", "hand/finger.2 has no face 99 (it has 8)")):
            refused = self.where(ref)
            self.assertEqual(refused.returncode, 2, refused.stdout)
            self.assertIn(said, refused.stderr)

    def test_the_command_reads_a_ref_without_loading_the_kernel(self) -> None:
        # The engine measures; the command only parses and places: a ref costs it no kernel load.
        code = ("import runpy, sys\n"
                "sys.argv = ['cadgen', 'inspect', 'XBF/hand.xbf', 'hand/finger.2/face 1']\n"
                "try:\n    runpy.run_module('cadgen.cli', run_name='__main__')\n"
                "except SystemExit as stop:\n    assert not stop.code, stop.code\n"
                "print(sorted(name for name in sys.modules if name.startswith('OCP.') or name == 'cadgen.engine.kernel.trace'),"
                " file=sys.stderr)\n")
        done = engine_daemon.run([sys.executable, "-c", code], cwd=self.folder, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["path"], "hand/finger.2")
        self.assertEqual(done.stderr.strip().splitlines()[-1], "[]", "no kernel module was loaded")


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()


class NearestTest(unittest.TestCase):
    def test_an_unknown_owner_is_answered_with_each_near_occurrence_once_in_the_tree_s_order(self) -> None:
        from cadgen.engine import refs

        children = [{"name": "plate", "prototype": 0}] + [{"name": f"standoff_{i}", "prototype": 1} for i in range(4)]
        root = refs.structure_tree({"tree": {"name": "kit", "children": children}})
        # Not `standoff_3, standoff_2, standoff_1, standoff_0, kit/standoff_3`: one part, one name.
        self.assertEqual(refs._nearest(root, "standoff"), "standoff_0, standoff_1, standoff_2, standoff_3")
        self.assertEqual(refs._nearest(root, "kit/plat").split(", ")[0], "plate", "matched by its path, named as its owner")
