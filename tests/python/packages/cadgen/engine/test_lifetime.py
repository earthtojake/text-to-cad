"""Document lifetime: a document outlives its worker (drained before the worker goes), everything
the daemon holds lives under one memory budget -- files the engine reads again itself evicted
before every other document, least recently used first, a watched document never -- the system's
memory-pressure signal evicts down to the low-water mark, and a document no longer held names the
command that builds it again, which nothing runs."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine.ids import model_id  # noqa: E402
from cadgen.engine.serve import LOW_WATER, Server  # noqa: E402

MIB = 1 << 20


def await_(condition, what: str, seconds: float = 60.0):
    deadline = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)


def _document(name: str) -> dict:
    return {"name": name, "version": "1-0", "prototypes": [{"key": f"{name}-key", "name": name}],
            "instances": [], "tree": {"name": name}}


class BudgetTest(unittest.TestCase):
    """The budget over a server's documents and tessellations, its tiers, and the pressure signal."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-lifetime-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.server = Server(port=0, mesh_mode="inline", budget=64 * MIB)
        self.addCleanup(self.server.stop)

    def file(self, name: str, size: int) -> str:
        """A document of a file on disk (one the engine could read again), ``size`` MiB of shape bytes."""
        path = self.folder / f"{name}.xbf"
        path.write_bytes(b"")
        return self.server.put(path, _document(name), {f"{name}-key": b"f" * (size * MIB)})

    def model(self, name: str, size: int) -> str:
        """A model's document (its id: nothing on disk reads it back), ``size`` MiB of shape bytes."""
        return self.server.put(model_id(self.folder / f"{name}.py", name), _document(name),
                               {f"{name}-key": b"m" * (size * MIB)})

    def test_files_go_before_other_documents_least_recently_used_first_and_a_watched_one_never(self) -> None:
        server = self.server
        server.cache.put("mesh", b"x" * (4 * MIB))
        older = self.model("older", 20)
        first = self.file("first", 20)
        newer = self.model("newer", 16)
        self.assertEqual(len(server.served), 3, "under the budget nothing goes")
        second = self.file("second", 20)  # 80 MiB: past the budget, trimmed to 80 % of it
        self.assertNotIn("mesh", server.cache.items, "a tessellation goes first: it is remade from the shape")
        self.assertEqual(set(server.served), {newer, second},
                         "the other file first, then the least recently used model; the document put stays")
        self.assertLessEqual(server.holding(), int(64 * MIB * 0.8))
        self.assertNotIn(older, server.served)
        self.assertNotIn(first, server.served)
        server.sync(newer)  # a page watches it
        third = self.model("third", 30)
        self.assertEqual(set(server.served), {newer, third}, "the file goes before any model")
        fourth = self.model("fourth", 30)
        self.assertEqual(set(server.served), {newer, fourth}, "a watched document is never evicted")
        self.assertEqual(server.memory()["evictions"], 4)

    def test_a_pressure_signal_evicts_down_to_the_low_water_mark(self) -> None:
        server = self.server
        server.start()
        watched = self.model("watched", 10)
        for name in ("a", "b", "c", "d", "e"):
            self.model(name, 10)
        self.assertEqual(len(server.served), 6, "60 MiB: under the budget")
        server.sync(watched)
        server.pressure.simulate(True)
        await_(lambda: server.holding() <= int(64 * MIB * LOW_WATER), "the low-water mark")
        server.pressure.simulate(None)
        self.assertIn(watched, server.served, "pressure never evicts a watched document either")
        self.assertGreater(server.holding(), int(64 * MIB * LOW_WATER) - 10 * MIB, "no further than the mark")

    def test_an_evicted_file_is_read_again_under_its_id(self) -> None:
        from cadgen.engine import build as engine_build

        script = self.folder / "plate.py"
        script.write_text(textwrap.dedent("""
            import build123d as bd
            from cadgen.engine import xbf


            @xbf("XBF/plate.xbf")
            def plate():
                return bd.Box(4, 3, 1)
        """), encoding="utf-8")
        self.assertTrue(engine_build.build(script, ["plate"], cwd=self.folder)[-1]["ok"])
        ident = self.server.add(self.folder / "XBF/plate.xbf")
        version = self.server.document(ident).version
        self.assertEqual(self.server.trim(0), [ident])
        self.assertNotIn(ident, self.server.served)
        self.assertTrue(self.server.holds(ident), "known by its id still")
        self.assertEqual(self.server.document(ident).version, version, "read again from its file, the same document")
        self.assertIn(ident, self.server.served)


    def test_a_held_documents_xbf_bytes_count_against_the_budget_and_go_with_it(self) -> None:
        ident = model_id(self.folder / "lid.py", "lid")
        self.server.keep(ident, _document("lid"), {"lid-key": b"m" * MIB}, 1, b"x" * 1000)
        bare = self.server.served[ident].size
        # Its animations' record is in the xbf bytes: a longer document is counted whole, again.
        self.server.keep(ident, _document("lid"), {"lid-key": b"m" * MIB}, 2, b"x" * 1500)
        self.assertEqual(self.server.served[ident].size, bare + 500)
        self.assertEqual(self.server.holding(), self.server.served[ident].size)
        self.assertEqual(self.server.trim(0), [ident])
        self.assertEqual(self.server.holding(), 0, "evicted, its xbf bytes go with it")


class NotHeldRefusalTest(unittest.TestCase):
    """An id the daemon does not hold is refused as ``NotHeld``, its state and rebuild with it."""

    def test_the_refusal_crosses_the_daemon_as_its_type(self) -> None:
        from cadgen.engine import api, daemon
        from cadgen.engine.serve import NotHeld

        engine = daemon.Daemon(60)
        self.addCleanup(engine.pool.stop)
        ident = model_id(Path("/nowhere/cell.py"), "cell")
        engine.models.expired[ident] = {"id": ident, "source": {"script": "/nowhere/cell.py", "name": "cell"},
                                        "program": "/nowhere/caller.py", "store": "memory", "version": 1, "builtAt": 0}
        answers: list[dict] = []
        engine.handle({"op": "document", "id": ident}, answers.append)
        (answer,) = answers
        self.assertEqual((answer["state"], answer["rebuild"]), ("expired", "python /nowhere/caller.py"))
        error = api._failed(answer)
        self.assertIsInstance(error, NotHeld, "raised as its type: the CLI exits 2 for a ValueError")
        self.assertEqual((error.state, error.rebuild, str(error)), ("expired", "python /nowhere/caller.py", answer["failed"]))
        answers.clear()
        engine.handle({"op": "document", "id": model_id(Path("/nowhere/other.py"), "other")}, answers.append)
        self.assertIsInstance(api._failed(answers[0]), NotHeld, "an id it never built is refused the same")


class StatusTextTest(unittest.TestCase):
    def test_the_serving_line_counts_what_was_opened_beside_the_documents_held(self) -> None:
        from cadgen.engine.cli import status_text

        live = [{"id": f"id-{n}", "name": f"part{n}", "state": "live"} for n in range(6)]
        text = status_text({"pid": 1, "up": 5, "cap": 4, "idleTimeout": 60, "workers": [], "models": live,
                            "serving": {"url": "http://127.0.0.1:1", "documents": [
                                {"id": "f", "path": "/a.xbf", "state": "evicted", "bytes": 0}]}})
        lines = text.splitlines()
        self.assertIn("serving http://127.0.0.1:1: 0 documents opened by a page or a command", lines)
        self.assertEqual(sum(line.startswith("  live") for line in lines), 6, "the documents held, listed apart")

    def test_a_shape_handed_over_is_worded_as_one_with_no_script_to_rerun(self) -> None:
        from cadgen.engine.cli import status_text

        text = status_text({"pid": 1, "up": 5, "cap": 4, "idleTimeout": 60, "workers": [], "models": [
            {"id": "id-1", "name": "plate", "state": "evicted", "store": "shape"}]})
        self.assertIn("  evicted   plate  id-1  a shape handed over: no script to rerun", text.splitlines())


SCRIPT = """
import pathlib
import build123d as bd
from cadgen.engine import model

pathlib.Path(__file__).with_suffix(".ran").write_text("ran", encoding="utf-8")


@model{store}
def {name}():
    return bd.Box(3, 2, 1)
"""

HINGE = """
import pathlib
import build123d as bd
from cadgen.ap242 import mechanism_state
from cadgen.engine import model

pathlib.Path(__file__).with_suffix(".ran").write_text("ran", encoding="utf-8")


@model
def {name}():
    base = bd.Box(100, 60, 20)
    base.label = "base"
    arm = bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
    arm.label = "arm"
    bd.RevoluteJoint("elbow", base, axis=bd.Axis((40, 0, 20), (0, 1, 0)), angular_range=(-10, 120))
    bd.RigidJoint("mount", arm, bd.Location())
    base.joints["elbow"].connect_to(arm.joints["mount"], angle=30)
    root = bd.Compound(children=[base, arm], label="hinge")
    mechanism_state(root, "raised", elbow=90)
    return root
"""

# The hinge with a configuration sequence (the document's) and an animation (the GLB's, recorded in
# the xbf), its GLB declared: the build writes it live, the export of its hold writes it again.
ANIMATED = HINGE.replace("from cadgen.engine import model", """from cadgen.ap242 import configuration_sequence
from cadgen.engine import glb
from cadgen.gltf import animation""").replace("@model", '@glb("live.glb")').replace("    return root", """\
    configuration_sequence(root, "lift", [(0, {{"elbow": 30}}), (1, "raised")])
    show = animation(root, "show", duration=2)
    show.pose(at={{0: {{}}, 1: "raised", 2: {{}}}})
    show.translation("base", by=(0, 0, -15)).hide("arm", at=2)
    return root""")

CALLER = """
import {name}

{name}.{name}()
"""

PART = """
import build123d as bd
from cadgen.engine import model


@model
def plate():
    return bd.Box(4, 3, 1)
"""

ASSEMBLY = """
import build123d as bd
from cadgen.engine import model
from part import plate


@model
def assembly():
    return bd.Compound(children=[plate().shape, plate().shape.moved(bd.Pos(10, 0, 0))], label="assembly")


if __name__ == "__main__":
    assembly()
"""


def get(url: str, token: str) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class LifetimeDaemonTest(unittest.TestCase):
    """Through a daemon, its workers real processes retired after a second idle."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-lifetime-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CADGEN_ENGINE_DIR": str(self.state),
                                          "CADGEN_ENGINE_IDLE": "120", "CADGEN_ENGINE_MESH": "inline",
                                          "CADGEN_ENGINE_WORKER_IDLE": "1"}, self.addCleanup)
        # This process asks the test's daemon (``status``, ``export``), never starting one.
        self.enterContext(mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(self.state)}))
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        engine_daemon.run([sys.executable, "-m", "cadgen.engine", "stop"], cwd=self.folder, env=self.env)
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def ask(self, message: dict) -> dict:
        from cadgen.engine.client import request

        return request(message, start=False) or {}

    def row(self, ident: str, state: str | None = None) -> dict:
        """The status row of document ``ident``; with ``state``, once it is in that state."""
        def found() -> dict:
            return next((row for row in self.ask({"op": "status"}).get("models") or [] if row["id"] == ident), {})

        return await_(lambda: (lambda row: row if row.get("state") == state else None)(found()),
                      f"{ident} {state}") if state else found()

    def built(self, name: str, store: str = "", env: dict | None = None, script: str = SCRIPT) -> str:
        """``python caller_NAME.py`` builds model ``name`` of ``NAME.py``: its id, once its worker retired."""
        (self.folder / f"{name}.py").write_text(textwrap.dedent(script.format(name=name, store=store)), encoding="utf-8")
        caller = self.folder / f"caller_{name}.py"
        caller.write_text(textwrap.dedent(CALLER.format(name=name)), encoding="utf-8")
        done = engine_daemon.run([sys.executable, caller.name], cwd=self.folder, env=env or self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        await_(lambda: not any(Path(w["script"]).name == f"{name}.py" for w in self.ask({"op": "status"})["workers"]),
               f"{name}'s worker to retire")
        (self.folder / f"{name}.ran").unlink()
        return model_id(self.folder / f"{name}.py", name)

    def page(self, ident: str) -> tuple[int, dict]:
        serving = self.ask({"op": "status"})["serving"]
        token = self.ask({"op": "http"}).get("token", "")
        return get(f"{serving['url']}/api/doc/{ident}", token)

    def test_a_held_document_exports_by_id_with_no_worker_of_its_script(self) -> None:
        ident = self.built("bracket")
        self.row(ident, "held")  # its worker gone, its document drained first
        out = self.folder / "bracket.stl"
        answer = self.ask({"op": "export", "source": {"id": ident}, "destinations": [str(out), str(out.with_suffix(".step"))],
                           "cwd": str(self.folder), "env": dict(os.environ)})
        self.assertIn("done", answer, answer)
        self.assertGreater(out.stat().st_size, 0)
        self.assertGreater(out.with_suffix(".step").stat().st_size, 0)
        inspected = engine_daemon.run([sys.executable, "-m", "cadgen.engine", "inspect", ident],
                                      cwd=self.folder, env=self.env)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertIn("source", json.loads(inspected.stdout), "its closure, from the held document")
        self.assertEqual([Path(w["script"]).name for w in self.ask({"op": "status"})["workers"]], ["documents"],
                         "the documents worker read the held bytes: no worker of its script started")
        self.assertFalse((self.folder / "bracket.ran").exists(), "nothing ran the script")
        # Its author's run builds it again: the same id, a new generation (a token, never a count).
        first = self.row(ident)["version"]
        again = engine_daemon.run([sys.executable, "caller_bracket.py"], cwd=self.folder, env=self.env)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.row(ident)["id"], ident)
        self.assertNotEqual(self.row(ident)["version"], first)

    def test_a_child_model_is_live_and_answers_by_its_id_from_the_worker_that_built_it(self) -> None:
        (self.folder / "part.py").write_text(textwrap.dedent(PART), encoding="utf-8")
        (self.folder / "assembly.py").write_text(textwrap.dedent(ASSEMBLY), encoding="utf-8")
        env = {**self.env, "CADGEN_ENGINE_WORKER_IDLE": "120"}  # the assembly's worker holds both
        for _ in range(2):  # the second run: the child's body marks it building, and the run's end built
            done = engine_daemon.run([sys.executable, "assembly.py"], cwd=self.folder, env=env)
            self.assertEqual(done.returncode, 0, done.stderr)
        plate, assembly = model_id(self.folder / "part.py", "plate"), model_id(self.folder / "assembly.py", "assembly")
        self.assertEqual((self.row(plate).get("state"), self.row(assembly).get("state")), ("live", "live"))
        out = self.folder / "plate.step"
        exported = engine_daemon.run([sys.executable, "-m", "cadgen.engine", "export", plate, str(out)],
                                     cwd=self.folder, env=env)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertGreater(out.stat().st_size, 0)
        inspected = engine_daemon.run([sys.executable, "-m", "cadgen.engine", "inspect", plate], cwd=self.folder, env=env)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["source"]["function"], "plate")
        programs = {ident: self.ask({"op": "model_info", "id": ident})["model"]["program"] for ident in (plate, assembly)}
        self.assertEqual(programs, {plate: str(self.folder / "assembly.py"), assembly: str(self.folder / "assembly.py")},
                         "the parent's program builds both again")

    def test_a_held_mechanism_exports_whole_from_the_hold(self) -> None:
        from cadgen.engine import document
        from tests.python.packages.cadgen.engine.test_kinematics import _arm_tip, _has_point, _vertices

        ident = self.built("hinge", script=HINGE)
        self.row(ident, "held")
        out = {kind: self.folder / f"held.{kind}" for kind in ("xbf", "step")}

        # The document as built, mechanism and all: a posed file is a model of its own (law 22).
        answer = self.ask({"op": "export", "source": {"id": ident}, "destinations": [str(p) for p in out.values()],
                           "cwd": str(self.folder), "env": dict(os.environ)})
        self.assertIn("done", answer, answer)
        held = document.Loaded(out["xbf"])
        (pair,) = held.mechanism.pairs
        self.assertEqual((pair.label, pair.kind, pair.limits), ("elbow", "revolute", ((-10.0, 120.0),)))
        self.assertEqual((held.mechanism.as_built, held.mechanism.configurations),
                         ({"elbow": (30.0,)}, {"raised": {"elbow": (90.0,)}}), "the xbf carries the mechanism")
        self.assertTrue(_has_point(_vertices(document.Loaded(out["step"]), "arm"), _arm_tip(30)),
                        "the STEP places the arm as built")
        # The viewer's export of the page's revision reads the hold too.
        _status, shown = self.page(ident)
        viewed = self.folder / "viewed.xbf"
        answer = self.ask({"op": "export", "source": {"id": ident},
                           "expected": {"id": ident, "digest": shown["exportRevision"],
                                        "modelRevision": shown["version"]}, "destinations": [str(viewed)]})
        self.assertIn("done", answer, answer)
        self.assertIsNotNone(document.Loaded(viewed).mechanism)
        self.assertEqual([Path(w["script"]).name for w in self.ask({"op": "status"})["workers"]], ["documents"])
        self.assertFalse((self.folder / "hinge.ran").exists(), "nothing ran the script")

    def test_a_glb_from_the_hold_and_from_its_xbf_file_is_the_live_one(self) -> None:
        from cadgen.engine import document
        from tests.python.packages.cadgen.engine.test_kinematics import _arm_tip, _has_point, _vertices

        ident = self.built("hinge", script=ANIMATED)
        self.row(ident, "held")
        live, held, step = self.folder / "live.glb", self.folder / "held.glb", self.folder / "held.step"
        saved, from_file = self.folder / "held.xbf", self.folder / "file.glb"
        answer = self.ask({"op": "export", "source": {"id": ident}, "destinations": [str(held), str(step), str(saved)],
                           "cwd": str(self.folder), "env": dict(os.environ)})
        self.assertIn("done", answer, answer)
        # The hold's xbf bytes are its Save As: a GLB of that file, read as any xbf is, bakes the record.
        answer = self.ask({"op": "export", "source": {"path": str(saved)}, "destinations": [str(from_file)],
                           "cwd": str(self.folder), "env": dict(os.environ)})
        self.assertIn("done", answer, answer)

        def clips(path: Path) -> list[str]:
            data = path.read_bytes()
            gltf = json.loads(data[20:20 + int.from_bytes(data[12:16], "little")])
            return [clip["name"] for clip in gltf.get("animations") or []]

        self.assertEqual(clips(held), ["lift", "show"], "the sequence and the animation, from the hold")
        self.assertEqual(held.read_bytes(), live.read_bytes(), "the GLB the build's worker wrote, byte for byte")
        self.assertEqual(from_file.read_bytes(), live.read_bytes(), "and the GLB of its xbf file, byte for byte")
        self.assertEqual(sorted(document.Loaded(saved).animations), ["show"], "the xbf records the animation")
        self.assertNotIn(b'"tracks"', step.read_bytes(), "a STEP is AP242 alone: no record of ours")
        self.assertTrue(_has_point(_vertices(document.Loaded(step), "arm"), _arm_tip(30)),
                        "a STEP of the same hold, as built: it never carried an animation")
        self.assertEqual([Path(w["script"]).name for w in self.ask({"op": "status"})["workers"]], ["documents"])
        self.assertFalse((self.folder / "hinge.ran").exists(), "nothing ran the script")

    def test_an_evicted_and_an_expired_document_name_their_rebuild_and_nothing_runs_it(self) -> None:
        # Every document is evicted once drained, and no cache holds it on disk (``test_cache``'s).
        tiny = {**self.env, "CADGEN_ENGINE_MEMORY_MB": "0.001", "CADGEN_ENGINE_CACHE_GB": "0"}
        evicted = self.built("arm", env=tiny)
        expired = self.built("cell", store='(store="memory")', env=tiny)
        command = f"python {self.folder / 'caller_arm.py'}"
        row = self.row(evicted, "evicted")
        self.assertEqual(row["rebuild"], command, "the program that built it, not its script")
        status, body = self.page(evicted)
        self.assertEqual((status, body["state"], body["rebuild"]), (404, "evicted", command))
        inspected = engine_daemon.run([sys.executable, "-m", "cadgen.engine", "inspect", evicted],
                                      cwd=self.folder, env=self.env)
        self.assertEqual(inspected.returncode, 2, "a document not held is a refusal, not a failure")
        self.assertIn(f"run `{command}`", inspected.stderr)
        row = self.row(expired, "expired")
        self.assertEqual(row["rebuild"], f"python {self.folder / 'caller_cell.py'}")
        status, body = self.page(expired)
        self.assertEqual((status, body["state"]), (404, "expired"))
        self.assertIn("it is kept in memory only", body["error"])
        listed = engine_daemon.run([sys.executable, "-m", "cadgen.engine", "status"], cwd=self.folder, env=self.env)
        self.assertIn(f"evicted   arm   {evicted}  run `{command}`", listed.stdout)
        self.assertIn(f"expired   cell  {expired}", listed.stdout)
        from cadgen.mcp.server import ToolFailed, _say_not_held

        with self.assertRaisesRegex(ToolFailed, "kept in memory only"):
            _say_not_held(expired)
        self.assertFalse((self.folder / "arm.ran").exists(), "nothing ran the script to restore it")
        self.assertFalse((self.folder / "cell.ran").exists())


if __name__ == "__main__":
    unittest.main()
