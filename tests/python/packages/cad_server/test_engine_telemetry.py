"""The engine counted (``cad_server/_internal/engine_telemetry.py``): the daemon counts each model build it
answers -- kind ``model``, how it ended, a failure only where the system or the machine caused it, its workers'
health, cadgen's own crashes -- for the person who asked it; the server's observer of ``cad.engine.api``, which its
commands append, counts each export and snapshot, never a build. Each is kept in the spool, and a command or the
daemon starts the sender (``telemetry_send``, process ``cli``) when nothing has taken the spool for a window.
Nothing is counted where the asker's environment says no, nor in a model's own process, which runs where only the
library is."""

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

from cad_server import analytics
from cad_server._internal import engine_telemetry, telemetry_send
from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them
WORKER = {"fresh": None, "retired": False, "died": None}


def facts(verb: str = "build", ok: bool = True, **extra) -> dict:
    """What ``cad.engine.api`` tells its observers of one verb (``api._facts``)."""
    return {"verb": verb, "ok": ok, "seconds": 0.5, "program": False, "models": [], "worker": dict(WORKER),
            "error": None, **extra}


def error(type_: str | None = "ValueError", frames: list | None = None, **flags) -> dict:
    return {"type": type_, "frames": frames or [], "engine": False, "refused": False, "here": False, **flags}


class EngineTelemetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="engine-telemetry-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.tmp / "state"), "DO_NOT_TRACK": "",
                                                   "CAD_TELEMETRY": "", "CAD_ENGINE_WORKER": ""})
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
        from cad.engine import api

        lines, start = inspect.getsourcelines(api._heard)
        line = start + next(at for at, text in enumerate(lines) if "getattr(" in text)
        bug = error("KeyError", [*model["frames"], {"file": api.__file__, "line": line, "function": "_heard"}], engine=True)
        self.assertEqual(reason(bug), "bug")
        crash = {"where": "build", "type": "KeyError", "handled": True,
                 "frames": [{"file": "<user>", "function": "<user>", "line": 0},
                            {"file": "cad/engine/api.py", "function": "_heard", "line": line}]}
        self.assertEqual(engine_telemetry.counts(facts(ok=False, error=bug), "script")["crashes"], [crash])
        # Raised here, it is the command's to report (``cad_server.cli``): only a script's process reports it itself.
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

        # Kept as a command's counts are, and sent by the sender as the process ``cli``, in schema 10.
        for found, via in ((built, "script"), (facts(ok=False, error=model), "script"), (died, "command")):
            self.assertTrue(analytics.spool(engine_telemetry.counts(found, via), path=self.settings))
        [payload] = self.sent()
        self.assertEqual((payload["schema"], payload["process"]), (10, "cli"))
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
        from cad.engine import api

        for suffix, kind in ((".xbf", "xbf"), (".step", "step"), (".3mf", "3mf"), (".dxf", "dxf"), (".urdf", "urdf"), (".sdf", "sdf"),
                             (".srdf", "srdf")):
            told = api._facts("snapshot", (self.tmp / f"secret{suffix}", self.tmp / "out.png"), {}, {}, None, None, 0.5)
            self.assertEqual(engine_telemetry.counts(told, "command"),
                             {"snapshots": [{"format": kind, "ok": True, "seconds": 0.5}]}, suffix)

        def why(failure: dict, **extra) -> str:
            snapshot = facts("snapshot", ok=False, **{"source": "xbf", "found": True, "pose": False, **extra}, error=failure)
            return engine_telemetry.counts(snapshot, "command")["snapshots"][0]["reason"]

        refused = error("cad.engine.snapshot.SnapshotRefused", engine=True, refused=True, here=True)
        self.assertEqual(why(refused), "bad_request")
        self.assertEqual(why(refused, found=False), "no_file")
        self.assertEqual(why(error(), models=[{"ok": False, "cached": False, "children": 0, "parts": 0, "files": []}]),
                         "input_error")
        self.assertEqual(why(error("TimeoutError", here=True)), "timeout")
        # A picture that was not drawn.
        self.assertEqual(why(error("RuntimeError", engine=True, here=True)), "render_error")
        # No OpenGL context to draw in, wherever it was to be drawn: in this process, in a model's worker (its
        # traceback), or in a file's render process (the type the daemon's answer names).
        from cad.engine import api
        from cad.engine.render.context import Unavailable

        no_display = "no X display for OpenGL: secret"
        source = (self.tmp / "secret.xbf", self.tmp / "out.png")
        (self.tmp / "secret.xbf").touch()
        try:
            raise Unavailable(no_display)
        except Unavailable as raised:
            here = raised
        worker = api.EngineError("Traceback (most recent call last):\n  File \"/x/context.py\", line 9, in driver\n"
                                 f"cad.engine.render.context.Unavailable: {no_display}")
        render = api._failed({"failed": f"RuntimeError: cad.engine.render.context.Unavailable: {no_display}",
                              "type": "cad.engine.render.context.Unavailable"})
        for failed in (here, worker, render):
            told = api._facts("snapshot", source, {}, {}, None, failed, 0.5)
            self.assertEqual(engine_telemetry.counts(told, "command")["snapshots"][0]["reason"], "no_gl", failed)
        self.assertIn("no_gl", analytics.SNAPSHOT_FAILURES)

    def test_snapshot_sources_and_failures_keep_model_and_file_kinds_through_the_spool(self) -> None:
        from cad.engine import api
        from cad.engine.snapshot import SnapshotRefused

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
        self.assertEqual([(row["kind"], row["reason"], row["part"], row["count"]) for row in failures],
                         [("model", "bad_request", "other", 2), ("xbf", "bad_request", "other", 2)])
        self.assertNotIn("private", json.dumps(payload))
        self.assertNotIn(ident, json.dumps(payload))

    def test_a_refused_snapshot_is_counted_by_the_part_of_its_request_it_refused_never_the_value(self) -> None:
        from cad.engine import api, worker
        from cad.engine.mechanism import KinematicsError
        from cad.engine.snapshot import SnapshotRefused, parse_camera, parse_display, parse_size

        def refused(call) -> BaseException:
            try:
                call()
            except ValueError as error:
                return error
            raise AssertionError("not refused")

        source = (self.tmp / "secret.xbf", self.tmp / "out.png")
        (self.tmp / "secret.xbf").touch()
        cases = [
            (refused(lambda: parse_display('{"clip": {"axis": "w-secret"}}', False)), "display.clip"),
            (refused(lambda: parse_display("secret-mode", False)), "display.mode"),
            (refused(lambda: parse_display('{"secret": 1}', False)), "display"),
            (refused(lambda: parse_camera("secret-angle")), "camera"),
            (refused(lambda: parse_size(9, 9, None)), "size"),
            (KinematicsError("joint secret_joint is out of range"), "pose"),
            (SnapshotRefused("named nothing"), "other"),
        ]
        for error, part in cases:
            with self.subTest(part=part):
                # As a worker answers it and this process raises it again (``api._failed``), and -- the library's
                # own refusals -- as raised here.
                answered = api._failed({"failed": str(error), **worker.refusal(error)})
                for raised in (answered, *((error,) if isinstance(error, SnapshotRefused) else ())):
                    told = api._facts("snapshot", source, {}, {}, None, raised, 0.5)
                    [counted] = engine_telemetry.counts(told, "command")["snapshots"]
                    self.assertEqual((counted["reason"], counted.get("part", "other")), ("bad_request", part))
                    self.assertTrue(analytics.spool(engine_telemetry.counts(told, "command"), path=self.settings))
        # Every word the library names a part by is one the receiver takes.
        library = Path(inspect.getfile(api)).parent
        import re

        named = {word for path in library.rglob("*.py")
                 for word in re.findall(r'(?:refusing\(|part=)"([a-z.]+)"', path.read_text(encoding="utf-8"))}
        self.assertTrue(named)
        self.assertLessEqual(named, analytics.SNAPSHOT_PARTS)
        # A failure that was no refusal names no part.
        told = api._facts("snapshot", source, {}, {}, None, RuntimeError("secret"), 0.5)
        self.assertTrue(analytics.spool(engine_telemetry.counts(told, "command"), path=self.settings))
        [payload] = self.sent()
        failures = sorted((row["reason"], row["part"], row["count"]) for row in payload["events"]
                          if row["name"] == "snapshot_failure")
        self.assertEqual(failures, sorted([("bad_request", part, 2 if isinstance(error, SnapshotRefused) else 1)
                                           for error, part in cases] + [("render_error", "none", 1)]))
        self.assertNotIn("secret", json.dumps(payload))

    def test_a_failure_the_engine_answers_in_words_is_counted_by_its_type_never_as_a_refusal(self) -> None:
        # The engine that could not start the kernel process the work runs in, a file the worker could not write:
        # failures the daemon or the worker answers in words alone, with the type they failed with beside them
        # (``frames.failed_type``). Each is what it is; only a type that is a refusal is one.
        from cad.engine import api, frames
        from cad.engine.build import BuildError
        from cad.engine.serve import KernelProcessesUnavailable
        from cad_server.engine.daemon import _unstarted
        from cad_server.engine.supervisor import Gone

        source = (self.tmp / "secret.xbf", self.tmp / "out.png")
        (self.tmp / "secret.xbf").touch()

        def counted(answer: dict) -> tuple[str, str]:
            failed = api._failed(answer)
            snapshot = api._facts("snapshot", source, {}, {}, None, failed, 0.5)
            build = api._facts("build", (), {}, {}, None, failed, 0.5)
            return (engine_telemetry.counts(snapshot, "command")["snapshots"][0]["reason"],
                    engine_telemetry.counts(build, "command")["builds"][0]["reason"])

        unavailable = KernelProcessesUnavailable("the server has no CAD kernel environment: secret")
        unstarted = Gone("the worker for secret.py did not start", unready=True)
        cases = [
            ({"failed": str(unavailable), **frames.failed_type(unavailable)}, ("no_kernel", "no_kernel")),
            ({"failed": str(unstarted), **_unstarted(unstarted)}, ("no_kernel", "no_kernel")),
            ({"failed": "secret.png: permission denied", **frames.failed_type(PermissionError())}, ("render_error", "io_error")),
            ({"failed": "no secret.step", **frames.failed_type(FileNotFoundError())}, ("no_file", "missing_file")),
            ({"failed": "@xbf returned no shape", **frames.failed_type(BuildError("x"))}, ("bad_request", "refused")),
            ({"failed": "unknown request 'secret'"}, ("bad_request", "refused")),  # in words alone: a refusal, as ever
        ]
        for answer, reasons in cases:
            with self.subTest(answer=answer):
                self.assertEqual(counted(answer), reasons)
        # One that died under the work says so in its words (its exit status): no type to count it by.
        self.assertEqual(_unstarted(Gone("the worker for secret.py exited (-9) during the build", during=True)), {})
        self.assertLessEqual({"no_kernel", "no_gl"}, analytics.SNAPSHOT_FAILURES)
        self.assertIn("no_kernel", analytics.BUILD_FAILURES)

    def test_an_older_server_or_no_daemon_is_no_refusal_by_its_class(self) -> None:
        # Untyped engine errors that are the system's state, not the request: told by their class, whatever
        # their words; one of no class that says so is a refusal, as ever.
        from cad.engine import api

        destinations = (self.tmp / "secret.step", self.tmp / "secret.dxf")
        cases = [(api.Outdated("the CAD server running meshed secret.stl at its own tolerance"), False, "outdated"),
                 (api.NoDaemon("secret"), False, "export_error"), (api.Stopped("secret"), False, "export_error"),
                 (api.Unanswered("secret"), False, "export_error"),
                 (api.EngineError("no engine daemon"), True, "refused"),
                 (api.EngineError("secret.py: no model named x"), True, "refused")]
        for raised, refused, reason in cases:
            with self.subTest(error=type(raised).__name__):
                told = api._facts("export", (self.tmp / "secret.xbf", *destinations), {}, {}, None, raised, 0.5)
                self.assertIs(told["error"]["refused"], refused)
                reasons = {row["reason"] for row in engine_telemetry.counts(told, "command")["builds"]}
                self.assertEqual(reasons, {reason})

    def test_nothing_is_counted_where_the_environment_or_the_asker_says_so(self) -> None:
        exported = facts("export", source="xbf", outputs=[{"kind": "step", "seconds": 0.5}])
        for switch in ({"DO_NOT_TRACK": "1"}, {"CAD_TELEMETRY": "0"}, {"CAD_ENGINE_WORKER": "1"}):
            with mock.patch.dict(os.environ, switch):
                engine_telemetry.observe(exported)
        with mock.patch.object(engine_telemetry, "command", "viewer"):  # a server's own work: it counts its own
            engine_telemetry.observe(exported)
        # A build is the daemon's to count, where it is answered: a Python caller that imports the server, whose
        # ``Model.build()`` its observer sees, counts it no second time; one built in its own process
        # (``daemon=False``) is counted nowhere.
        engine_telemetry.observe(facts(program=True, worker={**WORKER, "fresh": True}))
        self.assertEqual(self.spooled(), [])
        engine_telemetry.observe({**exported, "program": True, "worker": {**WORKER, "fresh": True}})
        self.assertEqual(self.spooled(), [{"builds": [{"kind": "step", "via": "script", "outcome": "ok",
                                                       "seconds": 0.5, "cached": False}]}],
                         "a worker started is the build's, which the daemon counts")
        analytics.choose(False, by="cli", path=self.settings, forget=lambda _id: True)
        engine_telemetry.observe(exported)
        self.assertEqual(self.spooled(), [], "a no deletes what waits, and keeps nothing more")

    def test_the_daemon_fails_a_model_build_for_the_system_s_reasons_alone(self) -> None:
        # The owner's rule: telemetry tracks CAD (or the machine) failing, never a script that raises or asks the
        # kernel for what it refuses. Pinned here, word by word.
        self.assertEqual(analytics.SYSTEM_FAILURES, {"bug", "no_kernel", "export_error", "outdated", "memory", "io_error"})
        self.assertLess(analytics.SYSTEM_FAILURES, analytics.BUILD_FAILURES)
        built = facts(ok=False, error=error(), worker={**WORKER, "fresh": True, "retired": True})
        for reason in sorted(analytics.BUILD_FAILURES):
            with self.subTest(reason=reason), mock.patch.object(analytics, "told_failure", return_value=reason):
                [build] = engine_telemetry.model_build(built)["builds"]
                if reason in analytics.SYSTEM_FAILURES:
                    self.assertEqual((build["outcome"], build["reason"]), ("failed", reason))
                else:  # in ``count`` alone
                    self.assertEqual(build, {"kind": "model", "via": "script", "outcome": "ok", "seconds": 0.5,
                                             "cached": False})
                self.assertEqual(engine_telemetry.model_build(built)["health"], {"workers": 1, "recycles": 1})
        # A build's features are usage, not CAD failing: not counted.
        assembly = facts(models=[{"ok": True, "cached": False, "children": 2, "parts": 3, "files": ["stl"]}])
        self.assertEqual(engine_telemetry.model_build(assembly),
                         {"builds": [{"kind": "model", "via": "script", "outcome": "ok", "seconds": 0.5, "cached": False}]})

    def test_a_build_the_daemon_answered_is_counted_for_its_asker_as_it_ended(self) -> None:
        from cad.engine import api

        def report(ok: bool = True, **extra) -> dict:
            return {"ok": ok, "model": "secret_model", "id": "c9b8b08f-8634-5011-a447-55648e01d810",
                    "cache": {"used": False}, **extra}

        model = [{"file": str(self.model), "line": 3, "function": "secret_model"}]
        lines, start = inspect.getsourcelines(api._heard)
        ours = {"file": api.__file__, "line": start + next(at for at, text in enumerate(lines) if "getattr(" in text),
                "function": "_heard"}
        written = ('Traceback (most recent call last):\n  File "/x/cad/engine/document.py", line 9, in write\n'
                   "PermissionError: [Errno 13] Permission denied: '/secret/plate.stl'")
        cases = [  # (the answer, fresh, died) -> its build row, and what else the window carries
            (({"done": [report()]}, True, None),
             {"outcome": "ok", "cached": False}, {"health": {"workers": 1}}),
            (({"done": [report(cache={"used": True})]}, False, None), {"outcome": "ok", "cached": True}, {}),
            # The person's: their code raised, the kernel refused their fillet. ``count`` alone.
            (({"done": [report(False, raised={"type": "ValueError", "frames": model})]}, False, None),
             {"outcome": "ok", "cached": False}, {}),
            (({"done": [report(False, raised={"type": "OCP.Standard.Standard_Failure", "frames": model})]}, False, None),
             {"outcome": "ok", "cached": False}, {}),
            # The system's: a mistake in our code a worker answered with, a file the engine could not write.
            (({"done": [report(False, raised={"type": "KeyError", "frames": [*model, ours]})]}, False, None),
             {"outcome": "failed", "cached": False, "reason": "bug"},
             {"crashes": [{"where": "build", "type": "KeyError", "handled": True,
                           "frames": [{"file": "<user>", "function": "<user>", "line": 0},
                                      {"file": "cad/engine/api.py", "function": "_heard", "line": ours["line"]}]}]}),
            (({"done": [report(False, trace=written)]}, False, None),
             {"outcome": "failed", "cached": False, "reason": "io_error"}, {}),
            # A worker that died under it: its exit status.
            (({"failed": "the worker for secret_model.py exited (-11) during the build"}, True, -11),
             {"outcome": "crashed", "cached": False}, {"health": {"workers": 1, "crashes": 1},
                                                       "crashes": [analytics.died(-11)]}),
        ]
        for (answer, fresh, died), build, extra in cases:
            with self.subTest(build=build, extra=extra):
                self.assertTrue(engine_telemetry.answered(answer, 0.5, {}, fresh=fresh, died=died))
                [counted] = self.spooled()
                self.assertEqual(counted, {"builds": [{"kind": "model", "via": "script", "seconds": 0.5, **build}],
                                           **extra})
                self.settings.with_name(analytics.SPOOL).unlink()
        # Consent follows the person who asked: their environment, never the daemon's own.
        for env in ({"DO_NOT_TRACK": "1"}, {"CAD_TELEMETRY": "0"}, None):
            self.assertFalse(engine_telemetry.answered({"done": [report()]}, 0.5, env))
        self.assertEqual(self.spooled(), [])
        with mock.patch.dict(os.environ, {"DO_NOT_TRACK": "1"}):  # whoever started the daemon said no; the asker did not
            self.assertTrue(engine_telemetry.answered({"done": [report()]}, 0.5, {}))
        self.assertEqual(len(self.spooled()), 1)

    def test_the_daemon_counts_a_build_with_no_kernel_and_reports_a_failed_making_once(self) -> None:
        # Builds that met a kernel environment that could not be made: each a system failure (``no_kernel``), the
        # crash reported once per making that failed, by the claim a CAD tool's call shares (``first_report``).
        from cad.engine.serve import KernelProcessesUnavailable
        from cad_server._internal import base
        from cad_server.engine import daemon

        class Making:
            claims = [True, False]

            def claim(self) -> bool:
                return self.claims.pop(0)

        engine = daemon.Daemon(cap=1)
        script = self.tmp / "secret_model.py"
        script.write_text("", encoding="utf-8")

        def lease(*_args, **_kwargs):
            try:
                raise RuntimeError("uv could not resolve secret")
            except RuntimeError as error:
                raise KernelProcessesUnavailable("the server has no CAD kernel environment: secret", "resolve") from error

        sent: list[dict] = []
        with mock.patch.object(base, "MAKING", Making()), mock.patch.object(engine, "lease", lease), \
                mock.patch.object(engine, "caller", return_value=(None, None)):
            for _ in range(2):
                engine.handle({"op": "build", "script": str(script), "cwd": str(self.tmp), "env": {}}, sent.append)
        self.assertEqual([answer["type"] for answer in sent], ["cad.engine.serve.KernelProcessesUnavailable"] * 2)
        first, second = self.spooled()
        for counted in (first, second):
            [build] = counted["builds"]
            self.assertEqual((build["outcome"], build["reason"]), ("failed", "no_kernel"))
        [crash] = first["crashes"]
        self.assertEqual((crash["where"], crash["type"], crash["cause"]),
                         ("build", "cad.engine.serve.KernelProcessesUnavailable", "resolve"))
        self.assertNotIn("crashes", second, "once per making that failed")
        self.assertNotIn("secret", json.dumps([first, second]))

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
        with mock.patch.object(subprocess, "Popen") as popen, mock.patch.dict(os.environ, {"CAD_TELEMETRY": "1"}):
            self.spawn(self.settings)
        [call] = popen.call_args_list
        self.assertEqual(call.args[0], [sys.executable, "-P", "-m", "cad_server._internal.telemetry_send"])
        detached = ({"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
                    if os.name == "nt" else {"start_new_session": True})
        self.assertEqual({key: call.kwargs[key] for key in (*detached, "stdin", "stdout", "stderr")},
                         {**detached, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL})
        self.assertNotIn("CAD_TELEMETRY", call.kwargs["env"])
        # The program itself: it sends what waits, keeps what the receiver did not take, and exits.
        env = {**os.environ, "PYTHONPATH": str(SRC), "CAD_API_URL": "http://127.0.0.1:9"}  # nothing answers there
        done = subprocess.run([sys.executable, "-P", "-m", "cad_server._internal.telemetry_send"], env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
        self.assertFalse(self.settings.with_name(analytics.SPOOL).exists())
        [kept] = [json.loads(line) for line in self.settings.with_name(analytics.KEPT).read_text(encoding="utf-8").splitlines()]
        self.assertEqual((kept["batch"]["process"], kept["batch"]["schema"], kept["batch"]["events"][0]["kind"]),
                         ("cli", 10, "xbf"))


class ThroughTheDaemonTest(unittest.TestCase):
    """``python model.py`` and a ``cadgen`` command through the engine's own daemon: a build counted by the
    daemon that answered it, a command in its own process, who asked and its worker's part; the model's own
    process counting nothing."""

    def setUp(self) -> None:
        # One folder of the test's own holds the models, the engine's door, its state and its cache.
        self.root = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.folder, self.state = self.root / "models", self.root / "state"
        self.folder.mkdir()
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_STATE_DIR": str(self.state),
                                          "CAD_ENGINE_DIR": str(self.root / "engine"),
                                          "CAD_CACHE_DIR": str(self.root / "cache"),
                                          "CAD_ENGINE_MESH": "inline", "DO_NOT_TRACK": "", "CAD_TELEMETRY": "",
                                          "CAD_API_URL": "http://127.0.0.1:9"},  # nothing answers there
                                         self.addCleanup)
        self.addCleanup(self._stop)
        analytics.choose(True, by="cli", path=self.state / "settings.json")

    def _stop(self) -> None:
        """The test's engine stopped, and every process it started -- the daemon, its workers, its
        render processes -- gone before its folder is removed; one left is killed and fails the test."""
        stopped = self.run_in("-m", "cad_server.engine", "stop")
        left = engine_daemon.survivors(self.env)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertEqual(left, [], "no engine process of this test's survives it")

    def run_in(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([sys.executable, *args], cwd=self.folder, env={**self.env, **env})

    def spooled(self, lines: int) -> list[dict]:
        """The spool once it holds ``lines`` lines: the daemon keeps a build's count after its answer is sent."""
        from tests.python.support.cache_fixtures import await_

        spool = self.state / analytics.SPOOL

        def found() -> list[dict]:
            return ([json.loads(line)["counts"] for line in spool.read_text(encoding="utf-8").splitlines()]
                    if spool.exists() else [])

        await_(lambda: len(found()) >= lines, f"{lines} counts in the spool")
        counted = found()
        self.assertEqual(len(counted), lines, counted)
        return counted

    def test_the_daemon_counts_the_builds_it_answers_and_a_model_s_own_process_counts_nothing(self) -> None:
        for name, body in (("quiet", "return bd.Box(1, 1, 1)"), ("raises", "raise ValueError('secret')"),
                           ("dies", "os._exit(3)"),
                           ("plate", "base, peg = bd.Box(10, 10, 2), bd.Pos(20, 0, 0) * bd.Cylinder(2, 4)\n"
                                     "    base.label, peg.label = 'base', 'peg'\n"
                                     "    return bd.Compound(children=[base, peg], label='plate')")):
            (self.folder / f"{name}.py").write_text(textwrap.dedent(f"""
                import os
                import build123d as bd
                from cad.engine import stl, xbf

                @xbf("XBF/{name}.xbf")
                @stl("{name}.stl")
                def {name}():
                    {{body}}

                if __name__ == "__main__":
                    {name}()
            """).replace("{body}", body), encoding="utf-8")
        # Asked by a person whose environment says no: nothing, whatever started the daemon.
        self.assertEqual(self.run_in("quiet.py", DO_NOT_TRACK="1").returncode, 0)
        script = self.run_in("plate.py")
        self.assertEqual(script.returncode, 0, script.stderr)
        self.assertEqual(self.run_in("plate.py").returncode, 0)  # unchanged: its xbf taken whole
        # A command exports the xbf the script built: counted by the command, its warm worker no health of its.
        command = self.run_in("-m", "cad_server.cli", "xbf", "export", "XBF/plate.xbf", "plate.step")
        self.assertEqual(command.returncode, 0, command.stderr)
        self.assertEqual(self.run_in("raises.py").returncode, 1)  # the person's script: count alone
        self.assertEqual(self.run_in("dies.py").returncode, 1)  # its worker died under it: crashed
        # A Python caller that imports the server, its observer attached: the daemon counts its build, once.
        caller = self.run_in("-c", "import cad_server, plate; print(plate.plate.build().ok)")
        self.assertEqual(caller.stdout.split(), ["True"], caller.stderr)
        counted = self.spooled(6)
        builds = [(row["kind"], row["via"], row["outcome"], row["cached"]) for counts in counted
                  for row in counts.get("builds", [])]
        self.assertEqual(builds, [("model", "script", "ok", False), ("model", "script", "ok", True),
                                  ("step", "command", "ok", False), ("model", "script", "ok", False),
                                  ("model", "script", "crashed", False), ("model", "script", "ok", True)])
        self.assertEqual([counts.get("health") for counts in counted],
                         [{"workers": 1}, None, None, {"workers": 1}, {"workers": 1, "crashes": 1}, None])
        [died] = counted[4]["crashes"]
        self.assertEqual(died, analytics.died(3), "its exit status")
        self.assertNotIn("features", json.dumps(counted), "a build's features are usage: not counted")
        # The window, sent as the process ``cli``: no failure of the person's, no reason, no exception but the death.
        env = {**self.env, "CAD_API_URL": "http://127.0.0.1:9"}
        sent = subprocess.run([sys.executable, "-P", "-m", "cad_server._internal.telemetry_send"], env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(sent.returncode, 0, sent.stderr)
        [kept] = [json.loads(line) for line in (self.state / analytics.KEPT).read_text(encoding="utf-8").splitlines()]
        events = kept["batch"]["events"]
        [model] = [event for event in events if event["name"] == "build" and event["kind"] == "model"]
        self.assertEqual({key: model[key] for key in ("via", "count", "failed", "crashed", "cancelled", "cached")},
                         {"via": "script", "count": 5, "failed": 0, "crashed": 1, "cancelled": 0, "cached": 2})
        self.assertEqual([event["name"] for event in events if event["name"] in ("build_failure", "exception")],
                         ["exception"])
        self.assertNotIn("secret", json.dumps(kept))

    def test_a_telemetry_batch_holds_no_id_and_no_path(self) -> None:
        """Verbs by document id -- a pointer model's and a shape's handed over, one refused, one whose body
        raised -- count kinds, outcomes and times: no id, script or state folder reaches the spool or the batch."""
        from cad.engine.ids import canonical, model_id

        (self.folder / "part.py").write_text(textwrap.dedent("""
            import build123d as bd
            from cad.engine import model


            @model
            def part():
                return bd.Box(3, 2, 1)


            @model
            def broken():
                raise ValueError(f"broken in {__file__}")
        """), encoding="utf-8")
        run = self.run_in("-c", "import part, build123d as bd, cad\npart.part()\n"
                                "print('SHAPE', cad.model(bd.Box(1, 2, 3), name='handed').id)\n"
                                "try:\n    part.broken()\nexcept Exception:\n    pass\n")
        self.assertEqual(run.returncode, 0, run.stderr)
        pointer, handed = model_id(self.folder / "part.py", "part"), run.stdout.split("SHAPE ", 1)[1].split()[0]
        refused = model_id(self.folder / "part.py", "nowhere")
        for ident in (pointer, handed):
            done = self.run_in("-m", "cad_server.cli", "model", "export", ident, str(self.folder / f"{ident}.stl"))
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotEqual(self.run_in("-m", "cad_server.cli", "model", "export", refused, str(self.folder / "x.stl")).returncode, 0)
        from tests.python.packages.cad_server.engine.test_snapshot import gl

        try:
            gl()
            drawn = True
        except unittest.SkipTest:
            drawn = False
        if drawn:
            done = self.run_in("-m", "cad_server.cli", "model", "snapshot", pointer, str(self.folder / "part.png"))
            self.assertEqual(done.returncode, 0, done.stderr)
        spool = self.state / analytics.SPOOL
        spooled = spool.read_text(encoding="utf-8")
        counted = [json.loads(line)["counts"] for line in spooled.splitlines()]
        outcomes = [(build["kind"], build["outcome"]) for counts in counted for build in counts.get("builds", [])]
        # The daemon counts the model's builds, the one whose body raised in ``count`` alone (the person's).
        self.assertEqual([outcome for outcome in outcomes if outcome[0] == "model"], [("model", "ok")] * 2)
        self.assertEqual(outcomes.count(("stl", "ok")), 2, "both exports by id were counted")
        if drawn:
            self.assertTrue(any(counts.get("snapshots") for counts in counted), "the snapshot by id was counted")
        # What the sender sends: the spool taken into a batch, kept beside the settings when nothing answers.
        env = {**self.env, "CAD_API_URL": "http://127.0.0.1:9"}
        sent = subprocess.run([sys.executable, "-P", "-m", "cad_server._internal.telemetry_send"], env=env,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(sent.returncode, 0, sent.stderr)
        batch = (self.state / analytics.KEPT).read_text(encoding="utf-8")
        self.assertIn('"events"', batch)
        for text, where in ((spooled, "spool"), (batch, "batch")):
            for secret in (pointer, handed, refused, canonical(self.folder / "part.py"), str(self.folder),
                           canonical(self.folder), str(self.state), canonical(self.state), "part.py"):
                self.assertNotIn(secret, text, f"the {where} holds {secret}")

    def test_a_command_observes_the_engine_once_its_verbs_are_imported_and_never_sooner(self) -> None:
        done = self.run_in("-c", "import sys, cad_server.cli; print(any(name.startswith('cad.engine') for name in sys.modules)); "
                                 "from cad.engine import api; print([o.__module__ for o in api.observers])")
        self.assertEqual(done.stdout.split("\n")[:2], ["False", "['cad_server._internal.engine_telemetry']"], done.stderr)
        model = self.run_in("-c", "import cad; from cad.engine import api; print(api.observers)")
        self.assertEqual(model.stdout.split("\n")[0], "[]", "a model's own process has no observer")


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
