"""A model's previous document is its cache: a restart with nothing changed runs no
body and writes nothing; anything else builds, and writes the cold build's bytes."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from cadgen.engine import build as engine_build
from cadgen.engine import document, previous

KIT = """
import json
from pathlib import Path

import build123d as bd
from cadgen.engine import read_step, xbf

HERE = Path(__file__).resolve().parent
# A set of strings: its order is another in every process.
NAMES = {{"peg", "pin", "dowel", "stud", "post", "spigot"}}


@xbf("XBF/peg.xbf")
def peg():
    size = json.loads((HERE / "peg.json").read_text())["size"]
    peg = bd.Box(size, size, {peg})
    peg.label = "peg" if "peg" in NAMES else "part"
    return peg


@xbf("XBF/cap.xbf")
def cap():
    cap = read_step(HERE / "inputs" / "cap.step")
    cap.label = "cap"
    return cap


@xbf("XBF/kit.xbf")
def kit():
    left = peg().shape.moved(bd.Location((10, 0, 0)))
    right = peg().shape.moved(bd.Location((-10, 0, 0)))
    plate = bd.Box({plate}, 30, json.loads((HERE / "kit.json").read_text())["thickness"])
    plate.label = "plate"
    return bd.Compound(children=[left, right, cap().shape.moved(bd.Location((0, 0, 8))), plate], label="kit")
"""


class PreviousTest(unittest.TestCase):
    def setUp(self) -> None:
        import build123d as bd

        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-previous-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "kit.py"
        self.xbf = self.folder / "XBF/kit.xbf"
        (self.folder / "inputs").mkdir()
        bd.export_step(bd.Cylinder(3, 4), str(self.folder / "inputs" / "cap.step"))
        (self.folder / "peg.json").write_text(json.dumps({"size": 4}), encoding="utf-8")
        (self.folder / "kit.json").write_text(json.dumps({"thickness": 2}), encoding="utf-8")
        self.restart()
        self.addCleanup(self.restart)
        memo.install()

    def restart(self) -> None:
        """What a new worker holds: nothing."""
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        engine_build._BUILT.clear()

    def source(self, peg: float = 10, plate: float = 40) -> None:
        self.script.write_text(textwrap.dedent(KIT.format(peg=peg, plate=plate)), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))

    def kit(self) -> dict:
        (report,) = engine_build.build(self.script, ["kit"], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        return report

    def cold(self, **values) -> bytes:
        """The kit as a process that never built it, with no file, builds it."""
        self.restart()
        self.xbf.unlink(missing_ok=True)
        self.source(**values)
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "no file yet")
        return self.xbf.read_bytes()

    def test_a_restart_with_nothing_changed_runs_no_body_and_writes_nothing(self) -> None:
        first = self.cold()
        written = self.xbf.stat().st_mtime_ns
        self.restart()
        report = self.kit()
        self.assertEqual(report["cache"], {"used": True, "from": "file"})
        self.assertEqual(report["memo"]["bodies_run"], 0)
        self.assertEqual(report["memo"]["bodies_loaded"], 3, "kit, peg and cap")
        self.assertEqual(report["bodies"], {"kit.py::kit": "loaded"})
        self.assertEqual([row["written"] for row in report["files"].values()], [False])
        self.assertEqual(self.xbf.read_bytes(), first)
        self.assertEqual(self.xbf.stat().st_mtime_ns, written)
        # The next build in the same worker: the key it took, in memory, and no read.
        again = self.kit()
        self.assertEqual(again["cache"], {"used": True, "from": "memory"})
        self.assertNotIn("read", again["timings"])
        self.assertEqual(self.xbf.stat().st_mtime_ns, written)

    def test_another_process_takes_the_file_whatever_its_hash_seed(self) -> None:
        import subprocess
        import sys

        self.source()
        code = ("import json, sys; from pathlib import Path; from cadgen.engine import build; "
                "print(json.dumps(build.build(Path(sys.argv[1]), ['kit'], cwd=Path(sys.argv[1]).parent)[0]))")
        found = []
        for seed in ("1", "2"):
            done = subprocess.run([sys.executable, "-c", code, str(self.script)], capture_output=True, text=True,
                                  env={**os.environ, "PYTHONHASHSEED": seed})
            self.assertEqual(done.returncode, 0, done.stderr)
            found.append(json.loads(done.stdout.strip().splitlines()[-1]))
        self.assertEqual(found[0]["cache"]["reason"], "no file yet")
        self.assertEqual(found[1]["cache"], {"used": True, "from": "file"})

    def test_an_edit_after_a_restart_writes_the_cold_bytes(self) -> None:
        self.cold()
        self.restart()
        self.source(peg=12)
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "../kit.py: peg changed")
        self.assertEqual(report["cache"]["changed"], ["../kit.py: peg changed"])
        self.assertEqual(report["bodies"], {"kit.py::kit": "run", "kit.py::peg": "run", "kit.py::cap": "run"})
        edited = self.xbf.read_bytes()
        self.assertEqual(edited, self.cold(peg=12))
        # Taken, then edited in the same worker: built, the cold bytes again.
        self.restart()
        self.assertTrue(self.kit()["cache"]["used"])
        self.source(peg=12, plate=44)
        report = self.kit()
        self.assertFalse(report["cache"]["used"])
        self.assertEqual(report["memo"]["bodies_run"], 3)
        self.assertEqual(self.xbf.read_bytes(), self.cold(peg=12, plate=44))

    def test_an_unchanged_warm_build_runs_and_replays_nothing_and_leaves_its_file(self) -> None:
        first = self.cold()
        written = self.xbf.stat().st_mtime_ns
        report = self.kit()
        self.assertEqual(report["cache"], {"used": True, "from": "memory"})
        self.assertEqual(report["bodies"], {"kit.py::kit": "loaded"})
        self.assertEqual((report["memo"]["bodies_run"], report["memo"]["bodies_skipped"],
                          report["memo"]["bodies_loaded"]), (0, 0, 3))
        self.assertEqual([row["written"] for row in report["files"].values()], [False])
        self.assertEqual((self.xbf.read_bytes(), self.xbf.stat().st_mtime_ns), (first, written))

    def test_warm_no_ops_keep_the_memo_an_edit_replays(self) -> None:
        from cadgen.engine.kernel import memo

        self.cold()
        for _ in range(memo.RUNS_KEPT + 2):
            self.assertTrue(self.kit()["cache"]["used"])
        self.source(plate=44)
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "../kit.py: kit changed")
        self.assertEqual(report["bodies"], {"kit.py::kit": "run", "kit.py::peg": "replayed", "kit.py::cap": "replayed"})
        self.assertEqual(self.xbf.read_bytes(), self.cold(plate=44))

    def test_a_warm_edit_of_the_source_or_an_input_builds(self) -> None:
        import build123d as bd

        self.cold()
        self.source(peg=12)
        report = self.kit()
        self.assertEqual((report["cache"]["reason"], report["bodies"]["kit.py::peg"]), ("../kit.py: peg changed", "run"))
        for change, named in (("json", "../peg.json"), ("root", "../kit.json"), ("step", "../inputs/cap.step")):
            if change == "json":
                (self.folder / "peg.json").write_text(json.dumps({"size": 5}), encoding="utf-8")
            elif change == "root":
                (self.folder / "kit.json").write_text(json.dumps({"thickness": 3}), encoding="utf-8")
            else:
                bd.export_step(bd.Cylinder(3, 5), str(self.folder / "inputs" / "cap.step"))
            report = self.kit()
            self.assertEqual(report["cache"]["reason"], f"{named} changed", change)
            self.assertTrue(report["files"][str(self.xbf)]["written"], change)

    def test_a_warm_build_whose_file_moved_or_went_is_replayed(self) -> None:
        first = self.cold()
        later = self.xbf.stat().st_mtime_ns + 1_000_000_000
        os.utime(self.xbf, ns=(later, later))
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "replayed from memory")
        self.assertEqual(set(report["bodies"].values()), {"replayed"})
        self.assertEqual(self.xbf.read_bytes(), first)
        self.xbf.unlink()
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "replayed from memory")
        self.assertTrue(report["files"][str(self.xbf)]["written"])
        self.assertEqual(self.xbf.read_bytes(), first)
        self.assertEqual(self.kit()["cache"], {"used": True, "from": "memory"})

    def test_a_warm_build_whose_child_models_file_moved_or_went_is_replayed(self) -> None:
        self.cold()
        self.assertEqual(self.kit()["cache"], {"used": True, "from": "memory"}, "every file as the last build left it")
        peg = self.folder / "XBF/peg.xbf"
        written = peg.read_bytes()
        later = peg.stat().st_mtime_ns + 1_000_000_000
        os.utime(peg, ns=(later, later))
        self.assertEqual(self.kit()["cache"]["reason"], "replayed from memory", "a child's file moved")
        peg.unlink()
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "replayed from memory", "a child's file gone")
        self.assertEqual(peg.read_bytes(), written, "the replay writes the child's file again")
        self.assertEqual(self.kit()["cache"], {"used": True, "from": "memory"})

    def test_a_verifying_warm_build_runs_every_body(self) -> None:
        self.cold()
        (report,) = engine_build.build(self.script, ["kit"], cwd=self.folder, verify=True)
        self.assertEqual((report["cache"]["reason"], report["memo"]["bodies_run"]), ("verifying", 3))
        self.assertEqual(set(report["verify"]["checked"].values()), {"same"})

    def test_a_changed_input_file_builds(self) -> None:
        self.cold()
        # A child's own read, the root's own read, a file read through the engine.
        for change in ("json", "root", "step"):
            self.restart()
            if change == "json":
                (self.folder / "peg.json").write_text(json.dumps({"size": 5}), encoding="utf-8")
            elif change == "root":
                (self.folder / "kit.json").write_text(json.dumps({"thickness": 3}), encoding="utf-8")
            else:
                import build123d as bd

                bd.export_step(bd.Cylinder(3, 5), str(self.folder / "inputs" / "cap.step"))
            report = self.kit()
            named = {"json": "../peg.json", "root": "../kit.json", "step": "../inputs/cap.step"}[change]
            self.assertEqual(report["cache"]["reason"], f"{named} changed", change)
            self.assertTrue(report["files"][str(self.xbf)]["written"])
        gone = self.folder / "peg.json"
        gone.unlink()
        self.restart()
        engine_build.build(self.script, ["kit"], cwd=self.folder)  # the body raises: no json
        self.assertTrue(self.xbf.exists(), "a failed build leaves the file")

    def test_the_file_names_its_inputs_by_relative_path_and_holds_no_script_path(self) -> None:
        self.cold()
        text = self.xbf.read_bytes()
        writer, found = previous.scan(self.xbf)
        record = json.loads(found)
        # Relative to the document's folder: XBF/ beside the script; digests, never contents.
        self.assertEqual([row[:2] for row in record["inputs"]], [["read", "../peg.json"], ["file", "../inputs/cap.step"],
                                                                 ["read", "../kit.json"]])
        self.assertTrue(all(len(row[2]) == 64 for row in record["inputs"]))
        self.assertEqual(record["source"], {"kind": "script", "path": "../kit.py", "function": "kit"})
        self.assertNotIn(str(self.folder).encode(), text)
        self.assertNotIn(b"thickness", text, "no source text")
        self.assertEqual(writer, document._writer())

    def test_another_programs_file_is_built_again(self) -> None:
        self.cold()
        writer = document._writer().encode()
        self.xbf.write_bytes(self.xbf.read_bytes().replace(writer, writer.replace(b"(cadgen ", b"(cadgem ")))
        self.restart()
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "written by another program")
        self.assertTrue(report["files"][str(self.xbf)]["written"])

    def test_another_release_of_the_format_is_current_and_another_format_builds_once(self) -> None:
        self.cold()
        writer = document._writer().encode()
        release = previous.version().encode()
        # Another cadgen release that wrote this format: the key is the format's, the file is taken.
        other_release = writer.replace(b"(cadgen " + release, b"(cadgen " + b"9" * len(release))
        self.xbf.write_bytes(self.xbf.read_bytes().replace(writer, other_release))
        self.restart()
        self.assertEqual(self.kit()["cache"], {"used": True, "from": "file"})
        # A document of the format before (the key made differently): built again, once.
        old = other_release.replace(f"cadgen.engine {previous.FORMAT} ".encode(), b"cadgen.engine xbf/1 ")
        self.assertEqual(len(old), len(other_release))
        self.xbf.write_bytes(self.xbf.read_bytes().replace(other_release, old))
        self.restart()
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], f"written by {old.decode()}")
        self.assertTrue(report["files"][str(self.xbf)]["written"])
        self.restart()
        self.assertEqual(self.kit()["cache"], {"used": True, "from": "file"}, "built once, then current")

    def test_a_missing_or_broken_file_builds(self) -> None:
        first = self.cold()
        self.restart()
        self.xbf.unlink()
        self.assertEqual(self.kit()["cache"]["reason"], "no file yet")
        self.assertEqual(self.xbf.read_bytes(), first)
        # Its head whole, the rest gone: the closure shows, the document does not read. (Cut
        # right after the closure, in the main label's attributes: OCCT's reader aborts the
        # process on some cuts of a shape section rather than failing, an uncaught
        # Standard_NullObject -- measured at a half of this one, and at a third once the
        # closure grew by its symbols.)
        head = first[: first.index(b"\x00", first.index(b'{"schema":"cadgen.engine closure/1",')) + 1]
        self.xbf.write_bytes(head)
        self.restart()
        report = self.kit()
        self.assertTrue(report["cache"]["reason"].startswith("the file does not read"), report["cache"])
        self.assertEqual(self.xbf.read_bytes(), first)

    def export(self, name: str) -> bytes:
        """The kit's STEP as ``cadgen export`` writes it, in a process of its own."""
        import subprocess
        import sys

        out = self.folder / name
        done = subprocess.run([sys.executable, "-m", "cadgen.engine", "export", str(self.xbf), str(out)],
                              cwd=self.folder, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        # The STEP header's time stamp is the second it was written: masked.
        return re.sub(rb"'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d'", b"'T'", out.read_bytes(), count=1)

    def test_a_taken_document_serves_and_exports_as_the_cold_one(self) -> None:
        self.cold()
        structure = document.Loaded(self.xbf).structure()
        step = self.export("cold.step")
        self.restart()
        self.assertTrue(self.kit()["cache"]["used"])
        again = document.Loaded(self.xbf)
        self.assertEqual(json.loads(json.dumps(again.structure())), json.loads(json.dumps(structure)))
        self.assertEqual(self.export("taken.step"), step)
        # Provenance is the worker's that built it: a taken document has none to give.
        key = again.prototypes[0].key
        self.assertIsNone(engine_build.made_by(str(self.xbf), key, "face", 1))


HELPER = """
# The plate's dimensions{comment}
WIDTH = {width}


def unused():
    return {unused}
"""

PLATE = """
import json
from pathlib import Path

import build123d as bd
from cadgen.engine import xbf

import dims

HERE = Path(__file__).resolve().parent


@xbf("XBF/plate.xbf")
def plate():
    try:
        depth = json.loads((HERE / "depth.json").read_text())["depth"]
    except FileNotFoundError:
        depth = 10
    plate = bd.Box(dims.WIDTH, depth, 2)
    plate.label = "plate"
    return plate
"""


class ClosureTest(unittest.TestCase):
    """The closure an xbf carries: pointers and digests, every field read back; what a restart
    names when it differs; the code it was built from, packaged and built again."""

    def setUp(self) -> None:
        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-closure-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "plate.py"
        self.xbf = self.folder / "XBF/plate.xbf"
        self.script.write_text(textwrap.dedent(PLATE), encoding="utf-8")
        self.helper()
        (self.folder / "depth.json").write_text(json.dumps({"depth": 6}), encoding="utf-8")
        self.restart()
        self.addCleanup(self.restart)
        memo.install()

    def restart(self) -> None:
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        engine_build._BUILT.clear()

    def helper(self, width: float = 20, comment: str = "", unused: int = 1) -> None:
        path = self.folder / "dims.py"
        path.write_text(textwrap.dedent(HELPER.format(width=width, comment=comment, unused=unused)), encoding="utf-8")
        os.utime(path, ns=(time.time_ns(), time.time_ns()))

    def plate(self, restart: bool = True) -> dict:
        if restart:
            self.restart()
        (report,) = engine_build.build(self.script, ["plate"], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        return report

    def test_the_closure_round_trips_every_field(self) -> None:
        from cadgen.engine import api

        self.plate()
        record = previous.of(self.xbf)
        self.assertEqual(list(record), ["schema", "engine", "libs", "source", "modules", "symbols", "inputs", "bodies",
                                        "key"])
        self.assertEqual(record["schema"], "cadgen.engine closure/1")
        version = (Path(__file__).resolve().parents[5] / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(record["engine"]["release"], f"cadgen {version}", "the release VERSION stamps")
        self.assertEqual((record["engine"]["format"], len(record["engine"]["digest"])), ("xbf/7", 32))
        self.assertEqual(set(record["libs"]), {"build123d", "OCP"})
        self.assertEqual(record["source"], {"kind": "script", "path": "../plate.py", "function": "plate"})
        self.assertEqual([path for path, _digest in record["modules"]], ["../dims.py", "../plate.py"])
        self.assertEqual([row[:2] for row in record["inputs"]], [["read", "../depth.json"]])
        self.assertEqual(record["bodies"], 1)
        self.assertEqual(record["key"], previous.key(record))
        # The same record, whole, through every door that reads it.
        self.assertEqual(document.Loaded(self.xbf).closure, record)
        self.assertEqual(api.inspect(self.xbf), record)
        self.assertIn(b"cadgen " + version.encode(), self.xbf.read_bytes()[:4096])

    def test_a_comment_changes_no_module_and_a_code_edit_names_its_module(self) -> None:
        self.plate()
        before = dict(map(tuple, previous.of(self.xbf)["modules"]))
        # A comment, and an edit to a function the model does not reach: nothing it is made of.
        self.helper(comment=", in millimetres", unused=2)
        self.assertEqual(self.plate()["cache"], {"used": True, "from": "file"})
        self.helper(width=24)
        report = self.plate()
        self.assertEqual(report["cache"]["changed"], ["../dims.py: WIDTH changed"])
        after = dict(map(tuple, previous.of(self.xbf)["modules"]))
        self.assertEqual({path for path in before if before[path] != after[path]}, {"../dims.py"})

    def test_an_input_edit_names_its_file_and_a_missing_one_builds_cleanly(self) -> None:
        self.plate()
        (self.folder / "depth.json").write_text(json.dumps({"depth": 7}), encoding="utf-8")
        self.assertEqual(self.plate()["cache"]["changed"], ["../depth.json changed"])
        (self.folder / "depth.json").unlink()
        report = self.plate()
        self.assertEqual(report["cache"]["changed"], ["../depth.json is missing"])
        self.assertTrue(report["files"][str(self.xbf)]["written"])
        # Found missing is an input too: the next restart takes the file.
        self.assertEqual(previous.of(self.xbf)["inputs"][0][2], None)
        self.assertEqual(self.plate()["cache"], {"used": True, "from": "file"})

    def test_a_commit_is_nothing_to_the_engine_and_a_no_op_after_one_writes_nothing(self) -> None:
        import subprocess
        from unittest import mock

        git = ["git", "-C", str(self.folder), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "fixture"]):
            subprocess.run([*git, *args], check=True, capture_output=True)
        asked = []
        run, popen = subprocess.run, subprocess.Popen

        def watched(real):
            def call(args, *rest, **options):
                if isinstance(args, (list, tuple)) and args and Path(str(args[0])).name.startswith("git"):
                    asked.append(args)
                return real(args, *rest, **options)
            return call

        def watching():
            return mock.patch.multiple(subprocess, run=watched(run), Popen=watched(popen))

        with watching():
            self.plate()
        self.assertNotIn("commit", previous.of(self.xbf)["source"])
        written = self.xbf.read_bytes(), self.xbf.stat().st_mtime_ns
        (self.folder / "notes.txt").write_text("x", encoding="utf-8")
        for args in (["add", "-A"], ["commit", "-q", "-m", "notes"]):
            subprocess.run([*git, *args], check=True, capture_output=True)
        with watching():
            report = self.plate()
        self.assertEqual(asked, [], "the engine calls no git")
        # The no-op after a commit: taken from the file, nothing written, the same bytes.
        self.assertEqual(report["cache"], {"used": True, "from": "file"})
        self.assertFalse(report["files"][str(self.xbf)]["written"])
        self.assertEqual((self.xbf.read_bytes(), self.xbf.stat().st_mtime_ns), written)

    def test_the_key_is_the_formats_not_the_release_the_engine_digest_or_numpy(self) -> None:
        self.plate()
        record = previous.of(self.xbf)
        other = json.loads(json.dumps(record))
        other["engine"] = {**other["engine"], "release": "cadgen 99.0.0", "digest": "0" * 32}
        other["libs"] = {**other["libs"], "numpy": "0.1"}
        self.assertEqual(previous.key(other), record["key"])
        other["engine"]["format"] = "xbf/1"
        self.assertNotEqual(previous.key(other), record["key"], "the format is keyed")

    def test_ocp_without_vtk_is_the_ocp_recorded(self) -> None:
        from importlib import metadata
        from unittest import mock

        def version(name: str) -> str:
            # An install with OCP's no-VTK distribution and not the other.
            if name in ("build123d", "cadquery-ocp-novtk"):
                return {"cadquery-ocp-novtk": "7.9.3.1"}.get(name, "1.0")
            raise metadata.PackageNotFoundError(name)

        previous._libraries.cache_clear()
        self.addCleanup(previous._libraries.cache_clear)
        with mock.patch.object(metadata, "version", version):
            self.assertEqual(previous._libraries(), {"build123d": "1.0", "OCP": "7.9.3.1"})


if __name__ == "__main__":
    unittest.main()
