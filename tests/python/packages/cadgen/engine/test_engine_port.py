"""The device's page links outlive its engine: one HTTP port (``--port``, else ``CADGEN_ENGINE_PORT``,
else 3245 or the port it rolled to when 3245 was another's, remembered) and the user's one page token,
the same at every start until ``cadgen server --rotate-token``. A named port another process holds
is refused by name; another engine on it (an earlier cadgen's, its door another name) that nothing
uses is asked to stop, and one in use is rolled from. One engine a device: a client of another
release attaches to the engine running, and starts the current installation's, never its own."""

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
from unittest import mock

from tests.python.support import engine_daemon

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
# An earlier cadgen's engine's name in the engine folder (``EnginePortTest.earlier``).
EARLIER = "0123456789ab"


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
        environment = {key: value for key, value in os.environ.items() if key != "CADGEN_ENGINE_PORT"}
        # The test's own default port (``daemon.default_port``): nothing here touches the machine's 3245.
        self.default = free_port()
        self.env = engine_daemon.watched({**environment, "PYTHONPATH": str(SRC),
                                          "CADGEN_ENGINE_DEFAULT_PORT": str(self.default),
                                          "CADGEN_ENGINE_DIR": str(self.root / "engine"),
                                          "CADGEN_STATE_DIR": str(self.root / "state"),
                                          "CADGEN_CACHE_DIR": str(self.root / "cache")},
                                         self.addCleanup)
        self.addCleanup(self.stop)
        self.addCleanup(self.stop_every)

    def stop_every(self) -> None:
        """Every engine in the test's engine folder asked to stop, whatever version it runs as (each
        its own door, ``daemon._tag``), and awaited gone."""
        from cadgen.engine import daemon

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": self.env["CADGEN_ENGINE_DIR"]}):
            for door in (self.root / "engine").glob("*.port" if os.name == "nt" else "*.door"):
                daemon._ask(door, {"op": "stop"})
        self.answering()

    def cli(self, *args: str, python: str = sys.executable, **extra: str) -> subprocess.CompletedProcess:
        return engine_daemon.run([python, "-m", "cadgen.engine", *args], env={**self.env, **extra})

    def stop(self, python: str = sys.executable) -> None:
        done = self.cli("stop", python=python)
        self.assertEqual(done.returncode, 0, done.stderr)

    def started(self, python: str = sys.executable, **extra: str) -> subprocess.CompletedProcess:
        """The viewer's launcher, run: it starts (or reuses) its installation's engine and its page."""
        return engine_daemon.run([python, "-m", "cadgen.viewer", "--api-only", "--json"],
                                 env={**self.env, **extra}, cwd=self.root)

    def launch(self, python: str = sys.executable, **extra: str) -> dict:
        """The engine's page, started (or reused) by the viewer's launcher: its port, token and pid."""
        done = self.started(python, **extra)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def answering(self, *expected: Path) -> None:
        """Await the engines whose doors answer in the test's engine folder being ``expected``."""
        from cadgen.engine import client

        deadline = time.monotonic() + 30
        while {door for door in (self.root / "engine").glob("*.port" if os.name == "nt" else "*.door")
               if client._answering(door)} != set(expected):
            self.assertLess(time.monotonic(), deadline, f"only {expected} answer")
            time.sleep(0.05)

    def ours(self) -> Path:
        """The engine's door in the test's engine folder (on Windows, its port file)."""
        from cadgen.engine import places

        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": self.env["CADGEN_ENGINE_DIR"]}):
            return places.address()

    def earlier(self, port: int) -> tuple[Path, dict]:
        """An earlier cadgen's engine in the test's engine folder -- its door another name, a tag of 12
        hex digits as 0.8's engines named theirs --, serving on ``port``: its door and its status,
        stopped at the end."""
        from cadgen.engine import client, daemon

        code = (f"import sys; from cadgen.engine import daemon, places; places.NAME = daemon.NAME = {EARLIER!r}; "
                "sys.exit(daemon.main())")
        process = subprocess.Popen([sys.executable, "-c", code], env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(engine_daemon.reap, process)
        door = self.root / "engine" / f"{EARLIER}.{'port' if os.name == 'nt' else 'door'}"
        deadline = time.monotonic() + 60
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": self.env["CADGEN_ENGINE_DIR"]}):
            while (connection := client._connect(door)) is None:
                self.assertIsNone(process.poll(), "the earlier engine exited before its door answered")
                self.assertLess(time.monotonic(), deadline, "the earlier engine's door answered")
                time.sleep(0.05)
            served = client._exchange(connection, {"op": "http", "port": port}, address=door)
            self.assertEqual(served.get("url"), f"http://127.0.0.1:{port}", served)
            self.addCleanup(lambda: daemon._ask(door, {"op": "stop"}))
            return door, daemon._ask(door, {"op": "status"}) or {}

    def server(self, *args: str) -> None:
        """``cadgen server ARGS`` in the background, once its door answers."""
        from cadgen.engine import client, places

        process = subprocess.Popen([sys.executable, "-m", "cadgen.engine", "server", *args], env=self.env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(engine_daemon.reap, process)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": self.env["CADGEN_ENGINE_DIR"]}):
            deadline = time.monotonic() + 60
            while (found := client._connect(places.address())) is None:
                self.assertIsNone(process.poll(), "the server exited before its door answered")
                self.assertLess(time.monotonic(), deadline, "the server's door answered")
                time.sleep(0.05)
            found.close()

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
        """``GET route`` of the engine on ``port``, redirects not followed."""
        import http.client

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        try:
            connection.request("GET", route, headers={name.replace("_", "-"): value for name, value in headers.items()})
            answer = connection.getresponse()
            return answer.status, dict(answer.getheaders()), answer.read()
        finally:
            connection.close()

    def held(self, door: Path) -> None:
        """An app server's hold on the engine at ``door``, as ``client.hold`` asks one, kept to the end."""
        from cadgen.engine import client

        held = client._connect(door)
        self.addCleanup(held.close)
        message = {"op": "hold", "host": "codex"}
        if os.name == "nt":
            message = {"token": door.read_text(encoding="utf-8").split()[1], **message}
        held.writer.write((json.dumps(message) + "\n").encode())
        held.writer.flush()
        self.assertEqual(json.loads(held.reader.readline()), {"ok": True})

    def bound(self, default: int, **extra: str) -> tuple[Listener, dict]:
        """``daemon.bind`` in this process, nothing named, its default ``default``: its listener
        (closed at the end) and where its port came from. ``extra``: this process's environment."""
        from cadgen.engine import daemon, registry

        environment = {key: value for key, value in os.environ.items() if key != "CADGEN_ENGINE_PORT"}
        with mock.patch.dict(os.environ, {**environment, "CADGEN_ENGINE_DIR": self.env["CADGEN_ENGINE_DIR"],
                                          "CADGEN_ENGINE_DEFAULT_PORT": str(default), **extra},
                             clear=True), \
                mock.patch.object(registry, "FACTORY", lambda: registry.Registry(self.root / "state")):
            server, where = daemon.bind("127.0.0.1", None, Listener)
        self.addCleanup(server.socket.close)
        return server, where

    def remembered(self) -> int | None:
        from cadgen.engine import places, registry

        return registry.Registry(self.root / "state").engine(places.NAME).get("port")

    def test_the_default_port_is_3245_and_taken_when_free(self) -> None:
        from cadgen.engine import daemon

        self.assertEqual(daemon.DEFAULT_PORT, 3245)
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DEFAULT_PORT": ""}):
            self.assertEqual(daemon.default_port(), 3245)
        self.assertEqual(self.launch()["port"], self.default)  # the test's stand-in for 3245, free
        self.assertIn(f"serving http://127.0.0.1:{self.default} (the default port)", self.cli("status").stdout)

    def test_a_port_another_program_holds_is_refused_by_name_and_leaves_no_engine(self) -> None:
        port = held_port(self)
        done = self.started(CADGEN_ENGINE_PORT=str(port))
        self.assertEqual(done.returncode, 1, done.stdout)
        (said,) = done.stderr.strip().splitlines()[-1:]
        self.assertRegex(said, rf"^CAD Viewer: port {port} is held by (.+ \(pid (\d+)\)|another process): "
                               r"stop it, or start cadgen with another CADGEN_ENGINE_PORT$")
        if os.name != "nt":  # the system names the holder: this process
            self.assertIn(f" (pid {os.getpid()}): ", said)
        self.answering()

    def test_a_request_s_own_held_port_is_refused_and_the_running_engine_goes_on(self) -> None:
        # An engine already running for other clients (no page yet): one viewer's --port, held by
        # another program, refuses that viewer and never stops the engine under the others.
        own = free_port()
        before = engine_daemon.run([sys.executable, "-c", "from cadgen.engine import client; "
                                    "print(client.request({'op': 'pid'})['pid'])"],
                                   env={**self.env, "CADGEN_ENGINE_PORT": str(own)})
        self.assertEqual(before.returncode, 0, before.stderr)
        port = held_port(self)
        done = engine_daemon.run([sys.executable, "-m", "cadgen.viewer", "--api-only", "--json", "--port", str(port)],
                                 env=self.env, cwd=self.root)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertRegex(done.stderr.strip().splitlines()[-1],
                         rf"^CAD Viewer: port {port} is held by .+: stop it, or pass another --port$")
        after = engine_daemon.run([sys.executable, "-c", "from cadgen.engine import client; "
                                   "print((client.request({'op': 'pid'}, start=False) or {}).get('pid'))"], env=self.env)
        self.assertEqual(after.stdout.strip(), before.stdout.strip(), "the same engine answers")
        self.assertEqual(self.launch()["port"], own, "and serves the next page on its own port")

    def test_cadgen_server_on_a_held_port_fails_at_once_and_leaves_no_engine(self) -> None:
        port = held_port(self)
        done = self.cli("server", "--port", str(port))  # no request is ever sent: it binds at its start
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertRegex(done.stderr.strip().splitlines()[-1],
                         rf"^cadgen: port {port} is held by .+: stop it, or pass another --port$")
        self.answering()

    def test_cadgen_server_beside_a_running_engine_says_so_and_a_port_it_cannot_take_fails(self) -> None:
        running = self.launch(CADGEN_ENGINE_PORT=str(free_port()))
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
        extra = {"CADGEN_ENGINE_DEFAULT_PORT": str(default)}
        done = self.started(**extra)
        self.assertEqual(done.returncode, 0, done.stderr)
        port = json.loads(done.stdout)["port"]
        self.assertTrue(default < port <= default + 64, port)
        pid = str(os.getpid()) if os.name != "nt" else r"\d+"  # the system names the holder
        said = rf"{default} is held by (.+pid {pid}\)|another process); the engine serves on {port} and keeps it"
        self.assertRegex(done.stderr, rf"(?m)^cadgen: {said}$")
        self.assertEqual(self.record()["port"], port)
        status = self.cli("status", **extra).stdout
        self.assertRegex(status, rf"serving http://127\.0\.0\.1:{port} \(rolled from {default} because .+ holds it\)")
        self.assertRegex(status, rf"(?m)^  {said}$")
        self.stop()
        again = self.started(**extra)  # the remembered port: the same links, nothing said
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(json.loads(again.stdout)["port"], port)
        self.assertNotIn(f"{default} is held", again.stderr + self.cli("status", **extra).stdout)

    def test_the_installation_port_returns_to_a_free_default_and_rolls_from_a_held_remembered_one(self) -> None:
        from cadgen.engine import places, registry

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
        self.assertRegex(where["notice"], rf"^{remembered} is held by .+; the engine serves on {server.port} "
                                          "and keeps it$")
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
        from cadgen.engine import registry

        registry.Registry(self.root / "state").put_token("t" * 43)
        token = self.root / "state" / "engines" / "token"
        token.chmod(0)
        self.addCleanup(token.chmod, 0o600)
        with self.assertRaisesRegex(ValueError, r"^the page token \S+/engines/token cannot be read \(Permission denied, "
                                                r"mode 0000\): make it this user's to read \(mode 0600\) or remove it"):
            self.bound(free_port())
        token.chmod(0o600)
        self.assertEqual(self.token(), "t" * 43, "never replaced: the links made with it still work")

    def test_an_unused_earlier_engine_on_the_port_is_asked_to_stop_and_its_port_taken(self) -> None:
        port = free_port()
        door, theirs = self.earlier(port)
        ours = self.launch(CADGEN_ENGINE_PORT=str(port))
        self.assertEqual(ours["port"], port)
        self.assertNotEqual(ours["pid"], theirs["pid"])
        # One token for every engine: a link outlives an update.
        self.assertEqual(ours["token"], self.token())
        self.answering(self.ours())

    def test_an_earlier_engine_in_use_is_refused_when_named_and_else_rolled_from(self) -> None:
        from cadgen.engine import previous

        port = free_port()
        door, theirs = self.earlier(port)
        self.held(door)  # an app server's hold on it, as ``client.hold`` asks one
        done = self.started(CADGEN_ENGINE_PORT=str(port))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertEqual(done.stderr.strip().splitlines()[-1],
                         f"CAD Viewer: port {port} is held by cadgen {previous.version()}'s engine "
                         f"(pid {theirs['pid']}), still in use by 1 app server: quit that app or run `cadgen stop` "
                         "with that version")
        self.answering(door)
        server, where = self.bound(port)  # its port the default: rolled from, never asked to stop
        self.assertGreater(server.port, port)
        self.assertEqual(where["notice"], f"{port} is held by cadgen {previous.version()}'s engine (pid "
                                          f"{theirs['pid']}); the engine serves on {server.port} and keeps it")
        # It serves with the token it started with: a new one is refused while it runs.
        refused = self.cli("server", "--rotate-token")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("another engine server is running", refused.stderr)

    def test_a_client_of_another_release_attaches_and_starts_the_current_installation_s_engine(self) -> None:
        """One engine a device: a client of another installation (an app's newer plugin) attaches to the
        engine running, whatever its release, and with none running starts the current installation's,
        never its own."""
        from cadgen._internal import installations

        found = installations.targets()
        if found is None:
            self.skipTest("this interpreter has no console script to register")
        with mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": self.env["CADGEN_STATE_DIR"]}):
            installations.register("1.0.0", found)
            installations.point("1.0.0")
        theirs = other_installation(self.root)  # another release's client, its environment its own
        first = self.launch(CADGEN_ENGINE_PORT=str(free_port()))
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
        first = self.launch(CADGEN_ENGINE_PORT=str(named))
        self.assertEqual(first["port"], named)
        self.assertNotIn("port", self.record(), "a named port is never remembered")
        self.assertEqual(first["token"], self.token())
        # The link a launch prints and the session a browser is given for it outlive the engine and
        # its port: the next engine, on another port of the host, admits both.
        from urllib.parse import parse_qs, urlsplit

        from cadgen.viewer.engine_app import TOKEN_NEEDED_PAGE

        link = parse_qs(urlsplit(first["url"]).query)["token"][0]
        status, headers, _ = self.ask(named, f"/?token={link}")
        self.assertEqual(status, 302)
        cookie = headers["set-cookie"].split(";")[0]
        self.stop()
        moved = self.launch(CADGEN_ENGINE_PORT=str(free_port()))
        self.assertNotEqual((moved["pid"], moved["port"]), (first["pid"], named))
        self.assertEqual(self.ask(moved["port"], "/__cad/server", Cookie=cookie)[0], 200)
        self.assertEqual(self.ask(moved["port"], f"/?token={link}")[0], 302)
        self.stop()
        # --port on ``cadgen server`` outranks CADGEN_ENGINE_PORT; --rotate-token retires every link
        # and every session: each page then needs a new link.
        other = free_port()
        self.env["CADGEN_ENGINE_PORT"] = str(named)
        self.server("--port", str(other), "--rotate-token")
        for headers in ({"Cookie": cookie}, {}):
            self.assertEqual(self.ask(other, "/" if headers else f"/?token={link}", Sec_Fetch_Dest="document",
                                      **headers)[::2], (403, TOKEN_NEEDED_PAGE))
        rotated = self.launch()
        self.assertEqual(rotated["port"], other)
        self.assertNotEqual(rotated["token"], first["token"])
        self.assertEqual(self.token(), rotated["token"])
        # Refused while an engine runs, which keeps the token it started with.
        refused = self.cli("server", "--rotate-token")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("run cadgen stop first", refused.stderr)
        self.assertEqual(self.token(), rotated["token"])


class BuildBoundNoticeTest(unittest.TestCase):
    def test_a_roll_a_builds_page_made_is_said_by_the_next_build_once_and_by_no_status(self) -> None:
        """A build's page binds the port with no client's request (``models.register_page``): the
        next build's answer says the roll, once; a status asked meanwhile does not take it."""
        import io
        from unittest import mock

        from cadgen.engine import daemon

        said = "3245 is held by another process; this installation serves on 3246 and keeps it"

        class Engine:
            refusal, token, unsaid = None, "ab" * 16, said

            def handle(self, request: dict, send) -> None:
                send({"log": "building"})
                send({"ok": True})

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


if __name__ == "__main__":
    unittest.main()
