"""The engine's verbs counted (``cadgen/_internal/engine_telemetry.py``): cadgen's observer of
``cadgen.engine.api`` turns what each build, export and snapshot did into the counts the build daemon
kept for its builds -- kind ``model``, who asked, how it ended and why, the workers' health, cadgen's own
crashes -- keeps them in the spool, and a command starts the sender (``telemetry_send``, process ``cli``)
when nothing has taken the spool for a window. Nothing is counted where the environment says no."""

from __future__ import annotations

import inspect
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
from unittest import mock

from cadgen import analytics
from cadgen._internal import engine_telemetry, telemetry_send
from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src"
WORKER = {"fresh": None, "retired": False, "died": None}


def facts(verb: str = "build", ok: bool = True, **extra) -> dict:
    """What ``cadgen.engine.api`` tells its observers of one verb (``api._facts``)."""
    return {"verb": verb, "ok": ok, "seconds": 0.5, "program": False, "models": [], "worker": dict(WORKER),
            "error": None, **extra}


def error(type_: str | None = "ValueError", frames: list | None = None, **flags) -> dict:
    return {"type": type_, "frames": frames or [], "engine": False, "refused": False, "here": False, **flags}


class EngineTelemetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="engine-telemetry-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp / "state"), "DO_NOT_TRACK": "",
                                                   "CADGEN_TELEMETRY": "", "CADGEN_ENGINE_WORKER": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.settings = self.tmp / "state" / "settings.json"
        analytics.choose(True, by="cli", path=self.settings)
        self.spawn = telemetry_send._spawn
        for patched in (mock.patch.object(engine_telemetry, "command", None),
                        mock.patch.object(telemetry_send, "_spawn", lambda _settings: self.fail("no sender here"))):
            patched.start()
            self.addCleanup(patched.stop)
        self.model = self.tmp / "secret_model.py"

    def spooled(self) -> list[dict]:
        spool = self.settings.with_name(analytics.SPOOL)
        return [json.loads(line)["counts"] for line in spool.read_text(encoding="utf-8").splitlines()] if spool.exists() else []

    def sent(self) -> list[dict]:
        """What the sender a command starts sends of the spool."""
        payloads: list[dict] = []
        telemetry_send.send(self.settings, send=lambda payload: payloads.append(payload) or True)
        return payloads

    def test_a_build_counts_as_the_daemon_counted_its_builds(self) -> None:
        def reason(found: dict) -> str:
            return engine_telemetry.counts(facts(ok=False, error=found), "command")["builds"][0]["reason"]

        # Why it failed, from the error's class and whose code raised it, never from what it said.
        model = error(frames=[{"file": str(self.model), "line": 3, "function": "secret_model"}])
        self.assertEqual(reason(model), "model_error")
        self.assertEqual(reason({**model, "type": "OCP.Standard.Standard_Failure"}), "kernel_error")
        self.assertEqual(reason({**model, "type": "SyntaxError"}), "script_error")
        self.assertEqual(reason({**model, "type": "ModuleNotFoundError"}), "missing_module")
        self.assertEqual(reason({**model, "type": "RuntimeError", "engine": True}), "export_error")  # a file it wrote
        self.assertEqual(reason(error(None, engine=True, refused=True)), "refused")
        # A mistake in cadgen's own code, as its worker answered it: a bug, and a crash named cadgen's way.
        from cadgen.engine import api

        lines, start = inspect.getsourcelines(api._heard)
        line = start + next(at for at, text in enumerate(lines) if "getattr(" in text)
        bug = error("KeyError", [*model["frames"], {"file": api.__file__, "line": line, "function": "_heard"}], engine=True)
        self.assertEqual(reason(bug), "bug")
        crash = {"where": "build", "type": "KeyError", "handled": True,
                 "frames": [{"file": "<user>", "function": "<user>", "line": 0},
                            {"file": "cadgen/engine/api.py", "function": "_heard", "line": line}]}
        self.assertEqual(engine_telemetry.counts(facts(ok=False, error=bug), "script")["crashes"], [crash])
        # Raised here, it is the command's to report (``cadgen.cli``): only a script's process reports it itself.
        with mock.patch.object(engine_telemetry, "command", "xbf"):
            self.assertNotIn("crashes", engine_telemetry.counts(facts(ok=False, error={**bug, "here": True}), "command"))
        here = engine_telemetry.counts(facts(ok=False, error={**bug, "here": True}), "script")["crashes"]
        self.assertEqual(here, [{**crash, "where": "command", "handled": False}])

        built = facts(models=[{"ok": True, "cached": True, "children": 0, "parts": 3, "files": ["glb", "xbf"]}],
                      worker={"fresh": True, "retired": True, "died": None}, program=True)
        self.assertEqual(engine_telemetry.counts(built, "script"), {
            "builds": [{"kind": "model", "via": "script", "outcome": "ok", "seconds": 0.5, "cached": True}],
            "features": ["assembly", "declared_mesh"], "health": {"workers": 1, "recycles": 1}})
        died = facts(ok=False, worker={**WORKER, "died": -11}, error=error(None, engine=True))
        self.assertEqual(engine_telemetry.counts(died, "command"), {
            "builds": [{"kind": "model", "via": "command", "outcome": "crashed", "seconds": 0.5, "cached": False}],
            "crashes": [analytics.died(-11)], "health": {"crashes": 1}})
        stopped = facts(ok=False, error=error("KeyboardInterrupt", here=True))
        self.assertEqual(engine_telemetry.counts(stopped, "script")["builds"][0]["outcome"], "cancelled")

        # Kept as a command's counts are, and sent by the sender as the process ``cli``, in schema 8.
        for found, via in ((built, "script"), (facts(ok=False, error=model), "script"), (died, "command")):
            self.assertTrue(analytics.spool(engine_telemetry.counts(found, via), path=self.settings))
        [payload] = self.sent()
        self.assertEqual((payload["schema"], payload["process"]), (8, "cli"))
        self.assertEqual(payload["events"], [
            {"name": "build", "kind": "model", "via": "command", "count": 1, "failed": 0, "crashed": 1, "cancelled": 0,
             "cached": 0, "seconds": 0.5, "longest": 0.5},
            {"name": "build", "kind": "model", "via": "script", "count": 2, "failed": 1, "crashed": 0, "cancelled": 0,
             "cached": 1, "seconds": 1.0, "longest": 0.5},
            {"name": "build_failure", "kind": "model", "via": "script", "reason": "model_error", "count": 1},
            {"name": "feature", "feature": "assembly", "count": 1},
            {"name": "feature", "feature": "declared_mesh", "count": 1},
            {"name": "health", "workers": 1, "crashes": 1, "recycles": 1, "refusals": 0},
            {"name": "exception", **analytics.died(-11), "count": 1},
        ])
        self.assertNotIn("secret", json.dumps(payload))
        self.assertFalse(self.settings.with_name(analytics.SPOOL).exists(), "the spool is the sender's now")

    def test_an_export_counts_a_build_of_each_destination_and_a_snapshot_its_source(self) -> None:
        exported = facts("export", source="model", outputs=[
            {"kind": "step", "seconds": 0.1}, {"kind": "threemf", "seconds": 0.2}, {"kind": "dxf", "seconds": 0.1},
            {"kind": "xbf", "seconds": 0.1}])
        self.assertEqual(engine_telemetry.counts(exported, "command"), {
            "builds": [{"kind": kind, "via": "command", "outcome": "ok", "seconds": 0.5 / 4, "cached": False}
                       for kind in ("step", "3mf", "dxf", "xbf")]})
        drawn = engine_telemetry.counts(facts("snapshot", source="model", found=True, pose=False), "script")
        self.assertEqual(drawn, {"snapshots": [{"format": "model", "ok": True, "seconds": 0.5}]})
        # A snapshot at a pose is the one use of kinematics a verb tells: an export has no pose.
        posed = engine_telemetry.counts(facts("snapshot", source="model", found=True, pose=True), "script")
        self.assertEqual(posed["features"], ["kinematics"])
        # Every kind the stills draw is counted by its name, from the facts the verb tells (``api._facts``):
        # drawings and robot descriptions as documents and meshes are.
        from cadgen.engine import api

        for suffix, kind in ((".xbf", "xbf"), (".step", "step"), (".3mf", "3mf"), (".dxf", "dxf"), (".urdf", "urdf"), (".sdf", "sdf"),
                             (".srdf", "srdf")):
            told = api._facts("snapshot", (self.tmp / f"secret{suffix}", self.tmp / "out.png"), {}, {}, None, None, 0.5)
            self.assertEqual(engine_telemetry.counts(told, "command"),
                             {"snapshots": [{"format": kind, "ok": True, "seconds": 0.5}]}, suffix)

        def why(failure: dict, **extra) -> str:
            snapshot = facts("snapshot", ok=False, **{"source": "xbf", "found": True, "pose": False, **extra}, error=failure)
            return engine_telemetry.counts(snapshot, "command")["snapshots"][0]["reason"]

        refused = error("cadgen.engine.snapshot.SnapshotRefused", engine=True, refused=True, here=True)
        self.assertEqual(why(refused), "bad_request")
        self.assertEqual(why(refused, found=False), "no_file")
        self.assertEqual(why(error(), models=[{"ok": False, "cached": False, "children": 0, "parts": 0, "files": []}]),
                         "input_error")
        self.assertEqual(why(error("TimeoutError", here=True)), "timeout")
        # No OpenGL to draw with: the picture was not drawn.
        self.assertEqual(why(error("RuntimeError", engine=True, here=True)), "render_error")

    def test_snapshot_sources_and_failures_keep_model_and_file_kinds_through_the_spool(self) -> None:
        from cadgen.engine import api
        from cadgen.engine.snapshot import SnapshotRefused

        ident = "c9b8b08f-8634-5011-a447-55648e01d810"
        file = self.tmp / "private.xbf"
        file.touch()
        # Direct sources (Python, CLI, MCP) and Quick Edit packets use the same observed verb.
        for source, kind in ((ident, "model"), (file, "xbf")):
            for packet in (False, True):
                for failed in (False, True):
                    heard = {"source": source} if packet else {}
                    args = () if packet else (source, self.tmp / "out.png")
                    refusal = SnapshotRefused("private detail") if failed else None
                    told = api._facts("snapshot", args, {"job": "private.packet"} if packet else {},
                                      heard, None, refusal, 0.5)
                    counted = engine_telemetry.counts(told, "command")
                    self.assertEqual(counted["snapshots"][0]["format"], kind)
                    self.assertTrue(analytics.spool(counted, path=self.settings))
        [payload] = self.sent()
        snapshots = [event for event in payload["events"] if event["name"] == "snapshot"]
        self.assertEqual([(row["kind"], row["count"], row["failed"]) for row in snapshots],
                         [("model", 4, 2), ("xbf", 4, 2)])
        failures = [event for event in payload["events"] if event["name"] == "snapshot_failure"]
        self.assertEqual([(row["kind"], row["count"]) for row in failures], [("model", 2), ("xbf", 2)])
        self.assertNotIn("private", json.dumps(payload))
        self.assertNotIn(ident, json.dumps(payload))

    def test_nothing_is_counted_where_the_environment_or_the_asker_says_so(self) -> None:
        for switch in ({"DO_NOT_TRACK": "1"}, {"CADGEN_TELEMETRY": "0"}, {"CADGEN_ENGINE_WORKER": "1"}):
            with mock.patch.dict(os.environ, switch):
                engine_telemetry.observe(facts())
        with mock.patch.object(engine_telemetry, "command", "viewer"):  # a server's own work: it counts its own
            engine_telemetry.observe(facts())
        self.assertEqual(self.spooled(), [])
        engine_telemetry.observe(facts(program=True))
        self.assertEqual(self.spooled(), [{"builds": [{"kind": "model", "via": "script", "outcome": "ok", "seconds": 0.5,
                                                       "cached": False}]}])
        analytics.choose(False, by="cli", path=self.settings, forget=lambda _id: True)
        engine_telemetry.observe(facts())
        self.assertEqual(self.spooled(), [], "a no deletes what waits, and keeps nothing more")

    def test_a_command_starts_the_sender_once_the_spool_has_waited_a_window(self) -> None:
        self.assertTrue(analytics.spool({"builds": [{"kind": "xbf", "via": "script", "outcome": "ok", "seconds": 1.0}]},
                                        path=self.settings))
        started: list[Path] = []
        now = time.time()

        def due(at: float) -> bool:
            return telemetry_send.start_if_due(self.settings, now=at, spawn=started.append)

        self.assertFalse(due(now), "the CAD app or the viewer may take it yet")
        self.assertTrue(due(now + analytics.FLUSH_SECONDS + 1))
        self.assertFalse(due(now + analytics.FLUSH_SECONDS + 2), "one sender a window")
        self.assertTrue(due(now + 2 * analytics.FLUSH_SECONDS + 3))
        self.assertEqual(started, [self.settings, self.settings])
        # Detached: no window, a session or group of its own, no output, the command's telemetry switches not
        # inherited (it goes by the person's settings).
        with mock.patch.object(subprocess, "Popen") as popen, mock.patch.dict(os.environ, {"CADGEN_TELEMETRY": "1"}):
            self.spawn(self.settings)
        [call] = popen.call_args_list
        self.assertEqual(call.args[0], [sys.executable, "-P", "-m", "cadgen._internal.telemetry_send"])
        detached = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
                    if os.name == "nt" else {"start_new_session": True})
        self.assertEqual({key: call.kwargs[key] for key in (*detached, "stdin", "stdout", "stderr")},
                         {**detached, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL})
        self.assertNotIn("CADGEN_TELEMETRY", call.kwargs["env"])
        # The program itself: it sends what waits, keeps what the receiver did not take, and exits.
        env = {**os.environ, "PYTHONPATH": str(SRC), "CADGEN_API_URL": "http://127.0.0.1:9"}  # nothing answers there
        done = subprocess.run([sys.executable, "-P", "-m", "cadgen._internal.telemetry_send"], env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
        self.assertFalse(self.settings.with_name(analytics.SPOOL).exists())
        [kept] = [json.loads(line) for line in self.settings.with_name(analytics.KEPT).read_text(encoding="utf-8").splitlines()]
        self.assertEqual((kept["batch"]["process"], kept["batch"]["schema"], kept["batch"]["events"][0]["kind"]),
                         ("cli", 8, "xbf"))


class ThroughTheDaemonTest(unittest.TestCase):
    """``python model.py`` and a ``cadgen`` command, counted in their own processes through the engine's own
    daemon: who asked, the worker started for the first build, and the one that died under a build."""

    def setUp(self) -> None:
        # One folder of the test's own holds the models, the engine's door, its state and its cache.
        self.root = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.folder, self.state = self.root / "models", self.root / "state"
        self.folder.mkdir()
        self.env = {**os.environ, "PYTHONPATH": str(SRC), "CADGEN_STATE_DIR": str(self.state),
                                          "CADGEN_ENGINE_DIR": str(self.root / "engine"),
                                          "CADGEN_CACHE_DIR": str(self.root / "cache"),
                                          "CADGEN_ENGINE_MESH": "inline", "DO_NOT_TRACK": "", "CADGEN_TELEMETRY": ""}
        self.addCleanup(self._stop)
        analytics.choose(True, by="cli", path=self.state / "settings.json")
        self.env = engine_daemon.started(self.env, self.addCleanup)

    def _stop(self) -> None:
        """The test's engine stopped, and every process it started -- the daemon, its workers, its
        render processes -- gone before its folder is removed; one left is killed and fails the test."""
        stopped = self.run_in("-m", "cadgen.engine", "stop")
        left = engine_daemon.survivors(self.env)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertEqual(left, [], "no engine process of this test's survives it")

    def run_in(self, *args: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, *args], cwd=self.folder, env=self.env)

    def test_a_model_script_and_a_command_are_counted_by_who_asked(self) -> None:
        (self.folder / "plate.py").write_text(textwrap.dedent("""
            import build123d as bd
            from cadgen.engine import stl, xbf

            @xbf("XBF/plate.xbf")
            @stl("plate.stl")
            def plate():
                base, peg = bd.Box(10, 10, 2), bd.Pos(20, 0, 0) * bd.Cylinder(2, 4)
                base.label, peg.label = "base", "peg"
                return bd.Compound(children=[base, peg], label="plate")

            if __name__ == "__main__":
                plate()
        """), encoding="utf-8")
        (self.folder / "dies.py").write_text(textwrap.dedent("""
            import os
            from cadgen.engine import xbf

            @xbf("XBF/dies.xbf")
            def dies():
                os._exit(3)

            if __name__ == "__main__":
                dies()
        """), encoding="utf-8")
        script = self.run_in("plate.py")
        self.assertEqual(script.returncode, 0, script.stderr)
        # A command exports the xbf the script built: the worker that built it holds it.
        command = self.run_in("-m", "cadgen.cli", "export", "XBF/plate.xbf", "plate.step")
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertEqual(self.run_in("dies.py").returncode, 1)
        spool = self.state / analytics.SPOOL
        first, second, third = [json.loads(line)["counts"] for line in spool.read_text(encoding="utf-8").splitlines()]
        self.assertEqual((first["builds"][0]["via"], first["builds"][0]["outcome"], first["features"], first["health"]),
                         ("script", "ok", ["assembly", "declared_mesh"], {"workers": 1}))
        self.assertEqual((second["builds"][0]["kind"], second["builds"][0]["via"], second["builds"][0]["outcome"],
                          second.get("health")), ("step", "command", "ok", None), "its worker was warm")
        self.assertEqual((third["builds"][0]["via"], third["builds"][0]["outcome"], third["health"], third["crashes"]),
                         ("script", "crashed", {"crashes": 1}, [analytics.died(3)]))
        self.assertEqual({build["kind"] for counts in (first, third) for build in counts["builds"]}, {"model"})

    def test_a_telemetry_batch_holds_no_id_and_no_path(self) -> None:
        """Verbs by document id -- a pointer model's and a shape's handed over, one refused, one whose body
        raised -- count kinds, outcomes and times: no id, script or state folder reaches the spool or the batch."""
        from cadgen.engine.ids import canonical, model_id

        (self.folder / "part.py").write_text(textwrap.dedent("""
            import build123d as bd
            from cadgen.engine import model


            @model
            def part():
                return bd.Box(3, 2, 1)


            @model
            def broken():
                raise ValueError(f"broken in {__file__}")
        """), encoding="utf-8")
        run = self.run_in("-c", "import part, build123d as bd, cadgen\npart.part()\n"
                                "print('SHAPE', cadgen.model(bd.Box(1, 2, 3), name='handed').id)\n"
                                "try:\n    part.broken()\nexcept Exception:\n    pass\n")
        self.assertEqual(run.returncode, 0, run.stderr)
        pointer, handed = model_id(self.folder / "part.py", "part"), run.stdout.split("SHAPE ", 1)[1].split()[0]
        refused = model_id(self.folder / "part.py", "nowhere")
        for ident in (pointer, handed):
            done = self.run_in("-m", "cadgen.cli", "export", ident, str(self.folder / f"{ident}.stl"))
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotEqual(self.run_in("-m", "cadgen.cli", "export", refused, str(self.folder / "x.stl")).returncode, 0)
        from tests.python.packages.cadgen.engine.test_snapshot import gl

        try:
            gl()
            drawn = True
        except unittest.SkipTest:
            drawn = False
        if drawn:
            done = self.run_in("-m", "cadgen.cli", "snapshot", pointer, str(self.folder / "part.png"))
            self.assertEqual(done.returncode, 0, done.stderr)
        spool = self.state / analytics.SPOOL
        spooled = spool.read_text(encoding="utf-8")
        counted = [json.loads(line)["counts"] for line in spooled.splitlines()]
        outcomes = [(build["kind"], build["outcome"]) for counts in counted for build in counts.get("builds", [])]
        self.assertIn(("model", "failed"), outcomes, "the body that raised was counted")
        self.assertEqual(outcomes.count(("stl", "ok")), 2, "both exports by id were counted")
        if drawn:
            self.assertTrue(any(counts.get("snapshots") for counts in counted), "the snapshot by id was counted")
        # What the sender sends: the spool taken into a batch, kept beside the settings when nothing answers.
        env = {**self.env, "CADGEN_API_URL": "http://127.0.0.1:9"}
        sent = subprocess.run([sys.executable, "-P", "-m", "cadgen._internal.telemetry_send"], env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(sent.returncode, 0, sent.stderr)
        batch = (self.state / analytics.KEPT).read_text(encoding="utf-8")
        self.assertIn('"events"', batch)
        for text, where in ((spooled, "spool"), (batch, "batch")):
            for secret in (pointer, handed, refused, canonical(self.folder / "part.py"), str(self.folder),
                           canonical(self.folder), str(self.state), canonical(self.state), "part.py"):
                self.assertNotIn(secret, text, f"the {where} holds {secret}")

    def test_cadgen_observes_the_engine_once_its_verbs_are_imported_and_never_sooner(self) -> None:
        done = self.run_in("-c", "import sys, cadgen; print(any(name.startswith('cadgen.engine') for name in sys.modules)); "
                                 "from cadgen.engine import api; print([o.__module__ for o in api.observers])")
        self.assertEqual(done.stdout.split("\n")[:2], ["False", "['cadgen._internal.engine_telemetry']"], done.stderr)


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
