"""Document lifetime: a document outlives its worker (its ``.xbf``, read as any file is once the worker goes),
everything the daemon holds lives under one memory budget -- files the engine reads again itself evicted
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
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from tests.python.support.ids import model_id  # noqa: E402
from cad.engine.serve import LOW_WATER, Server  # noqa: E402

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
    """The budget over a server's documents and tessellations, its one order, and the pressure signal."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-lifetime-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.server = Server(mesh_mode="inline", budget=64 * MIB)
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

    def test_the_least_recently_used_goes_first_a_file_or_a_model_alike_and_a_watched_one_never(self) -> None:
        server = self.server
        server.cache.put("mesh", b"x" * (4 * MIB))
        self.model("older", 26)
        file = self.file("file", 26)
        self.assertEqual(len(server.served), 2, "under the budget nothing goes")
        newer = self.model("newer", 10)  # 66 MiB: past the budget, trimmed to 80 % of it
        self.assertNotIn("mesh", server.cache.items, "a tessellation goes first: it is remade from the shape")
        self.assertEqual(set(server.served), {file, newer},
                         "the least recently used, a model before a newer file: one order, nothing ranked above it")
        self.assertLessEqual(server.holding(), int(64 * MIB * 0.8))
        server.sync(newer)  # a page watches it
        third = self.model("third", 30)
        self.assertEqual(set(server.served), {newer, third}, "the file goes: it is the least recently used")
        fourth = self.model("fourth", 30)
        self.assertEqual(set(server.served), {newer, fourth}, "a watched document is never evicted")
        self.assertEqual(server.memory()["evictions"], 3)

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
        from cad.engine import build as engine_build

        script = self.folder / "plate.py"
        script.write_text(textwrap.dedent("""
            import build123d as bd
            from cad.engine import model


            @model("XBF/plate.xbf")
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


class NotHeldRefusalTest(unittest.TestCase):
    """An id that names nothing is refused as ``NotHeld``."""

    def test_the_refusal_crosses_the_daemon_as_its_type(self) -> None:
        from cad.engine import api
        from cad_server.engine import daemon
        from cad.engine.serve import NotHeld

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-refusal-")))
        self.addCleanup(shutil.rmtree, folder, True)
        script = folder / "cell.py"
        script.write_text("", encoding="utf-8")
        engine = daemon.Daemon()
        self.addCleanup(engine.supervisor.stop)
        ident = model_id(script, "cell")
        # Built before, its worker gone and its .xbf with it: no worker, no file.
        engine.models.records[ident] = {"id": ident, "source": {"script": str(script), "name": "cell",
                                                                "xbf": str(folder / "cell.xbf")}, "worker": None,
                                        "program": str(script), "kind": "model", "version": "g1", "builtAt": 0,
                                        "files": [], "revision": "r1"}
        answers: list[dict] = []
        engine.handle({"op": "document", "id": ident}, answers.append)
        (answer,) = answers
        self.assertEqual((answer["failed"], "state" in answer, "rebuild" in answer),
                         (f"no document {ident} is held", False, False))
        error = api._failed(answer)
        self.assertIsInstance(error, NotHeld, "raised as its type: the CLI exits 2 for a ValueError")
        self.assertEqual(str(error), answer["failed"])


class ListingTest(unittest.TestCase):
    """The engine's list of the model documents its workers hold: one that declares files is listed like any
    other, since a declared file is an export of it, never a tie between the two."""

    def test_a_model_that_declares_outputs_is_listed_like_any_other(self) -> None:
        from types import SimpleNamespace

        from cad_server.engine import daemon
        from cad_server.engine.state import file_version

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-listing-")))
        self.addCleanup(shutil.rmtree, folder, True)
        engine = daemon.Daemon()
        self.addCleanup(engine.supervisor.stop)
        idents = []
        for name, files in (("plain", []), ("declares", [str(folder / "XBF" / "declares.xbf"), str(folder / "declares.step")])):
            script = folder / f"{name}.py"
            script.write_text("", encoding="utf-8")
            ident = model_id(script, name)
            idents.append(ident)
            (folder / f"{name}.xbf").write_bytes(b"its document")  # a model's document is its .xbf, there
            engine.models.records[ident] = {"id": ident, "source": {"script": str(script), "name": name,
                                                                    "xbf": str(folder / f"{name}.xbf")},
                                            "written": file_version(folder / f"{name}.xbf"),  # the one its run left
                                            "worker": SimpleNamespace(alive=lambda: True, service=SimpleNamespace(name="worker"),
                                                                      key=str(script), retired=False),
                                            "program": str(script),
                                            "kind": "model",
                                            "version": "g1", "builtAt": 0, "files": files, "revision": "r1"}
        for op in ("models", "status"):
            answers: list[dict] = []
            engine.handle({"op": op}, answers.append)
            self.assertEqual(sorted(row["id"] for row in answers[-1]["models"]), sorted(idents), op)


class _Supervisor:
    """A supervisor whose one worker is live; ``landing``, once set, is run at its next look at the worker: what
    the daemon does meanwhile on another thread (a run's answer) lands between a row's read and its judgement."""

    def __init__(self) -> None:
        self.landing = None

    def holds(self, _worker) -> bool:
        landing, self.landing = self.landing, None
        if landing is not None:
            landing()
        return True


class OwnRunsTest(unittest.TestCase):
    """A live model's row is let go for an ``.xbf`` another process wrote, and never for one its own worker's run
    wrote, wherever the run is when the page asks (``models.Models.held``): writing the file before the daemon
    heard any of its progress, answering while the row is judged, or failing after it wrote the file. A row let go
    hears no progress and no failure of the next run (the daemon tells the rows of the worker that ran it)."""

    def setUp(self) -> None:
        from types import SimpleNamespace

        from cad_server.engine.models import Models

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-own-runs-")))
        self.addCleanup(shutil.rmtree, folder, True)
        self.enterContext(mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(folder / "state"),
                                                       "CAD_CACHE_DIR": str(folder / "cache")}))
        self.server = Server(mesh_mode="inline")
        self.addCleanup(self.server.stop)
        self.supervisor = _Supervisor()
        daemon = SimpleNamespace(supervisor=self.supervisor, server=self.server, builders={},
                                 serve=lambda _request: self.server)
        self.models = Models(daemon)
        self.worker = SimpleNamespace(alive=lambda: True, leased=False)
        script = folder / "part.py"
        script.write_text("", encoding="utf-8")
        self.xbf = folder / "part.xbf"
        self.ident = model_id(script, "part")
        self.source = {"script": str(script), "name": "part", "xbf": str(self.xbf)}
        self.runs = 0
        self.writes()
        self.answer()

    def writes(self) -> None:
        """A run of the model under way, its lease taken: its worker writes the .xbf (each run's its own size)."""
        self.runs += 1
        self.worker.leased = True
        self.xbf.write_bytes(b"x" * self.runs)

    def answer(self, ok: bool = True) -> None:
        """The run's answer, as the daemon takes it (``Daemon._built``), and then its lease let go."""
        report = {"ok": ok, "id": self.ident, "model": "part.py::part", "source": self.source,
                  "closure": {"key": f"{self.runs:064x}"}, "files": {str(self.xbf): {"kind": "xbf"}}}
        self.models.register(self.worker, {"done": [report]})
        self.server.built({ident: None if ok else {"model": "part.py::part"} for ident in
                           self.models.paths(self.worker)})
        self.worker.leased = False

    def assertLive(self) -> None:
        self.assertIsNotNone(self.models.held(self.ident))
        self.assertEqual(self.models.paths(self.worker), [self.ident], "the next run's progress and failure reach it")
        self.assertIn(self.ident, self.server.model_loaders, "its page is the model's")

    def test_a_row_read_before_its_run_answered_is_judged_with_the_answer_s_row(self) -> None:
        self.writes()
        self.supervisor.landing = self.answer  # a page's read takes the row; the answer lands; then it is judged
        self.assertLive()
        from cad_server.engine.state import file_version

        self.assertEqual(self.models.row(self.ident)["written"], file_version(self.xbf))

    def test_what_its_own_runs_write_is_its_own_and_what_another_process_writes_is_the_file(self) -> None:
        self.writes()  # written before the daemon heard any frame of the run
        self.assertLive()
        self.answer()
        self.assertLive()
        self.writes()
        self.answer(ok=False)  # a run that wrote its .xbf, then failed on a declared file
        self.assertLive()
        self.xbf.write_bytes(b"another process's")
        self.assertIsNone(self.models.held(self.ident))
        self.assertNotIn(self.ident, self.server.model_loaders)
        self.assertEqual(self.models.paths(self.worker), [])


class StatusTextTest(unittest.TestCase):
    def test_the_serving_line_counts_what_was_opened_beside_the_documents_held(self) -> None:
        from cad_server.engine.cli import status_text

        live = [{"id": f"id-{n}", "name": f"part{n}", "state": "live"} for n in range(6)]
        text = status_text({"pid": 1, "up": 5, "cap": 4, "workers": [], "models": live,
                            "serving": {"url": "http://127.0.0.1:1", "documents": [
                                {"id": "f", "path": "/a.xbf", "state": "evicted", "bytes": 0}]}})
        lines = text.splitlines()
        self.assertIn("serving http://127.0.0.1:1: 0 documents opened by a page or a command", lines)
        self.assertEqual(sum(line.startswith("  live") for line in lines), 6, "the documents held, listed apart")

    def test_a_port_handed_on_by_an_update_is_said_with_the_port_it_served_before(self) -> None:
        from cad_server.engine.cli import status_text

        text = status_text({"pid": 1, "up": 5, "cap": 4, "workers": [], "models": [],
                            "serving": {"url": "http://127.0.0.1:3246", "port": 3246, "defaultPort": 3245,
                                        "portSource": "handed", "also": [3300], "documents": []}})
        self.assertIn("serving http://127.0.0.1:3246 (the port pages were on before this server started), and on port 3300 too: "
                      "0 documents opened by a page or a command", text.splitlines())


SCRIPT = """
import pathlib
import build123d as bd
from cad.engine import model

pathlib.Path(__file__).with_suffix(".ran").write_text("ran", encoding="utf-8")


@model
def {name}():
    return bd.Box(3, 2, 1)
"""

HINGE = """
import pathlib
import build123d as bd
from cad.build123d import mechanism_state
from cad.engine import model

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
ANIMATED = HINGE.replace("from cad.engine import model", """from cad.build123d import configuration_sequence
from cad.engine import glb, model
from cad.build123d import animation""").replace("@model", '@model\n@glb("live.glb")').replace("    return root", """\
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
from cad.engine import model


@model
def plate():
    return bd.Box(4, 3, 1)
"""

ASSEMBLY = """
import build123d as bd
from cad.engine import model
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
    """Through a daemon, its workers real processes retired after each build, over a memory cap of 1 MB."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-lifetime-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        # Its engine, its registry of documents and its cache are its own, never the developer's.
        own = Path(tempfile.mkdtemp(prefix="engine-own-"))  # beside the project: nothing lands in it
        self.addCleanup(shutil.rmtree, own, True)
        private = {"CAD_ENGINE_DIR": str(self.state), "CAD_STATE_DIR": str(own / "state"),
                   "CAD_CACHE_DIR": str(own / "cache")}
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), **private,
                                          "CAD_ENGINE_MESH": "inline",
                                          "CAD_ENGINE_WORKER_RSS_MB": "1"}, self.addCleanup)
        # This process asks the test's daemon (``status``, ``export``), never starting one.
        self.enterContext(mock.patch.dict(os.environ, private))
        self.addCleanup(self._stop)

    def _stop(self) -> None:
        engine_daemon.run([sys.executable, "-m", "cad_server.engine", "stop"], cwd=self.folder, env=self.env)
        shutil.rmtree(self.folder, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def restart(self, env: dict) -> None:
        """The test's server stopped and started again with ``env``: what it reads of its environment it reads as
        it starts."""
        engine_daemon.run([sys.executable, "-m", "cad_server.engine", "stop"], cwd=self.folder, env=self.env)
        engine_daemon.start(env)

    def ask(self, message: dict) -> dict:
        from cad.engine.client import request

        return request(message, start=False) or {}

    def known(self, ident: str, state: str) -> dict:
        """What the engine says of document ``ident`` (its ``state`` op), once it is in ``state``."""
        return await_(lambda: (lambda found: found if found.get("state") == state else None)(
            self.ask({"op": "state", "id": ident})), f"{ident} {state}")

    def row(self, ident: str) -> dict:
        """The status row of document ``ident`` a live worker holds; ``{}`` for none."""
        return next((row for row in self.ask({"op": "status"}).get("models") or [] if row["id"] == ident), {})

    def built(self, name: str, env: dict | None = None, script: str = SCRIPT) -> str:
        """``python caller_NAME.py`` builds model ``name`` of ``NAME.py``: its id, once its worker retired."""
        (self.folder / f"{name}.py").write_text(textwrap.dedent(script.format(name=name)), encoding="utf-8")
        caller = self.folder / f"caller_{name}.py"
        caller.write_text(textwrap.dedent(CALLER.format(name=name)), encoding="utf-8")
        done = engine_daemon.run([sys.executable, caller.name], cwd=self.folder, env=env or self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        await_(lambda: not any(Path(w["script"]).name == f"{name}.py" for w in self.ask({"op": "status"})["workers"]),
               f"{name}'s worker to retire")
        (self.folder / f"{name}.ran").unlink()
        return model_id(self.folder / f"{name}.py", name)

    def assert_documents_worker_alone(self, script: str) -> None:
        """Since ``script``'s worker retired, only the documents worker served it: no worker of the
        script is live, and none retired again (its one retirement is the build's; the documents
        worker may have retired too, past the 1 MB cap)."""
        status = self.ask({"op": "status"})
        live = [Path(w["script"]).name for w in status["workers"]]
        retired = [Path(row["script"]).name for row in status["retired"]]
        self.assertNotIn(script, live)
        self.assertEqual(retired.count(script), 1, retired)
        self.assertIn("documents", live + retired)

    def page(self, ident: str) -> tuple[int, dict]:
        serving = self.ask({"op": "status"})["serving"]
        token = self.ask({"op": "http"}).get("token", "")
        return get(f"{serving['url']}/api/v1/documents/model/{ident}/structure", token)

    def test_a_held_document_exports_by_id_with_no_worker_of_its_script(self) -> None:
        ident = self.built("bracket")
        self.known(ident, "held")  # its worker gone: its .xbf is the document
        out = self.folder / "bracket.stl"
        answer = self.ask({"op": "export", "source": {"id": ident}, "destinations": [str(out), str(out.with_suffix(".step"))],
                           "cwd": str(self.folder), "env": dict(os.environ)})
        self.assertIn("done", answer, answer)
        self.assertGreater(out.stat().st_size, 0)
        self.assertGreater(out.with_suffix(".step").stat().st_size, 0)
        inspected = engine_daemon.run([sys.executable, "-m", "cad_server.engine", "inspect", ident, "--json"],
                                      cwd=self.folder, env=self.env)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertIn("source", json.loads(inspected.stdout)["closure"], "its closure, from its .xbf")
        # The documents worker read its .xbf (it may have retired since: the memory cap is 1 MB).
        self.assertNotIn("bracket.py", [Path(w["script"]).name for w in self.ask({"op": "status"})["workers"]],
                         "no worker of its script started")
        self.assertFalse((self.folder / "bracket.ran").exists(), "nothing ran the script")
        # Its author's run takes it again from its .xbf: the same id, nothing ran.
        again = engine_daemon.run([sys.executable, "caller_bracket.py"], cwd=self.folder, env=self.env)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn(f"id: {ident}", again.stdout)
        self.assertIn("its .xbf holds the model's key", again.stdout)

    def test_a_child_model_is_live_and_answers_by_its_id_from_the_worker_that_built_it(self) -> None:
        (self.folder / "part.py").write_text(textwrap.dedent(PART), encoding="utf-8")
        (self.folder / "assembly.py").write_text(textwrap.dedent(ASSEMBLY), encoding="utf-8")
        env = {**self.env, "CAD_ENGINE_WORKER_RSS_MB": ""}  # no small cap: the assembly's worker holds both
        self.restart(env)
        for _ in range(2):  # the second run: the child's body marks it building, and the run's end built
            done = engine_daemon.run([sys.executable, "assembly.py"], cwd=self.folder, env=env)
            self.assertEqual(done.returncode, 0, done.stderr)
        plate, assembly = model_id(self.folder / "part.py", "plate"), model_id(self.folder / "assembly.py", "assembly")
        self.assertEqual((self.row(plate).get("state"), self.row(assembly).get("state")), ("live", "live"))
        out = self.folder / "plate.step"
        exported = engine_daemon.run([sys.executable, "-m", "cad_server.engine", "export", plate, str(out)],
                                     cwd=self.folder, env=env)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertGreater(out.stat().st_size, 0)
        inspected = engine_daemon.run([sys.executable, "-m", "cad_server.engine", "inspect", plate, "--json"], cwd=self.folder, env=env)
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertEqual(json.loads(inspected.stdout)["closure"]["source"]["function"], "plate")
        programs = {ident: self.ask({"op": "model_info", "id": ident})["model"]["program"] for ident in (plate, assembly)}
        self.assertEqual(programs, {plate: str(self.folder / "assembly.py"), assembly: str(self.folder / "assembly.py")},
                         "the parent's program builds both again")

    def test_a_held_mechanism_exports_whole_from_its_xbf(self) -> None:
        from cad.engine import document
        from tests.python.packages.cad.engine.test_kinematics import _arm_tip, _has_point, _vertices

        ident = self.built("hinge", script=HINGE)
        self.known(ident, "held")
        out = {kind: self.folder / f"held.{kind}" for kind in ("xbf", "step")}

        # The document as built, mechanism and all: a posed file is a model of its own.
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
        # The viewer's export of the page's version reads its file too.
        _status, shown = self.page(ident)
        viewed = self.folder / "viewed.step"
        answer = self.ask({"op": "export", "source": {"path": str(self.folder / "hinge.xbf")},
                           "expected": {"version": shown["version"]}, "destinations": [str(viewed)]})
        self.assertIn("done", answer, answer)
        self.assertTrue(_has_point(_vertices(document.Loaded(viewed), "arm"), _arm_tip(30)))
        self.assert_documents_worker_alone("hinge.py")
        self.assertFalse((self.folder / "hinge.ran").exists(), "nothing ran the script")

    def test_a_glb_of_a_model_no_worker_holds_and_of_its_xbf_is_the_live_one(self) -> None:
        from cad.engine import document
        from tests.python.packages.cad.engine.test_kinematics import _arm_tip, _has_point, _vertices

        ident = self.built("hinge", script=ANIMATED)
        self.known(ident, "held")
        live, held, step = self.folder / "live.glb", self.folder / "held.glb", self.folder / "held.step"
        saved, from_file = self.folder / "held.xbf", self.folder / "file.glb"
        answer = self.ask({"op": "export", "source": {"id": ident}, "destinations": [str(held), str(step), str(saved)],
                           "cwd": str(self.folder), "env": dict(os.environ)})
        self.assertIn("done", answer, answer)
        # Its xbf, saved as: a GLB of that file, read as any xbf is, bakes the record.
        answer = self.ask({"op": "export", "source": {"path": str(saved)}, "destinations": [str(from_file)],
                           "cwd": str(self.folder), "env": dict(os.environ)})
        self.assertIn("done", answer, answer)

        def clips(path: Path) -> list[str]:
            data = path.read_bytes()
            gltf = json.loads(data[20:20 + int.from_bytes(data[12:16], "little")])
            return [clip["name"] for clip in gltf.get("animations") or []]

        self.assertEqual(clips(held), ["lift", "show"], "the sequence and the animation, from its .xbf")
        self.assertEqual(held.read_bytes(), live.read_bytes(), "the GLB the build's worker wrote, byte for byte")
        self.assertEqual(from_file.read_bytes(), live.read_bytes(), "and the GLB of its xbf file, byte for byte")
        self.assertEqual(sorted(document.Loaded(saved).animations), ["show"], "the xbf records the animation")
        self.assertNotIn(b'"tracks"', step.read_bytes(), "a STEP is AP242 alone: no record of ours")
        self.assertTrue(_has_point(_vertices(document.Loaded(step), "arm"), _arm_tip(30)),
                        "a STEP of the same document, as built: it never carried an animation")
        self.assert_documents_worker_alone("hinge.py")
        self.assertFalse((self.folder / "hinge.ran").exists(), "nothing ran the script")


def setUpModule() -> None:
    # The state, cache and engine folder every test here reads are its own, never the developer's
    # (``engine_daemon.isolate``).
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
