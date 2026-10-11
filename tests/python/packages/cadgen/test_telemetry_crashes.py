"""Telemetry's crash reports (``cadgen/analytics.py``: ``signature``, ``report``, ``Recorder.crashed``): what a
crash says -- its type and its frames in code that may be named -- and what it never says: its message, a
value, a path outside cadgen, the standard library or cadgen's own dependencies, or anything of the
person's own code. And that crashes go where their process sends from, counted rather than repeated."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen import analytics
from cadgen.daemon import client


def _user_calls(target, filename: str = "/home/someone/secret_bracket.py"):
    """A function the person wrote, in a file of theirs, that calls ``target``."""
    namespace = {"target": target}
    exec(compile("def make_secret_bracket():\n    return target()\n", filename, "exec"), namespace)  # noqa: S102
    return namespace["make_secret_bracket"]


def _raises(error: BaseException):
    """The person's model, raising ``error`` in their own code."""
    def model() -> None:
        raise error
    return _user_calls(model)


def _caught(call) -> BaseException:
    try:
        call()
    except BaseException as error:  # noqa: BLE001 - the error is what the test reads
        return error
    raise AssertionError("it did not fail")


def _cadgen_bug() -> None:
    """A mistake in cadgen's own code, as a crash would find one: a KeyError raised inside cadgen."""
    analytics._Tally().note("no such event", ("secret_part",), {})


class SignatureTest(unittest.TestCase):
    def test_a_bug_in_cadgen_names_its_frames_and_nothing_the_person_made(self) -> None:
        error = _caught(_user_calls(_cadgen_bug))
        found = analytics.signature(error, "build", bugs_only=True)
        self.assertEqual((found["where"], found["type"], found["handled"]), ("build", "KeyError", True))
        files = [frame["file"] for frame in found["frames"]]
        self.assertIn("<user>", files)
        self.assertEqual(files[-1], "cadgen/analytics.py", "the innermost frame is where it failed")
        self.assertEqual(found["frames"][-1]["function"], "_Tally.note")
        self.assertTrue(analytics.valid_signature(found))
        said = json.dumps(found)
        for secret in ("secret", "/home/someone", "no such event", os.path.expanduser("~")):
            self.assertNotIn(secret, said)

    def test_the_persons_own_errors_are_theirs_and_never_a_crash_of_cadgens(self) -> None:
        def mistake() -> None:
            raise KeyError("the part they named")

        error = _caught(_user_calls(lambda: exec(compile("raise KeyError('x')", "/work/model.py", "exec"))))  # noqa: S102
        self.assertIsNone(analytics.signature(error, "build", bugs_only=True), "raised in their code")
        self.assertIsNone(analytics.signature(_caught(_user_calls(mistake)), "command", bugs_only=True))
        # An error cadgen raises on purpose, for what it was given, is not a bug either.
        self.assertIsNone(analytics.signature(_caught(lambda: int("not a number")), "command", bugs_only=True))
        # At a boundary that must never fail (a tool's call, a route), any error is a crash; one the
        # person's code defined is named only as theirs.
        defined: dict = {}
        exec(compile("class BracketError(Exception):\n    pass\n", "/work/errors.py", "exec"), defined)  # noqa: S102
        defined["BracketError"].__module__ = "errors_of_theirs"
        theirs = analytics.signature(defined["BracketError"]("secret"), "tool", tool="cad_show")
        self.assertEqual((theirs["type"], theirs["tool"]), ("<user>", "cad_show"))
        for stop in (KeyboardInterrupt(), SystemExit(1)):
            self.assertIsNone(analytics.signature(stop, "command"))
        self.assertIsNone(analytics.signature(KeyError("x"), "somewhere"))

    def test_an_error_cadgen_raises_on_purpose_is_never_its_bug_whatever_its_type(self) -> None:
        # cadgen tells a person their mistake in Python's own words ("@step returned a dict" is a TypeError):
        # a crash is only an error Python raised in cadgen's code, never one at a raise.
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        source = folder / "generation.py"
        source.write_text("def told():\n    raise TypeError(\n        '@step returned a dict')\n\n"
                          "def told_too(x):\n    if not x: raise KeyError('no such joint')\n\n"
                          "def broke():\n    return {}['tree']\n", encoding="utf-8")
        namespace: dict = {}
        exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), namespace)  # noqa: S102
        file_of = analytics._file_of
        ours = os.path.realpath(source)
        with mock.patch.object(analytics, "_file_of", lambda path: "cadgen/_internal/generation.py"
                               if os.path.realpath(path) == ours else file_of(path)):
            self.assertIsNone(analytics.signature(_caught(namespace["told"]), "build", bugs_only=True))
            self.assertIsNone(analytics.signature(_caught(lambda: namespace["told_too"](0)), "build", bugs_only=True))
            found = analytics.signature(_caught(_user_calls(namespace["broke"])), "build", bugs_only=True)
        self.assertEqual(found["frames"][-1], {"file": "cadgen/_internal/generation.py", "function": "broke", "line": 9})

    def test_what_a_model_asks_wrongly_of_cadgens_helpers_is_its_own_mistake(self) -> None:
        # cadgen's frame is the innermost, but only to name what the model asked for: a name build123d does
        # not have (still with Python's suggestion), a colour that is not a string.
        import traceback

        from cadgen import build123d as bd
        from cadgen.color import srgb

        missing = _caught(_user_calls(lambda: bd.Boxx))
        self.assertIsInstance(missing, AttributeError)
        self.assertIn("Did you mean: 'Box'?", "".join(traceback.format_exception_only(missing)))
        not_a_string = _caught(_user_calls(lambda: srgb(0x2E3742)))
        self.assertIsInstance(not_a_string, TypeError)
        self.assertIn("got int", str(not_a_string))
        for error in (missing, not_a_string):
            with self.subTest(error=type(error).__name__):
                self.assertIsNone(analytics.signature(error, "build", bugs_only=True))
        self.assertIs(bd.Box, __import__("build123d").Box, "a name it has is build123d's own")

    def test_the_other_end_leaving_or_the_persons_own_recursion_is_never_a_crash(self) -> None:
        def write() -> None:
            raise BrokenPipeError(32, "Broken pipe")

        # A reader that closed the command's own output (`| head`): its stdout is the pipe that broke.
        with mock.patch.object(analytics, "stdout_closed", return_value=True):
            self.assertIsNone(analytics.signature(_caught(write), "command", handled=False))
        # Another pipe the command wrote to (a child's stdin), and a route's own connection out, are cadgen's: a
        # page leaving a route is the response writer's to swallow, and never reaches here.
        with mock.patch.object(analytics, "stdout_closed", return_value=False):
            self.assertEqual(analytics.signature(_caught(write), "command", handled=False)["type"], "BrokenPipeError")
        for error in (ConnectionAbortedError(10053, "aborted"), ConnectionRefusedError()):
            self.assertEqual(analytics.signature(error, "route", handled=False)["type"], type(error).__name__)
        # Anywhere else it may be cadgen's: a tool's call, a request, a command's own connection.
        self.assertEqual(analytics.signature(ConnectionAbortedError(), "tool")["type"], "ConnectionAbortedError")
        self.assertEqual(analytics.signature(ConnectionResetError(), "command")["type"], "ConnectionResetError")

        # A RecursionError: whose cycle it is. This file stands in for cadgen's code.
        def ours() -> None:
            ours()

        def model() -> None:  # cadgen's wrapper, calling a model that calls itself through it
            _user_calls(model, "/work/model.py")()

        file_of, here = analytics._file_of, os.path.realpath(__file__)
        self.addCleanup(sys.setrecursionlimit, sys.getrecursionlimit())
        sys.setrecursionlimit(200)  # a short stack: each frame's file is looked up on disk
        with mock.patch.object(analytics, "_file_of", lambda path: "cadgen/authoring.py"
                               if os.path.realpath(path) == here else file_of(path)):
            theirs, mine = _caught(model), _caught(_user_calls(ours, "/work/model.py"))
            sys.setrecursionlimit(1000)
            for where, bugs_only in (("build", True), ("tool", False)):
                with self.subTest(where=where):
                    self.assertIsNone(analytics.signature(theirs, where, bugs_only=bugs_only), "theirs is in the cycle")
                    found = analytics.signature(mine, where, bugs_only=bugs_only)
                    self.assertEqual((found["type"], {frame["file"] for frame in found["frames"]}),
                                     ("RecursionError", {"cadgen/authoring.py"}), "the person's call is far outside it")

    def test_cadgens_own_module_gone_is_its_installation_removed_and_never_a_crash(self) -> None:
        import importlib

        # uv replacing the environment under a running command: a module of cadgen's is not there, nor is cadgen.
        import cadgen

        for missing in ("cadgen._gone_under_this_test", "cadgen._internal._gone_under_this_test"):
            with self.subTest(missing=missing):
                gone = _caught(lambda: importlib.import_module(missing))
                self.assertIsInstance(gone, ModuleNotFoundError)
                with mock.patch.object(cadgen, "__file__", str(Path(tempfile.gettempdir()) / "removed" / "__init__.py")):
                    self.assertIsNone(analytics.signature(gone, "command", handled=False))
                # The same import with cadgen still installed is a stale import: cadgen's bug, reported.
                self.assertEqual(analytics.signature(gone, "command", handled=False)["type"], "ModuleNotFoundError")
        # A module cadgen imports from another package that is not installed is cadgen's to fix; so is a name a
        # module of cadgen's does not have (the module is there).
        missing_dependency = _caught(lambda: importlib.import_module("cadgen_test_absent_dependency"))
        self.assertEqual(analytics.signature(missing_dependency, "command", handled=False)["type"], "ModuleNotFoundError")
        no_such_name = _caught(lambda: exec("from cadgen.analytics import no_such_name_here", {}))  # noqa: S102
        self.assertEqual(analytics.signature(no_such_name, "command", handled=False)["type"], "ImportError")

    def test_an_installed_package_that_is_not_cadgens_is_never_named(self) -> None:
        site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, site, ignore_errors=True)
        (site / "acme_private").mkdir()
        (site / "acme_private" / "__init__.py").write_text("def fail():\n    return {}['x']\n", encoding="utf-8")
        sys.path.insert(0, str(site))
        self.addCleanup(sys.path.remove, str(site))
        self.addCleanup(sys.modules.pop, "acme_private", None)
        import acme_private  # noqa: PLC0415

        places, ours = analytics._places()
        with mock.patch.object(analytics, "_places", return_value=(((os.path.realpath(site), "site"), *places), ours)):
            found = analytics.signature(_caught(acme_private.fail), "route")
        self.assertEqual([frame["file"] for frame in found["frames"]], ["<user>"])
        self.assertNotIn("acme", json.dumps(found))
        self.assertIn("build123d", ours, "cadgen's own dependencies are named")

    def test_a_crash_from_elsewhere_is_taken_only_if_this_module_would_have_made_it(self) -> None:
        good = {"where": "page", "type": "TypeError", "handled": False,
                "frames": [{"file": "assets/index-Bx3k2.js", "function": "Kt", "line": 1, "column": 48213,
                            "chunk_id": "0de4d024-c159-4f6d-b15a-cc4ef7a6856d"}]}
        self.assertTrue(analytics.valid_signature(good))
        self.assertTrue(analytics.valid_signature(analytics.died(-11)))
        # Windows ends a faulted process with its exception code (STATUS_ACCESS_VIOLATION): that is its exit
        # status, and the crash says it as a signal's would.
        self.assertEqual(analytics.died(0xC0000005)["status"], 0xC0000005)
        self.assertTrue(analytics.valid_signature(analytics.died(0xC0000005)))
        for status in (70000, -0xC0000005, 0x100000000):
            with self.subTest(status=status):
                self.assertNotIn("status", analytics.died(status))
                self.assertFalse(analytics.valid_signature({**analytics.died(-11), "status": status}))
        for bad in (
            {**good, "message": "Cannot read properties of undefined (reading 'secret')"},
            {**good, "frames": [{"file": "/Users/someone/secret.js", "function": "f", "line": 1}]},
            {**good, "frames": [{"file": "C:\\Users\\someone\\secret.js", "function": "f", "line": 1}]},
            {**good, "frames": [{"file": "../secret.js", "function": "f", "line": 1}]},
            {**good, "frames": [{"file": "a.js", "function": "make secret bracket", "line": 1}]},
            {**good, "frames": [{"file": "a.js", "function": "f", "line": -1}]},
            {**good, "frames": [{"file": "a.js", "function": "f", "line": 1, "source": "secret"}]},
            {**good, "frames": [{"file": "a.js", "function": "f", "line": 1, "chunk_id": "secret"}]},
            {**good, "where": "build"},  # only a page's frames name a chunk
            {**good, "frames": good["frames"] * (analytics.MAX_FRAMES + 1)},
            {**good, "type": "TypeError: secret"},
            {**good, "where": "elsewhere"},
            {**good, "handled": "no"},
            {**good, "tool": "rm -rf"},
            {**good, "status": True},
            "a crash",
        ):
            with self.subTest(bad=bad):
                self.assertFalse(analytics.valid_signature(bad))


class FailureReasonTest(unittest.TestCase):
    """Why a build or a snapshot failed (``build_failure``, ``snapshot_failure``): a word of a closed vocabulary,
    from what the error is and whose code raised it, never from what it says."""

    def setUp(self) -> None:
        # A module of cadgen's, as the frames place it: one that calls into a dependency, one that refuses what it
        # was given at a raise, and one with a mistake in it.
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        source = folder / "export.py"
        source.write_text("def export(write):\n    return write()\n\n"
                          "def refuse():\n    raise TypeError(\n        '@step returned a dict')\n\n"
                          "def broke():\n    return {}['tree']\n", encoding="utf-8")
        self.cadgen: dict = {}
        exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), self.cadgen)  # noqa: S102
        located, ours = analytics._located, os.path.realpath(source)
        placed = mock.patch.object(analytics, "_located", lambda path: ("cadgen", "cadgen/_internal/export.py")
                                   if os.path.realpath(path) == ours else located(path))
        placed.start()
        self.addCleanup(placed.stop)

    def test_a_builds_failure_is_named_by_what_failed_and_whose_code_raised_it(self) -> None:
        import functools
        import importlib

        from PIL import Image

        kernel = functools.partial(Image.new, "NOT A MODE", (1, 1))  # a library refusing what it was asked
        child = type("ChildBuildError", (RuntimeError,), {"__module__": "cadgen.store.lazy"})
        raises = _raises
        cases = {
            "model_error": raises(ValueError("No module named secret: a message is never read")),
            "kernel_error": _user_calls(kernel),
            "refused": _user_calls(self.cadgen["refuse"]),
            "export_error": lambda: self.cadgen["export"](kernel),
            "bug": _user_calls(self.cadgen["broke"]),
            "script_error": lambda: compile("def (", "/work/secret_model.py", "exec"),
            "missing_module": _user_calls(lambda: importlib.import_module("secret_missing_module")),
            "missing_file": _user_calls(lambda: open("/nonexistent/secret.step", encoding="utf-8")),
            "io_error": raises(PermissionError("locked")),
            "timeout": raises(TimeoutError()),
            "memory": raises(MemoryError()),
            "child_failed": raises(child("child model secret_arm failed")),
        }
        for reason, call in cases.items():
            with self.subTest(reason=reason):
                error = _caught(call)
                self.assertEqual(analytics.build_failure(error), reason)
                # The same as a crash report finds: a bug, and only a bug, is cadgen's own mistake.
                self.assertEqual(analytics.signature(error, "build", bugs_only=True) is not None, reason == "bug")
        self.assertLessEqual(set(cases), analytics.BUILD_FAILURES)
        # A name a module does not have is the model's mistake, not a module missing from the machine.
        misspelled = _caught(_user_calls(lambda: exec("from os import secret_name_os_does_not_have")))
        self.assertNotIsInstance(misspelled, ModuleNotFoundError)
        self.assertEqual(analytics.build_failure(misspelled), "model_error")

    def test_a_reason_cadgen_names_where_it_raises_stands_but_never_over_a_bug(self) -> None:
        named = _caught(_raises(analytics.because(ValueError(), "export_error")))  # the person's frames say model_error
        self.assertEqual(analytics.build_failure(named), "export_error")
        error = _caught(_user_calls(self.cadgen["broke"]))
        analytics.because(error, "missing_file")
        self.assertEqual(analytics.build_failure(error), "bug")
        # The innermost name stands; one outside the vocabulary names nothing.
        twice = analytics.because(analytics.because(ValueError(), "timeout"), "memory")
        self.assertEqual(analytics.build_failure(twice), "timeout")
        self.assertEqual(analytics.build_failure(analytics.because(ValueError(), "Secret words")), "other")
        self.assertEqual(analytics.build_failure(ValueError()), "other", "no frames: whose code is unknown")

    def test_a_snapshots_failure_is_what_it_was_doing_unless_the_error_says_more(self) -> None:
        playwright_timeout = type("TimeoutError", (Exception,), {"__module__": "playwright._impl._errors"})
        route = type("RouteFileError", (RuntimeError,), {"__module__": "cadgen.snapshot_core", "status": 404})
        for error, otherwise, reason in (
            (_caught(_user_calls(self.cadgen["broke"])), "input_error", "bug"),
            (analytics.because(RuntimeError(), "browser"), "render_error", "browser"),
            (FileNotFoundError("/w/secret.step"), "input_error", "no_file"),
            (route("no such file"), "bad_request", "no_file"),
            (playwright_timeout(), "render_error", "timeout"),
            (MemoryError(), "render_error", "memory"),
            (ValueError("bad camera"), "bad_request", "bad_request"),
            (ValueError("bad camera"), "a word of tomorrow", "other"),
        ):
            with self.subTest(error=type(error).__name__, otherwise=otherwise):
                self.assertEqual(analytics.snapshot_failure(error, otherwise), reason)
                self.assertIn(reason, analytics.SNAPSHOT_FAILURES)


class _Recording(unittest.TestCase):
    """A recorder that shares, sending into ``self.sent``."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp), "DO_NOT_TRACK": "",
                                                   "CADGEN_TELEMETRY": ""})
        environment.start()
        self.addCleanup(environment.stop)
        analytics.choose(True, by="cli", path=self.tmp / "settings.json")
        self.sent: list[dict] = []
        self.recorder = analytics.Recorder(path=self.tmp / "settings.json", send=lambda payload: self.sent.append(payload) or True)

    def crashes(self) -> list[dict]:
        self.assertTrue(self.recorder.flush())
        return [event for event in self.sent[-1]["events"] if event["name"] == "exception"]


class RecorderCrashTest(_Recording):
    def test_the_same_crash_is_sent_once_with_how_many_times_it_happened(self) -> None:
        for _ in range(3):
            self.recorder.crashed(_caught(_cadgen_bug), "tool", tool="cad_show")
        self.recorder.crashed(analytics.died(-9))
        self.recorder.crashed({"where": "page", "type": "TypeError", "handled": False, "frames": [], "message": "secret"})
        crashes = self.crashes()
        self.assertEqual([(crash["type"], crash["count"]) for crash in crashes], [("KeyError", 3), ("WorkerDied", 1)])
        self.assertEqual(crashes[1]["status"], -9)
        # Past a batch's room, crashes wait for the next; past a window's, a new one is not counted.
        with mock.patch.object(analytics, "CRASHES_PER_BATCH", 1), mock.patch.object(analytics, "CRASHES_PENDING", 2):
            for status in (1, 2, 3):
                self.recorder.crashed(analytics.died(status))
            self.assertEqual([crash["status"] for crash in self.crashes()], [1])
            self.assertEqual([crash["status"] for crash in self.crashes()], [2])
            self.assertFalse(self.recorder.flush())

    def test_a_process_sends_its_crashes_and_a_command_hands_its_own_over(self) -> None:
        noted: list[dict] = []
        analytics.collect_crashes(noted.append)
        self.addCleanup(analytics.collect_crashes, None)
        analytics.report(_caught(_cadgen_bug), "route")
        analytics.report(_caught(lambda: int("x")), "command", bugs_only=True)  # raised on purpose: none
        self.assertEqual([crash["where"] for crash in noted], ["route"])
        analytics.collect_crashes(None)
        with mock.patch.object(client, "hand_over") as handed:
            analytics.report(_caught(_cadgen_bug), "command", handled=False)
        [counts] = [call.args[0] for call in handed.call_args_list]
        self.assertEqual([(crash["where"], crash["handled"]) for crash in counts["crashes"]], [("command", False)])
        # Reporting never fails what failed.
        with mock.patch.object(client, "hand_over", side_effect=RuntimeError("broken")):
            analytics.report(_caught(_cadgen_bug), "command")


class ServerCrashTest(_Recording):
    """The CAD app: a request that fails for no reason its client gave is a crash; a tool's own failure is not."""

    def serve(self):
        from cadgen.mcp.server import Server
        from cadgen.mcp.ui import AppPage
        from cadgen.viewer.recents import RecentStore

        (self.tmp / "app").mkdir(exist_ok=True)
        server = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state"), analytics=self.recorder)
        server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "codex-mcp-client", "version": "0.159.0"}}, None)
        return server

    def call(self, server, name: str, arguments: dict | None = None):
        from cadgen.mcp.protocol import RequestContext

        return server.handle("tools/call", {"name": name, "arguments": arguments or {}}, RequestContext(1, {"threadId": "t"}))

    def test_a_tool_that_breaks_is_answered_as_ever_and_counted_as_a_crash(self) -> None:
        from cadgen.mcp.protocol import RpcError
        from cadgen.mcp.server import Server

        server = self.serve()
        self.assertTrue(self.call(server, "cad_show", {"path": str(self.tmp / "missing.step")}).get("isError"))  # its own failure
        with self.assertRaises(RpcError):
            self.call(server, "cad_no_such_tool")  # the client's mistake
        with mock.patch.object(Server, "_tool_cad_show", side_effect=KeyError("secret part")):
            with self.assertRaises(KeyError):  # the protocol answers it as an internal error (protocol.Connection)
                self.call(server, "cad_show", {"path": "a.step"})
        [crash] = self.crashes()
        self.assertEqual((crash["where"], crash["tool"], crash["type"], crash["count"]), ("tool", "cad_show", "KeyError", 1))
        self.assertNotIn("secret", json.dumps(self.sent))


class CommandCrashTest(unittest.TestCase):
    """A command sends nothing itself: its crash is handed to a running daemon, as its snapshots are."""

    def setUp(self) -> None:
        analytics.collect_crashes(None)
        handed = mock.patch.object(client, "hand_over")
        self.handed = handed.start()
        self.addCleanup(handed.stop)

    def crashes(self) -> list[dict]:
        return [crash for call in self.handed.call_args_list for crash in call.args[0].get("crashes", ())]

    def test_a_command_that_fails_past_its_own_report_is_a_crash_and_still_fails(self) -> None:
        from cadgen import cli

        with mock.patch("cadgen.cli.telemetry.main", side_effect=_caught(_cadgen_bug).__class__("secret")), \
                mock.patch.object(cli, "_tell"), self.assertRaises(KeyError):
            cli.main(["telemetry", "status"])
        self.assertEqual([(crash["where"], crash["handled"]) for crash in self.crashes()], [("command", False)])

    @unittest.skipIf(sys.platform == "win32", "Windows has no SIGPIPE, and says a closed pipe is EINVAL")
    def test_a_command_whose_output_is_closed_stops_quietly_and_reports_nothing(self) -> None:
        import subprocess

        # `cadgen ... | head`, its reader gone before it writes: no traceback, the exit a shell gives
        # `yes | head`, and nothing handed over, which a command would do through `report`.
        read, write = os.pipe()
        os.close(read)
        code = ("import sys\nfrom cadgen import analytics, cli\n"
                "analytics.report = lambda *a, **k: sys.stderr.write('reported\\n')\n"
                "cli._run = lambda *a: sys.stdout.write('x' * 1_000_000) and 0\n"
                "sys.exit(cli.main(['telemetry', 'status']))\n")
        try:
            done = subprocess.run([sys.executable, "-c", code], stdout=write, stderr=subprocess.PIPE,
                                  env={**os.environ, "CADGEN_TELEMETRY": "0"}, timeout=60)
        finally:
            os.close(write)
        self.assertEqual((done.returncode, done.stderr), (141, b""))
        # Another pipe it wrote to (a child that died before reading its stdin) is a failure like any other: said,
        # and the command fails, its own output still open.
        code = ("import sys\nfrom cadgen import cli\n"
                "def run(*a):\n    raise BrokenPipeError(32, 'Broken pipe')\n"
                "cli._run = run\nsys.exit(cli.main(['telemetry', 'status']))\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, env={**os.environ, "CADGEN_TELEMETRY": "0"},
                              timeout=60)
        self.assertEqual(done.returncode, 1)
        self.assertIn(b"BrokenPipeError", done.stderr)

    def test_a_commands_reported_failure_is_a_crash_only_when_it_is_a_mistake_in_cadgens_code(self) -> None:
        import io

        from cadgen._internal.cli_from_function import emit

        def told() -> None:
            raise ValueError("no such file: /home/someone/secret.step")

        for invoke in (told, _cadgen_bug):
            emit(invoke, prog="cadgen step build", as_json=True, stdout=io.StringIO())
        [crash] = self.crashes()
        self.assertEqual((crash["where"], crash["type"], crash["frames"][-1]["file"]), ("command", "KeyError", "cadgen/analytics.py"))


if __name__ == "__main__":
    unittest.main()
