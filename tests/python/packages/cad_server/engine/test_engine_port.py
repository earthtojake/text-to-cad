"""The device's page links outlive its engine: one HTTP port (``--port``, else ``CAD_ENGINE_PORT``,
else 3245 or the port it rolled to when 3245 was another's, remembered) and the user's one page token,
the same at every start until ``cad server --rotate-token``. A named port another process holds
is refused by name, and the device's port is rolled from it: another engine on it -- of another
engine folder, as 0.8's server is to 0.10 -- is asked nothing, as any program is. One engine a
device: a client of another release attaches to the engine running, and starts the current
installation's, never its own."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def held_port(test: unittest.TestCase) -> int:
    """A free port, then held by a plain listener of this process's: another program's."""
    holder = socket.socket()
    test.addCleanup(holder.close)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    return holder.getsockname()[1]


def other_installation(root: Path) -> str:
    """The interpreter of a second installation: a virtual environment of its own (its own
    ``sys.prefix``, so its own engine, ``daemon._tag``) that imports what this one does."""
    import sysconfig

    folder = root / "other"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(folder)], check=True)
    (site,) = (folder / "Lib" / "site-packages",) if os.name == "nt" else folder.glob("lib/python*/site-packages")
    (site / "inherit.pth").write_text(f"import site; site.addsitedir({sysconfig.get_paths()['purelib']!r})\n",
                                      encoding="utf-8")
    return str(folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))


class Listener:
    """What ``daemon.bind``'s ``listen`` makes, in process: a plain listener on ``port``."""

    def __init__(self, port: int, token: str) -> None:
        self.socket = socket.socket()
        try:
            self.socket.bind(("127.0.0.1", port))
        except OSError:
            self.socket.close()
            raise
        self.socket.listen(1)
        self.port, self.token = self.socket.getsockname()[1], token


def listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
    except OSError:
        return False
    return True


class EnginePortTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="eport-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        environment = {key: value for key, value in os.environ.items() if key != "CAD_ENGINE_PORT"}
        # The test's own default port (``daemon.default_port``): nothing here touches the machine's 3245.
        self.default = free_port()
        self.env = engine_daemon.watched({**environment, "PYTHONPATH": str(SRC),
                                          "CAD_ENGINE_DEFAULT_PORT": str(self.default),
                                          "CAD_ENGINE_DIR": str(self.root / "engine"),
                                          "CAD_STATE_DIR": str(self.root / "state"),
                                          "CAD_CACHE_DIR": str(self.root / "cache")},
                                         self.addCleanup)
        self.addCleanup(self.answering)
        self.addCleanup(self.stop)

    def cli(self, *args: str, python: str = sys.executable, **extra: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([python, "-m", "cad_server.engine", *args], env={**self.env, **extra})

    def stop(self, python: str = sys.executable) -> None:
        done = self.cli("stop", python=python)
        self.assertEqual(done.returncode, 0, done.stderr)

    def started(self, python: str = sys.executable, **extra: str) -> subprocess.CompletedProcess:
        """The viewer's launcher, run: it starts (or reuses) its installation's engine and its page."""
        return engine_daemon.run([python, "-m", "cad_server.viewer", "--api-only", "--json"],
                                 env={**self.env, **extra}, cwd=self.root)

    def launch(self, python: str = sys.executable, **extra: str) -> dict:
        """The engine's page, started (or reused) by the viewer's launcher: its port, token and pid."""
        done = self.started(python, **extra)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def answering(self, *expected: Path) -> None:
        """Await the engines whose doors answer in the test's engine folder being ``expected``."""
        from cad.engine import client

        deadline = time.monotonic() + 30
        while {door for door in (self.root / "engine").glob("*.port" if os.name == "nt" else "*.door")
               if client._answering(door)} != set(expected):
            self.assertLess(time.monotonic(), deadline, f"only {expected} answer")
            time.sleep(0.05)

    def ours(self) -> Path:
        """The engine's door in the test's engine folder (on Windows, its port file)."""
        from cad.engine import places

        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": self.env["CAD_ENGINE_DIR"]}):
            return places.address()

    def server(self, *args: str, **extra: str) -> subprocess.Popen:
        """``cad server ARGS`` in the background, once its door answers; ``extra``: its environment."""
        from cad.engine import client, places

        env = {**self.env, **extra}
        process = subprocess.Popen([sys.executable, "-m", "cad_server.engine", "server", *args], env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(engine_daemon.reap, process)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_DIR": env["CAD_ENGINE_DIR"]}):
            deadline = time.monotonic() + 60
            while (found := client._connect(places.address())) is None:
                self.assertIsNone(process.poll(), "the server exited before its door answered")
                self.assertLess(time.monotonic(), deadline, "the server's door answered")
                time.sleep(0.05)
            found.close()
        return process

    def record(self) -> dict:
        """This installation's engine record, or ``{}`` with none."""
        found = [path for path in (self.root / "state" / "engines").glob("*.json")]
        if not found:
            return {}
        (found,) = found
        if os.name != "nt":
            self.assertEqual(found.stat().st_mode & 0o777, 0o600)
        return json.loads(found.read_text(encoding="utf-8"))

    def token(self) -> str:
        """The user's page token, as its file holds it."""
        found = self.root / "state" / "engines" / "token"
        if os.name != "nt":
            self.assertEqual(found.stat().st_mode & 0o777, 0o600)
        return found.read_text(encoding="utf-8").strip()

    @staticmethod
    def ask(port: int, route: str, **headers: str) -> tuple[int, dict, bytes]:
        """``GET route`` of the engine on ``port``."""
        import http.client

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        try:
            connection.request("GET", route, headers={name.replace("_", "-"): value for name, value in headers.items()})
            answer = connection.getresponse()
            return answer.status, dict(answer.getheaders()), answer.read()
        finally:
            connection.close()

    def bound(self, default: int, **extra: str) -> tuple[Listener, dict]:
        """``daemon.bind`` in this process, nothing named, its default ``default``: its listener
        (closed at the end) and where its port came from. ``extra``: this process's environment."""
        from cad_server.engine import daemon, registry

        environment = {key: value for key, value in os.environ.items() if key != "CAD_ENGINE_PORT"}
        with mock.patch.dict(os.environ, {**environment, "CAD_ENGINE_DIR": self.env["CAD_ENGINE_DIR"],
                                          "CAD_ENGINE_DEFAULT_PORT": str(default), **extra},
                             clear=True), \
                mock.patch.object(registry, "FACTORY", lambda: registry.Registry(self.root / "state")):
            server, where = daemon.bind("127.0.0.1", None, Listener)
        self.addCleanup(server.socket.close)
        return server, where

    def remembered(self) -> int | None:
        from cad.engine import places
        from cad_server.engine import registry

        return registry.Registry(self.root / "state").engine(places.NAME).get("port")

    def test_the_default_port_is_3245_and_taken_when_free(self) -> None:
        from cad_server.engine import daemon

        self.assertEqual(daemon.DEFAULT_PORT, 3245)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_DEFAULT_PORT": ""}):
            self.assertEqual(daemon.default_port(), 3245)
        self.assertEqual(self.launch()["port"], self.default)  # the test's stand-in for 3245, free
        self.assertIn(f"serving http://127.0.0.1:{self.default} (the default port)", self.cli("status").stdout)

    def test_a_port_another_program_holds_is_refused_by_name_and_leaves_no_engine(self) -> None:
        port = held_port(self)
        done = self.started(CAD_ENGINE_PORT=str(port))
        self.assertEqual(done.returncode, 1, done.stdout)
        found = json.loads(done.stdout)  # the launch answers in JSON: its failure is its one document there
        said = found["error"]
        self.assertEqual(found["reason"], "failed")
        self.assertRegex(said, rf"^port {port} is held by (.+ \(pid (\d+)\)|another process): "
                               r"stop it, or start the server with another CAD_ENGINE_PORT$")
        if os.name != "nt":  # the system names the holder: this process
            self.assertIn(f" (pid {os.getpid()}): ", said)
        self.answering()

    def test_a_request_s_own_held_port_is_refused_and_the_running_engine_goes_on(self) -> None:
        # An engine already running for other clients (no page yet): one viewer's --port, held by
        # another program, refuses that viewer and never stops the engine under the others.
        own = free_port()
        before = engine_daemon.run([sys.executable, "-c", "from cad.engine import client; "
                                    "print(client.request({'op': 'pid'})['pid'])"],
                                   env={**self.env, "CAD_ENGINE_PORT": str(own)})
        self.assertEqual(before.returncode, 0, before.stderr)
        port = held_port(self)
        done = engine_daemon.run([sys.executable, "-m", "cad_server.viewer", "--api-only", "--json", "--port", str(port)],
                                 env=self.env, cwd=self.root)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertRegex(json.loads(done.stdout)["error"], rf"^port {port} is held by .+: stop it, or pass another --port$")
        after = engine_daemon.run([sys.executable, "-c", "from cad.engine import client; "
                                   "print((client.request({'op': 'pid'}, start=False) or {}).get('pid'))"], env=self.env)
        self.assertEqual(after.stdout.strip(), before.stdout.strip(), "the same engine answers")
        self.assertEqual(self.launch()["port"], own, "and serves the next page on its own port")

    def test_cadgen_server_on_a_held_port_fails_at_once_and_leaves_no_engine(self) -> None:
        port = held_port(self)
        done = self.cli("server", "--port", str(port))  # no request is ever sent: it binds at its start
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertRegex(done.stderr.strip().splitlines()[-1],
                         rf"^cad: port {port} is held by .+: stop it, or pass another --port$")
        self.answering()

    def test_cadgen_server_beside_a_running_engine_says_so_and_a_port_it_cannot_take_fails(self) -> None:
        running = self.launch(CAD_ENGINE_PORT=str(free_port()))
        asked = free_port()
        done = self.cli("server", "--port", str(asked))
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("the engine server is already running", done.stderr)
        self.assertFalse(listening(asked), "nothing serves the port it named")
        plain = self.cli("server")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertIn("already running", plain.stderr)
        self.assertEqual(self.launch()["pid"], running["pid"])
        bad = self.cli("server", "--port", "70000")
        self.assertEqual(bad.returncode, 2)
        self.assertRegex(bad.stderr.strip(), r"^[^:]*server: --port must be between 0 and 65535$", "its name said once")

    def test_a_held_default_rolls_to_the_next_free_port_says_so_once_and_keeps_it(self) -> None:
        default = held_port(self)  # the test's default, held by this process: another program's
        extra = {"CAD_ENGINE_DEFAULT_PORT": str(default)}
        done = self.started(**extra)
        self.assertEqual(done.returncode, 0, done.stderr)
        port = json.loads(done.stdout)["port"]
        self.assertTrue(default < port <= default + 64, port)
        pid = str(os.getpid()) if os.name != "nt" else r"\d+"  # the system names the holder
        said = rf"the engine serves on port {port} and keeps it for its links: {default} is in use by (.+pid {pid}\)|another process)"
        self.assertRegex(done.stderr, rf"(?m)^cad: {said}$")
        self.assertEqual(self.record()["port"], port)
        status = self.cli("status", **extra).stdout
        self.assertRegex(status, rf"serving http://127\.0\.0\.1:{port} \(rolled from {default} because .+ holds it\)")
        self.assertRegex(status, rf"(?m)^  {said}$")
        self.stop()
        again = self.started(**extra)  # the remembered port: the same links, nothing said
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(json.loads(again.stdout)["port"], port)
        self.assertNotIn(f"{default} is in use", again.stderr + self.cli("status", **extra).stdout)

    def test_the_installation_port_returns_to_a_free_default_and_rolls_from_a_held_remembered_one(self) -> None:
        from cad.engine import places
        from cad_server.engine import registry

        default, remembered = held_port(self), free_port()
        registry.Registry(self.root / "state").put_token("t" * 43)
        registry.Registry(self.root / "state").put_engine(places.NAME, {"port": remembered})
        server, where = self.bound(default)  # the default held, the remembered port free: used, nothing said
        self.assertEqual((server.port, where["source"], "notice" in where), (remembered, "rolled", False))
        self.assertEqual(server.token, "t" * 43)
        server.socket.close()
        held = Listener(remembered, "")  # the remembered port held too: the roll starts from it
        self.addCleanup(held.socket.close)
        server, where = self.bound(default)
        self.assertGreater(server.port, remembered)
        self.assertRegex(where["notice"], rf"^the engine serves on port {server.port} and keeps it for its links: "
                                          rf"{remembered} is in use by .+$")
        self.assertEqual(self.remembered(), server.port)
        server.socket.close()
        default = free_port()  # the default free again: taken back, the rolled port forgotten
        rolled = self.remembered()
        server, where = self.bound(default)
        self.assertEqual((server.port, where["source"]), (default, "default"))
        self.assertEqual(where["notice"], f"back on the default port {default}: links made on {rolled} no longer work")
        self.assertIsNone(self.remembered())
        self.assertEqual(server.token, "t" * 43)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "a file's mode is POSIX's, and refuses no one running as root")
    def test_a_page_token_that_cannot_be_read_serves_nothing_and_is_left_as_it_is(self) -> None:
        from cad_server.engine import registry

        registry.Registry(self.root / "state").put_token("t" * 43)
        token = self.root / "state" / "engines" / "token"
        token.chmod(0)
        self.addCleanup(token.chmod, 0o600)
        with self.assertRaisesRegex(ValueError, r"^the page token \S+/engines/token cannot be read \(Permission denied, "
                                                r"mode 0000\): make it this user's to read \(mode 0600\) or remove it"):
            self.bound(free_port())
        token.chmod(0o600)
        self.assertEqual(self.token(), "t" * 43, "never replaced: the links made with it still work")

    def test_another_engine_on_the_default_port_is_asked_nothing_and_rolled_from(self) -> None:
        """An engine of another engine folder on the device's port -- as 0.8's server is to 0.10's -- is
        rolled from as any program is, said as a text-to-cad's, never asked to stop: it runs on."""
        default = free_port()
        other = {"CAD_ENGINE_DIR": str(self.root / "other-engine"), "CAD_STATE_DIR": str(self.root / "other-state"),
                 "CAD_ENGINE_STANDBY": "0"}
        theirs = self.server("--port", str(default), **other)
        self.addCleanup(lambda: self.cli("stop", **other))
        done = self.started(CAD_ENGINE_DEFAULT_PORT=str(default))
        self.assertEqual(done.returncode, 0, done.stderr)
        port = json.loads(done.stdout)["port"]
        self.assertTrue(default < port <= default + 64, port)
        (said,) = [line for line in done.stderr.splitlines() if line.startswith("cad: the engine serves on port ")]
        self.assertTrue(said.startswith(f"cad: the engine serves on port {port} and keeps it for its links: "
                                        f"{default} is in use by "), said)
        if os.name != "nt":  # the system names the holder by its command line
            self.assertIn("another cad-server (", said)
            self.assertIn(f"pid {theirs.pid})", said)
        self.assertIsNone(theirs.poll(), "never asked to stop: it runs on")
        self.assertTrue(listening(default))

    def test_a_client_of_another_release_attaches_and_starts_the_current_installation_s_engine(self) -> None:
        """One engine a device: a client of another installation (an app's newer plugin) attaches to the
        engine running, whatever its release, and with none running starts the current installation's,
        never its own."""
        from cad_server._internal import installations

        found = installations.targets()
        if found is None:
            self.skipTest("this interpreter has no console script to register")
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": self.env["CAD_STATE_DIR"]}):
            installations.register("1.0.0", found)
            installations.point("1.0.0")
        theirs = other_installation(self.root)  # another release's client, its environment its own
        first = self.launch(CAD_ENGINE_PORT=str(free_port()))
        attached = self.launch(theirs)
        self.assertEqual(attached["pid"], first["pid"], "it attaches to the engine running")
        self.stop()
        started = self.launch(theirs)
        self.assertNotEqual(started["pid"], first["pid"])
        status = json.loads(self.cli("status", "--json", python=theirs).stdout)
        self.assertEqual(os.path.realpath(status["prefix"]), os.path.realpath(found[2]),
                         "it starts the current installation's engine, never its own")
        self.answering(self.ours())

    def test_a_named_port_wins_and_rotate_token_replaces_the_token(self) -> None:
        named = free_port()
        first = self.launch(CAD_ENGINE_PORT=str(named))
        self.assertEqual(first["port"], named)
        self.assertNotIn("port", self.record(), "a named port is never remembered")
        self.assertEqual(first["token"], self.token())
        # The link a launch prints and the session a browser is given for it outlive the engine and
        # its port: the next engine, on another port of the host, admits both.
        from urllib.parse import parse_qs, urlsplit

        from cad_server.viewer.engine_app import TOKEN_NEEDED_PAGE

        link = parse_qs(urlsplit(first["url"]).query)["token"][0]
        status, headers, _ = self.ask(named, f"/api/v1/server?token={link}")
        self.assertEqual(status, 200)
        cookie = headers["set-cookie"].split(";")[0]
        self.stop()
        moved = self.launch(CAD_ENGINE_PORT=str(free_port()))
        self.assertNotEqual((moved["pid"], moved["port"]), (first["pid"], named))
        self.assertEqual(self.ask(moved["port"], "/api/v1/server", Cookie=cookie)[0], 200)
        self.assertEqual(self.ask(moved["port"], f"/api/v1/server?token={link}")[0], 200)
        self.stop()
        # --port on ``cad server`` outranks CAD_ENGINE_PORT; --rotate-token retires every link
        # and every session: each page then needs a new link. It destroys, so it asks first: where no one
        # can be asked (here), nothing is replaced and nothing starts without --yes.
        other = free_port()
        self.env["CAD_ENGINE_PORT"] = str(named)
        asked = self.cli("server", "--port", str(other), "--rotate-token")
        self.assertEqual(asked.returncode, 2, asked.stderr)
        self.assertIn(f"`python -m cad_server.engine server --rotate-token --port {other} --yes` says yes", asked.stderr)
        self.assertEqual(self.token(), first["token"])
        self.server("--port", str(other), "--rotate-token", "--yes")
        for headers in ({"Cookie": cookie}, {}):
            self.assertEqual(self.ask(other, "/" if headers else f"/?token={link}", Sec_Fetch_Dest="document",
                                      **headers)[::2], (403, TOKEN_NEEDED_PAGE))
        rotated = self.launch()
        self.assertEqual(rotated["port"], other)
        self.assertNotEqual(rotated["token"], first["token"])
        self.assertEqual(self.token(), rotated["token"])
        # While an engine runs, it takes the new token at once: every link and session before ends now, not at its
        # next start, and the command says the engine runs on.
        self.assertEqual(self.ask(other, f"/api/v1/server?token={rotated['token']}")[0], 200)
        again = self.cli("server", "--rotate-token", "--yes")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("in every version's server at once", again.stderr)
        self.assertIn("already running", again.stderr)
        self.assertNotEqual(self.token(), rotated["token"])
        self.assertEqual(self.ask(other, f"/api/v1/server?token={rotated['token']}")[0], 403, "the token before: ended")
        self.assertEqual(self.ask(other, f"/api/v1/server?token={self.token()}")[0], 200, "the new one, at once")
        # With --port too, a server already running: the token is replaced, which is what was asked -- exit 0.
        ported = self.cli("server", "--rotate-token", "--port", str(free_port()), "--yes")
        self.assertEqual(ported.returncode, 0, ported.stderr)
        self.assertIn("took the new token", ported.stderr)


class BuildBoundNoticeTest(unittest.TestCase):
    def test_a_roll_a_builds_page_made_is_said_by_the_next_build_once_and_by_no_status(self) -> None:
        """A build's page binds the port with no client's request (``models.register_page``): the
        next build's answer says the roll, once; a status asked meanwhile does not take it."""
        import io
        from unittest import mock

        from cad_server.engine import daemon

        said = "the engine serves on port 3246 and keeps it for its links: 3245 is in use by another process"

        class Engine:
            refusal, token, unsaid = None, "ab" * 16, said

            def handle(self, request: dict, send) -> None:
                send({"log": "building"})
                send({"ok": True})

            def ended(self, request: dict) -> None:  # the quiet hour's stamp (``Daemon.ended``)
                pass

        # Both transports' rule: on Windows a request carries the engine's token, as a client puts
        # it (``client._exchange``), and one without it is answered with nothing.
        for windows in (False, True):
            engine = Engine()

            def asked(op: str) -> list[dict]:
                out = io.BytesIO()
                line = json.dumps({"token": engine.token, "op": op}) + "\n"
                daemon._serve(engine, io.BytesIO(line.encode()), out)
                return [json.loads(line) for line in out.getvalue().splitlines()]

            with self.subTest(windows=windows), mock.patch.object(daemon, "WINDOWS", windows):
                self.assertEqual(asked("status"), [{"log": "building"}, {"ok": True}])
                self.assertEqual(asked("build"), [{"log": "building"}, {"ok": True, "notice": said}])
                self.assertEqual(asked("build"), [{"log": "building"}, {"ok": True}])


    def test_the_notice_is_said_on_stderr_after_what_stdout_has_printed_never_inside_it(self) -> None:
        """A command's output piped with its stderr (``2>&1``): stdout buffered, stderr not. The notice comes
        after the lines the command printed before the request, not ahead of them in the pipe."""
        import io

        from cad.engine import client

        class Pipe(io.RawIOBase):
            def __init__(self) -> None:
                self.bytes = bytearray()

            def writable(self) -> bool:
                return True

            def write(self, data: Any) -> int:
                self.bytes += bytes(data)
                return len(data)

        pipe = Pipe()
        out = io.TextIOWrapper(io.BufferedWriter(pipe, 1 << 16))  # a pipe's stdout: block-buffered
        err = io.TextIOWrapper(pipe, write_through=True)
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            print("structure: 270 parts")
            client._notice("the engine serves on port 3247 and keeps it for its links: 3245 is in use by another cad-server")
            print("  Base_SO101")
            out.flush()
        self.assertEqual(pipe.bytes.decode().splitlines(), [
            "structure: 270 parts", "cad: the engine serves on port 3247 and keeps it for its links: 3245 is in use by another cad-server",
            "  Base_SO101"])


class PortHolderTest(unittest.TestCase):
    def test_windows_console_tools_are_read_in_the_oem_code_page_and_a_failed_read_is_unknown(self) -> None:
        """``netstat`` and ``tasklist`` write in the console's OEM code page (cp950 on a zh-TW
        Windows), which UTF-8 under ``PYTHONUTF8=1`` cannot decode; a read that died leaves no
        output, and the holder is then unknown, never an error that ends ``cad setup`` (#758)."""
        from cad_server.engine import daemon

        said = {"netstat": "\u5354\u5b9a   \u672c\u6a5f\u4f4d\u5740\n  TCP    127.0.0.1:3245   0.0.0.0:0   LISTENING   4321\n",
                "tasklist": '"python.exe","4321","Console","1","52,000 K"\n'}
        asked = []

        def run(argv, **options):
            asked.append(options)
            return subprocess.CompletedProcess(argv, 0, stdout=said[argv[0]])

        with mock.patch.object(daemon, "WINDOWS", True), mock.patch("sys.platform", "win32"), \
                mock.patch.object(daemon.subprocess, "run", run):
            self.assertEqual(daemon.port_holder(3245), (4321, "python.exe", None))
            self.assertTrue(all(o["encoding"] == "oem" and o["errors"] == "replace" for o in asked))
            said["netstat"] = None
            self.assertEqual(daemon.port_holder(3245), (None, None, None))



class MirroredPortFileTest(unittest.TestCase):
    def test_on_windows_the_port_file_is_mirrored_where_0_10_s_clients_look_and_goes_with_the_engine(self) -> None:
        """0.10.0's clients look for the engine in the temporary folder (``places.appdata_engine_dir``): for
        one release the engine's port file is written there too, never over a 0.10.0 engine's that answers,
        and removed with its own (#759)."""
        from cad_server.engine import daemon

        root = Path(tempfile.mkdtemp(prefix="mirror-"))
        self.addCleanup(shutil.rmtree, root, True)
        own, old = root / "engine" / "engine.port", root / "temp" / "cad-engine"
        own.parent.mkdir()
        own.write_text("3245 tok\n", encoding="utf-8")
        with mock.patch.object(daemon, "port_path", return_value=own), \
                mock.patch("cad.engine.places.appdata_engine_dir", return_value=old):
            daemon._mirror(3245, "tok")
            self.assertEqual((old / "engine.port").read_text(encoding="utf-8"), "3245 tok\n")
            daemon._unmirror()
            self.assertFalse((old / "engine.port").exists())
            (old / "engine.port").write_text("3999 theirs\n", encoding="utf-8")
            with mock.patch.object(daemon, "_answers", return_value=True):
                daemon._mirror(3245, "tok")
                daemon._unmirror()
            self.assertEqual((old / "engine.port").read_text(encoding="utf-8"), "3999 theirs\n", "a 0.10 engine's own")
        with mock.patch("cad.engine.places.appdata_engine_dir", return_value=None):
            daemon._mirror(3245, "tok")  # elsewhere: nothing

if __name__ == "__main__":
    unittest.main()
