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

        # A page that left a route mid-reply, a reader that closed a command's output (`| head`).
        for error, where in ((ConnectionAbortedError(10053, "aborted"), "route"), (ConnectionResetError(), "route"),
                             (_caught(write), "command")):
            with self.subTest(type=type(error).__name__, where=where):
                self.assertIsNone(analytics.signature(error, where, handled=False))
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
