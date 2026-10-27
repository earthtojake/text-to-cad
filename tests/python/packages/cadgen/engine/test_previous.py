"""A model's previous document is the engine's cache of it, or this worker's own record: a restart
with nothing changed runs no body, and its declared files are exports of the document taken --
compared, and written only where they differ or are missing; anything else builds, and writes the
cold build's bytes. The key alone decides: a declared file plays no part."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from typing import Any

from cadgen.engine import build as engine_build
from cadgen.engine import document, previous
from cadgen.engine.ids import model_id


def keep(script: Path, name: str, cache: Path) -> Path:
    """What the daemon's idle save writes (``cache``): the document of model ``name`` this process
    holds, as ``worker._save`` answers it, at its file in the cache's ``documents/`` folder."""
    from cadgen.engine import worker

    header, payload = worker._save({"ident": "-", "script": str(script), "name": name, "generation": "g"})
    assert not header.get("error"), header
    path = cache / model_id(script, name) / "document.xbf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path

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
        self.cache = self.folder / "cache" / "documents"
        self.cached = self.cache / model_id(self.script, "kit") / "document.xbf"
        (self.folder / "inputs").mkdir()
        bd.export_step(bd.Cylinder(3, 4), str(self.folder / "inputs" / "cap.step"))
        (self.folder / "peg.json").write_text(json.dumps({"size": 4}), encoding="utf-8")
        (self.folder / "kit.json").write_text(json.dumps({"thickness": 2}), encoding="utf-8")
        self.restart()
        self.addCleanup(self.restart)
        memo.install()

    def restart(self, saved: bool = True) -> None:
        """What a new worker holds: nothing; and the engine's cache, the kit's document as the
        worker held it (``saved``: its idle save, before the worker went)."""
        from cadgen.engine.kernel import memo

        if saved and engine_build.held(self.script, "kit") is not None:
            keep(self.script, "kit", self.cache)
        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        engine_build._BUILT.clear()

    def source(self, peg: float = 10, plate: float = 40) -> None:
        self.script.write_text(textwrap.dedent(KIT.format(peg=peg, plate=plate)), encoding="utf-8")
        os.utime(self.script, ns=(time.time_ns(), time.time_ns()))

    def kit(self, said: list | None = None) -> dict:
        """The kit built, what the build logs (the files it wrote or kept) appended to ``said``."""
        (report,) = engine_build.build(self.script, ["kit"], cwd=self.folder, cache=str(self.cache),
                                       log=said.append if said is not None else lambda _line: None)
        self.assertTrue(report["ok"], report)
        return report

    def cold(self, **values) -> bytes:
        """The kit as a process that never built it, with no file and nothing cached, builds it."""
        self.restart(saved=False)
        self.xbf.unlink(missing_ok=True)
        self.cached.unlink(missing_ok=True)
        self.source(**values)
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "the engine's cache holds none of it")
        return self.xbf.read_bytes()

    def test_a_restart_with_nothing_changed_runs_no_body_and_writes_nothing(self) -> None:
        first = self.cold()
        written = self.xbf.stat().st_mtime_ns
        self.restart()
        said: list[str] = []
        report = self.kit(said)
        self.assertEqual(report["cache"], {"used": True, "from": "cache"})
        self.assertEqual(report["memo"]["bodies_run"], 0)
        self.assertEqual(report["memo"]["bodies_loaded"], 3, "kit, peg and cap")
        self.assertEqual(report["bodies"], {"kit.py::kit": "loaded"})
        self.assertEqual([row["written"] for row in report["files"].values()], [False])
        self.assertEqual(self.xbf.read_bytes(), first)
        self.assertEqual(self.xbf.stat().st_mtime_ns, written)
        # The next build in the same worker: the key it took, in memory, and no read.
        again = self.kit(said)
        self.assertEqual(again["cache"], {"used": True, "from": "memory"})
        self.assertNotIn("read", again["timings"])
        self.assertEqual(self.xbf.stat().st_mtime_ns, written)
        self.assertEqual(said, [], "a take is said by its run line alone: it wrote and logged nothing")
        self.assertEqual(self.cached.read_bytes(), first, "the cache holds the bytes the declared xbf has")

    def test_another_process_takes_the_file_whatever_its_hash_seed(self) -> None:
        import subprocess
        import sys

        self.source()
        code = ("import json, sys; from pathlib import Path; from cadgen.engine import build; "
                "from tests.python.packages.cadgen.engine.test_previous import keep; "
                "script, cache = Path(sys.argv[1]), Path(sys.argv[2]); "
                "report = build.build(script, ['kit'], cwd=script.parent, cache=str(cache))[0]; "
                "keep(script, 'kit', cache); print(json.dumps(report))")
        found = []
        for seed in ("1", "2"):
            done = subprocess.run([sys.executable, "-c", code, str(self.script), str(self.cache)], capture_output=True,
                                  text=True, env={**os.environ, "PYTHONHASHSEED": seed},
                                  cwd=Path(__file__).resolve().parents[5])
            self.assertEqual(done.returncode, 0, done.stderr)
            found.append(json.loads(done.stdout.strip().splitlines()[-1]))
        self.assertEqual(found[0]["cache"]["reason"], "the engine's cache holds none of it")
        self.assertEqual(found[1]["cache"], {"used": True, "from": "cache"})

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

    def test_a_declared_file_touched_or_deleted_is_written_again_from_the_document_and_nothing_runs(self) -> None:
        first = self.cold()
        later = self.xbf.stat().st_mtime_ns + 1_000_000_000
        os.utime(self.xbf, ns=(later, later))
        report = self.kit()
        self.assertEqual((report["cache"], report["bodies"]), ({"used": True, "from": "memory"}, {"kit.py::kit": "loaded"}),
                         "the key alone decides: a declared file plays no part")
        self.assertFalse(report["files"][str(self.xbf)]["written"], "compared: the same bytes, left as they are")
        self.assertEqual((self.xbf.read_bytes(), self.xbf.stat().st_mtime_ns), (first, later))
        self.xbf.unlink()
        report = self.kit()
        self.assertEqual((report["cache"], report["memo"]["bodies_run"]), ({"used": True, "from": "memory"}, 0))
        self.assertTrue(report["files"][str(self.xbf)]["written"])
        self.assertEqual(self.xbf.read_bytes(), first, "written again from the document, the cold bytes")
        # After a restart too: the document the cache holds writes it, and no body runs.
        self.restart()
        self.xbf.write_bytes(b"edited by hand")
        report = self.kit()
        self.assertEqual((report["cache"], report["memo"]["bodies_run"]), ({"used": True, "from": "cache"}, 0))
        self.assertTrue(report["files"][str(self.xbf)]["written"])
        self.assertEqual(self.xbf.read_bytes(), first)

    def test_a_child_models_declared_file_is_its_own_models_to_write(self) -> None:
        self.cold()
        peg = self.folder / "XBF/peg.xbf"
        written = peg.read_bytes()
        peg.unlink()
        report = self.kit()
        self.assertEqual(report["cache"], {"used": True, "from": "memory"}, "the parent is taken: no child runs")
        self.assertFalse(peg.exists(), "nothing ran peg: its file is written when its own model is")
        self.source(plate=44)  # an edit that runs the kit runs peg, its child, which writes its file
        self.kit()
        self.assertEqual(peg.read_bytes(), written)

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

    def test_a_cache_another_program_wrote_is_built_again_and_a_declared_file_is_never_read(self) -> None:
        first = self.cold()
        writer = document._writer().encode()
        self.restart()
        self.cached.write_bytes(self.cached.read_bytes().replace(writer, writer.replace(b"(cadgen ", b"(cadgem ")))
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], "its cache was written by another program")
        self.assertFalse(report["files"][str(self.xbf)]["written"], "built again: the same bytes")
        # The declared xbf is an export, never a source: another program's in its place is written over.
        self.restart()
        self.xbf.write_bytes(first.replace(writer, writer.replace(b"(cadgen ", b"(cadgem ")))
        report = self.kit()
        self.assertEqual(report["cache"], {"used": True, "from": "cache"})
        self.assertEqual(self.xbf.read_bytes(), first)

    def test_the_writers_release_is_information_and_another_format_builds_once(self) -> None:
        self.cold()
        writer = document._writer().encode()
        release = previous.version().encode()
        # Another cadgen release in the writer's words: information, as in the closure; the file
        # is taken.
        other_release = writer.replace(b"(cadgen " + release, b"(cadgen " + b"9" * len(release))
        self.restart()
        self.cached.write_bytes(self.cached.read_bytes().replace(writer, other_release))
        self.assertEqual(self.kit()["cache"], {"used": True, "from": "cache"})
        # A document of the format before (the key made differently): built again, once.
        old = other_release.replace(f"cadgen.engine {previous.FORMAT} ".encode(), b"cadgen.engine xbf/1 ")
        self.assertEqual(len(old), len(other_release))
        self.restart(saved=False)
        self.cached.write_bytes(self.cached.read_bytes().replace(other_release, old))
        report = self.kit()
        self.assertEqual(report["cache"]["reason"], f"its cache was written by {old.decode()}")
        self.restart()
        self.assertEqual(self.kit()["cache"], {"used": True, "from": "cache"}, "built once, then current")

    def test_a_missing_or_broken_cache_file_builds(self) -> None:
        first = self.cold()
        self.restart()
        self.cached.unlink()
        self.assertEqual(self.kit()["cache"]["reason"], "the engine's cache holds none of it")
        self.assertEqual(self.xbf.read_bytes(), first)
        # Its head whole, the rest gone: the closure shows, the document does not read. (Cut
        # right after the closure, in the main label's attributes: OCCT's reader aborts the
        # process on some cuts of a shape section rather than failing, an uncaught
        # Standard_NullObject -- measured at a half of this one, and at a third once the
        # closure grew by its symbols.)
        head = first[: first.index(b"\x00", first.index(b'{"schema":' + json.dumps(previous.SCHEMA).encode())) + 1]
        self.restart()
        self.cached.write_bytes(head)
        report = self.kit()
        self.assertTrue(report["cache"]["reason"].startswith("its cache does not read"), report["cache"])
        self.assertTrue(report["cache"]["unreadable"], "the daemon drops it, and caches the build again")
        self.assertEqual(self.xbf.read_bytes(), first)

    def export(self, name: str) -> bytes:
        """The kit's STEP as ``cadgen export`` writes it, in a process of its own, through an engine
        of the test's own -- its folders, no port of its own choosing -- stopped once the test ends:
        never the developer's engine, state or cache, however the file is run."""
        import subprocess
        import sys

        if not hasattr(self, "engine_env"):
            engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
            self.addCleanup(shutil.rmtree, engine, True)
            self.engine_env = {**os.environ, "CADGEN_ENGINE_DIR": str(engine), "CADGEN_STATE_DIR": str(engine / "state"),
                               "CADGEN_CACHE_DIR": str(engine / "cache"), "CADGEN_ENGINE_PORT": "0",
                               "CADGEN_ENGINE_STANDBY": "0"}
            self.addCleanup(subprocess.run, [sys.executable, "-m", "cadgen.engine", "stop"], env=self.engine_env,
                            capture_output=True)
        out = self.folder / name
        done = subprocess.run([sys.executable, "-m", "cadgen.engine", "export", str(self.xbf), str(out)],
                              cwd=self.folder, capture_output=True, text=True, env=self.engine_env)
        self.assertEqual(done.returncode, 0, done.stderr)
        # The STEP header's time stamp is the second it was written: masked.
        return re.sub(rb"'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d'", b"'T'", out.read_bytes(), count=1)

    def test_a_taken_document_serves_and_exports_as_the_cold_one(self) -> None:
        from cadgen.engine.ids import model_id

        self.cold()
        structure = document.Loaded(self.xbf).structure()
        built = document.Loaded(self.xbf).prototypes[0].key
        self.assertIsNotNone(engine_build.made_by(model_id(self.script, "kit"), built, "face", 1),
                             "the process that built it names what made its elements")
        step = self.export("cold.step")
        self.restart()
        self.assertTrue(self.kit()["cache"]["used"])
        again = document.Loaded(self.xbf)
        self.assertEqual(json.loads(json.dumps(again.structure())), json.loads(json.dumps(structure)))
        self.assertEqual(self.export("taken.step"), step)
        # Provenance is the worker's that built it: a taken document has none to give.
        key = again.prototypes[0].key
        self.assertIsNone(engine_build.made_by(model_id(self.script, "kit"), key, "face", 1))


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
        self.cache = self.folder / "cache" / "documents"
        self.script.write_text(textwrap.dedent(PLATE), encoding="utf-8")
        self.helper()
        (self.folder / "depth.json").write_text(json.dumps({"depth": 6}), encoding="utf-8")
        self.restart()
        self.addCleanup(self.restart)
        memo.install()

    def restart(self) -> None:
        """A new worker: nothing held but what the engine's cache kept of the plate."""
        from cadgen.engine.kernel import memo

        if engine_build.held(self.script, "plate") is not None:
            keep(self.script, "plate", self.cache)
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
        (report,) = engine_build.build(self.script, ["plate"], cwd=self.folder, cache=str(self.cache))
        self.assertTrue(report["ok"], report)
        return report

    def test_the_closure_round_trips_every_field(self) -> None:
        from cadgen.engine import api

        self.plate()
        record = previous.of(self.xbf)
        self.assertEqual(list(record), ["schema", "engine", "libs", "platform", "source", "modules", "symbols",
                                        "inputs", "bodies", "key"])
        self.assertEqual(record["schema"], "cadgen.engine closure/2")
        version = (Path(__file__).resolve().parents[5] / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(record["engine"]["release"], f"cadgen {version}", "the release VERSION stamps")
        self.assertEqual((record["engine"]["format"], len(record["engine"]["digest"])), ("xbf/9", 32))
        self.assertEqual(set(record["libs"]), {"build123d", "OCP", "bd_materials", "threejs_materials"})
        self.assertEqual(record["platform"], {"python": platform.python_version(), "system": platform.system(),
                                              "arch": platform.machine()}, "the Python and the machine it ran on")
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
        self.assertEqual(self.plate()["cache"], {"used": True, "from": "cache"})
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
        self.assertEqual(self.plate()["cache"], {"used": True, "from": "cache"})

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
        # The no-op after a commit: taken from the cache, nothing written, the same bytes.
        self.assertEqual(report["cache"], {"used": True, "from": "cache"})
        self.assertFalse(report["files"][str(self.xbf)]["written"])
        self.assertEqual((self.xbf.read_bytes(), self.xbf.stat().st_mtime_ns), written)

    def test_the_key_covers_format_libs_system_arch_and_code_but_not_release_or_python(self) -> None:
        self.plate()
        record = previous.of(self.xbf)

        def copy(**fields: dict) -> dict:
            other = json.loads(json.dumps(record))
            for name, values in fields.items():
                other[name] = {**other[name], **values}
            return other

        self.assertEqual(previous.key(copy(engine={"digest": "0" * 32}, libs={"numpy": "0.1"})), record["key"],
                         "the engine's code digest and numpy are information")
        # Two closures that differ in the architecture alone: an x86-64 kernel writes other bytes.
        arm, intel = copy(platform={"arch": "arm64"}), copy(platform={"arch": "x86_64"})
        self.assertNotEqual(previous.key(arm), previous.key(intel))
        for name, values in (("engine", {"release": "cadgen 99.0.0"}), ("platform", {"python": "3.99.0"})):
            self.assertEqual(previous.key(copy(**{name: values})), record["key"], f"{name} {values} is recorded only")
        for name, values in (("engine", {"format": "xbf/1"}), ("libs", {"build123d": "0.0.1"}),
                             ("libs", {"OCP": "7.0.0"}),
                             ("libs", {"bd_materials": "0.0.1"}), ("libs", {"threejs_materials": "0.0.1"}),
                             ("platform", {"system": "Plan 9"})):
            self.assertNotEqual(previous.key(copy(**{name: values})), record["key"], f"{name} {values} is keyed")
        # The same closure on the same toolchain is the same key, made again anywhere.
        self.assertEqual(previous.key(json.loads(previous.text(record))), record["key"])
        self.assertEqual(previous.key(copy(platform=previous._platform(), engine=previous._engine())), record["key"])

    def test_another_release_or_python_takes_the_document_without_a_rebuild_reason(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        self.plate()
        record = previous.of(self.xbf)
        for field, value in (("engine", {**previous._engine(), "release": "cadgen 99.0.0"}),
                             ("platform", {**previous._platform(), "python": "3.99.0"})):
            with self.subTest(field=field), mock.patch.object(previous, f"_{field}", lambda: value):
                report = self.plate()
                key, changes = previous.again(record, SimpleNamespace(script=self.script, name="plate"),
                                              self.xbf.parent, {previous.absolute(path, self.xbf.parent): digest
                                                                for path, digest in record["modules"]})
            self.assertEqual((report["cache"], report["memo"]["bodies_run"]),
                             ({"used": True, "from": "cache"}, 0))
            self.assertEqual((key, changes), (record["key"], []))
            self.assertEqual(previous.of(self.xbf), record, "the taken document keeps its recorded toolchain")

    def test_another_system_or_architecture_builds_and_says_so(self) -> None:
        from unittest import mock

        self.plate()
        here = previous._platform()
        there = {**here, "python": "3.99.0", "system": "Plan 9",
                 "arch": "x86_64" if here["arch"] != "x86_64" else "arm64"}
        with mock.patch.object(previous, "_platform", lambda: there):
            report = self.plate()
        self.assertEqual(report["cache"]["changed"], [f"{here['system']} became Plan 9",
                                                      f"{here['arch']} became {there['arch']}"])
        self.assertEqual(previous.of(self.xbf)["platform"], there, "the closure names what it was built with")

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




# Models with no file: each body says it ran in a log it appends to (written, so never one of its
# inputs), and reads a file itself; the plate reads a STEP through the engine and calls the peg.
WARM = """
import json
from pathlib import Path

import build123d as bd
from cadgen.engine import model, read_step

import dims

HERE = Path(__file__).resolve().parent


def ran(name):
    with open(HERE / "ran.log", "a", encoding="utf-8") as handle:
        handle.write(name + "\\n")


@model
def peg():
    ran("peg")
    peg = bd.Cylinder(dims.RADIUS, json.loads((HERE / "peg.json").read_text())["height"])
    peg.label = "{peg}"
    return peg


@model
def plate():
    ran("plate")
    plate = bd.Box({width}, json.loads((HERE / "plate.json").read_text())["depth"], 2)
    plate.label = "plate"
    cap = read_step(HERE / "cap.step")
    return bd.Compound(children=[plate, peg().shape.moved(bd.Pos(0, 0, 6)), cap.moved(bd.Pos(10, 0, 8))],
                       label="plate")
"""


class WarmModelTest(unittest.TestCase):
    """A model with no file built in this worker: an unchanged warm build takes its document from
    memory by its key and runs no body, as one with an xbf does; a change to anything the key
    covers -- the script, a module it imports, a file a body reads itself or through the engine, a
    child model's code or its reads -- runs what it reaches again."""

    def setUp(self) -> None:
        import build123d as bd

        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-warm-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "plate.py"
        self.source()
        self.write("dims.py", "RADIUS = 2\n")
        self.write("peg.json", json.dumps({"height": 10}))
        self.write("plate.json", json.dumps({"depth": 6}))
        bd.export_step(bd.Cylinder(3, 4), str(self.folder / "cap.step"))
        self.restart()
        self.addCleanup(self.restart)
        memo.install()

    def restart(self) -> None:
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        engine_build._BUILT.clear()

    def write(self, name: str, text: str) -> None:
        path = self.folder / name
        path.write_text(text, encoding="utf-8")
        os.utime(path, ns=(time.time_ns(), time.time_ns()))

    def source(self, width: float = 40, peg: str = "peg") -> None:
        self.write("plate.py", textwrap.dedent(WARM.format(width=width, peg=peg)))

    def build(self, name: str = "plate") -> dict:
        (report,) = engine_build.build(self.script, [name], cwd=self.folder)
        self.assertTrue(report["ok"], report)
        return report

    def ran(self) -> list[str]:
        """The bodies that ran since the last call, in order."""
        log = self.folder / "ran.log"
        found = log.read_text(encoding="utf-8").split() if log.exists() else []
        log.unlink(missing_ok=True)
        return found

    def test_an_unchanged_warm_build_takes_its_document_and_runs_no_body(self) -> None:
        self.build()
        self.assertEqual(self.ran(), ["plate", "peg"])
        for _ in range(2):
            report = self.build()
            self.assertEqual((report["cache"], report["bodies"], self.ran()),
                             ({"used": True, "from": "memory"}, {"plate.py::plate": "loaded"}, []))
            self.assertEqual((report["memo"]["bodies_run"], report["memo"]["bodies_skipped"],
                              report["memo"]["bodies_loaded"]), (0, 0, 2))
            self.assertEqual(report["files"], {})
        # The child, built in the plate's run, is taken alike.
        self.assertEqual((self.build("peg")["cache"], self.ran()), ({"used": True, "from": "memory"}, []))

    def test_a_change_to_anything_its_key_covers_runs_what_it_reaches(self) -> None:
        import build123d as bd

        self.build()
        self.ran()
        changes = (
            ("the script", lambda: self.source(width=44), "plate.py: plate changed", ["plate"]),
            ("a module it imports", lambda: self.write("dims.py", "RADIUS = 3\n"), "dims.py: RADIUS changed",
             ["plate", "peg"]),
            ("a file the body reads", lambda: self.write("plate.json", json.dumps({"depth": 7})),
             "plate.json changed", ["plate"]),
            ("a file read through the engine", lambda: bd.export_step(bd.Cylinder(3, 5), str(self.folder / "cap.step")),
             "cap.step changed", ["plate"]),
            ("a child model's code", lambda: self.source(width=44, peg="pin"), "plate.py: peg changed",
             ["plate", "peg"]),
            ("a file the child reads", lambda: self.write("peg.json", json.dumps({"height": 12})), "peg.json changed",
             ["plate", "peg"]),
        )
        for what, change, said, ran in changes:
            change()
            report = self.build()
            self.assertEqual((report["cache"]["changed"], self.ran()), ([said], ran), what)
            again = self.build()
            self.assertEqual((again["cache"], self.ran()), ({"used": True, "from": "memory"}, []), what)
        # What the last build made, taken: the cold build of the same code makes it too.
        held = engine_build.held(self.script, "plate").structure
        self.restart()
        self.build()
        self.assertEqual(json.loads(json.dumps(engine_build.held(self.script, "plate").structure)),
                         json.loads(json.dumps(held)))


# A script whose module reads its environment as it is imported.
ENVIRONED = """
import os

import build123d as bd
from cadgen.engine import xbf

WIDTH = float(os.environ.get("ENGINE_TEST_WIDTH", "10"))


@xbf("XBF/strip.xbf")
def strip():
    return bd.Box(WIDTH, 4, 1)
"""


class LoadTest(unittest.TestCase):
    """One run's calls of a script are served from one load of it (``build._Load``) only while
    what the load read stands: its files, and the environment it ran in."""

    def setUp(self) -> None:
        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-load-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.script = self.folder / "strip.py"
        self.script.write_text(textwrap.dedent(ENVIRONED), encoding="utf-8")
        self.restart()
        self.addCleanup(self.restart)
        memo.install()

    def restart(self) -> None:
        from cadgen.engine.kernel import memo

        memo.clear()
        engine_build._WRITTEN.clear()
        engine_build._PARTS.clear()
        engine_build._BUILT.clear()
        engine_build._LOAD.clear()

    def strip(self, width: str) -> dict:
        """One call of the run's: ``strip`` built with the environment saying ``width``."""
        from unittest import mock

        with mock.patch.dict(os.environ, {"ENGINE_TEST_WIDTH": width}):
            (report,) = engine_build.build(self.script, ["strip"], cwd=self.folder, run="one run")
        self.assertTrue(report["ok"], report)
        return report

    def test_a_call_in_another_environment_loads_the_script_again(self) -> None:
        self.assertEqual(self.strip("10")["facts"]["bounds"], [10.0, 4.0, 1.0])
        self.assertEqual(self.strip("10")["cache"], {"used": True, "from": "memory"}, "taken: its load is kept")
        # The program changed its environment between two calls: the import reads another width.
        report = self.strip("20")
        self.assertEqual(report["cache"]["changed"], ["../strip.py: WIDTH changed"])
        self.assertEqual(report["facts"]["bounds"], [20.0, 4.0, 1.0])


if __name__ == "__main__":
    unittest.main()
