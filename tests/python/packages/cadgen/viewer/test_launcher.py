"""The launcher contract: one port, asked before it is bound — nothing there starts, this
user's viewer at this identity is reused, one running other code is replaced, anything else
is refused — ``--new`` past all of it, and the stdout lines agents parse.

Deliberately SUBPROCESS tests rather than in-process ones. The subject here IS the process:
stdout flushing on a server that never exits, the exit codes, signal shutdown, a server
another launch asks to exit. Calling ``main()`` in-process would test none of that and would
silently pass the buffering bug that hangs the real launch.

Never the default port: 3245 is the developer's own viewer, and every launch here names a
port of its own (``free_port``) or takes ``--new``. Each launch gets a private state
directory (the detached log, the analytics answer) and temporary directory.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from cadgen.viewer import main as main_module
from cadgen.viewer.http_app import os_user

PACKAGE_DIR = Path(main_module.__file__).resolve().parent
# The documented module spelling, so the child resolves the SAME cadgen this
# suite imports (PYTHONPATH is inherited through ``env``).
LAUNCH = [sys.executable, "-m", "cadgen.viewer"]
TAKEN = "is in use by another program (or another user's CAD Viewer); start the viewer with --port N."


def free_port() -> int:
    """A port nothing holds right now (the OS's pick), for one launch to name."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def server_info(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/__cad/server", timeout=5) as response:
        return json.loads(response.read())


def port_answers(port: int, timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__cad/server", timeout=timeout) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False


class FakeViewer:
    """A server on a port of its own that says it is a CAD Viewer of ``user``, and counts the
    requests to exit it gets (never honoured)."""

    def __init__(self, *, user, token: str = "") -> None:
        self.shutdowns: list[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D102 - silent
                return

            def do_GET(self):  # noqa: N802
                body = json.dumps({"app": "cad-viewer", "user": user, "identityToken": token, "pid": 1,
                                   "port": fake.port}).encode()
                self.send_response(200)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802
                fake.shutdowns.append(self.path)
                self.send_response(202)
                self.send_header("content-length", "0")
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)


class LauncherFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self._tmp.name, "tmp")
        self.state = os.path.join(self._tmp.name, "state")
        os.makedirs(self.home)
        self._children: list[subprocess.Popen] = []
        self._servers: list[tuple[int, int]] = []
        self.addCleanup(self._teardown)

    def adopt_server(self, port: int) -> dict:
        """Own the server answering ``port``: a detached one, or the replacement a development
        restart left there (on Windows a process this fixture never spawned), is stopped at the
        end like a child. Returns what it says of itself."""
        info = server_info(port)
        entry = (int(port), int(info["pid"]))
        if entry not in self._servers:
            self._servers.append(entry)
        return info

    def _stop_server(self, port: int, pid: int, timeout: float = 15.0) -> None:
        if not port_answers(port) or server_info(port).get("pid") != pid:
            return  # gone already, and the port is someone else's business now
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and port_answers(port):
            time.sleep(0.1)

    def _teardown(self) -> None:
        # Adopted servers first, and gracefully: they may be standing in a directory this
        # cleanup is about to remove, which Windows refuses (WinError 32).
        for port, pid in self._servers:
            self._stop_server(port, pid)
        for child in self._children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            for pipe in (child.stdout, child.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        self._cleanup_tmp()

    def _cleanup_tmp(self, timeout: float = 15.0) -> None:
        """Remove the fixture's directory, allowing for a late handle release: Windows drops a
        terminated process's handles ASYNCHRONOUSLY. Bounded, and still raising at the end."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                self._tmp.cleanup()
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)

    def env(self, **overrides) -> dict:
        env = dict(os.environ)
        env.update(
            {
                "TMPDIR": self.home,
                "TEMP": self.home,
                "TMP": self.home,
                "CADGEN_STATE_DIR": self.state,
                # A launch warms the build daemon, which would be one per test, its workers left
                # running after it. PrewarmsTheDaemon opts in.
                "CADGEN_DAEMON": "0",
            }
        )
        env.update(overrides)
        return env

    def make_dist(self) -> str:
        dist = tempfile.mkdtemp(dir=self._tmp.name, prefix="cad-dist-")
        Path(dist, "index.html").write_text("<html>viewer</html>", encoding="utf-8")
        return dist

    def make_root(self) -> str:
        return tempfile.mkdtemp(dir=self._tmp.name, prefix="cad-root-")

    def launch(self, args: list[str], cwd: str | None = None, **env_overrides) -> subprocess.Popen:
        child = subprocess.Popen(
            [*LAUNCH, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd or self.make_root(),
            env=self.env(**env_overrides),
        )
        self._children.append(child)
        return child

    def run_to_exit(self, args: list[str], timeout: float = 30.0, cwd: str | None = None, **env_overrides):
        child = self.launch(args, cwd=cwd, **env_overrides)
        stdout, stderr = child.communicate(timeout=timeout)
        return child.returncode, stdout, stderr

    def wait_for_url_line(self, child: subprocess.Popen, timeout: float = 30.0, *, marker: str = "{") -> str:
        """Read stdout until the announce line appears and return everything so far.

        ``marker`` is the line prefix that ends the read: the ``{url,port,action}``
        JSON line by default, or ``CAD Viewer URL: `` for a launch without ``--json``.

        Reading LINE BY LINE off a live process is the point: the launcher must
        flush, because Python block-buffers a non-TTY stdout and this process
        never exits to flush on close. The read runs on a thread so the deadline
        holds while the child is silent, and a launch that misses it is killed
        before its stderr is read: a live server's stderr never ends.
        """
        lines: list[str] = []

        def read() -> None:
            for line in iter(child.stdout.readline, ""):
                lines.append(line)
                if line.startswith(marker):
                    return

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        reader.join(timeout)
        if lines and lines[-1].startswith(marker):
            return "".join(lines)
        child.kill()
        try:
            _, stderr = child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stderr = "(still held open by a process the launch started)"
        self.fail(f"no {marker!r} line within {timeout:.0f}s; got: {''.join(lines)!r} stderr={stderr!r}")
        return ""

    @staticmethod
    def json_line(stdout: str) -> dict:
        for line in stdout.split("\n"):
            if line.startswith("{"):
                return json.loads(line)
        raise AssertionError(f"no JSON line in: {stdout!r}")

    def hold_port(self) -> int:
        """A port held by a program that is no viewer: a plain listening socket."""
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(holder.close)
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        return holder.getsockname()[1]


class Launch(LauncherFixture):
    def test_a_launch_starts_on_its_port_and_prints_the_url_contract(self) -> None:
        port, root = free_port(), self.make_root()
        child = self.launch(["--dist", self.make_dist(), "--port", str(port), "--json"], cwd=root)
        stdout = self.wait_for_url_line(child)
        # --json: stdout is the one JSON line, like every other --json verb; the
        # narration (Starting… / CAD Viewer URL:) goes to stderr. The line is compact:
        # the launch smoke test greps for '"action":"started"'.
        self.assertEqual(
            [line for line in stdout.splitlines() if line.strip()],
            [f'{{"url":"http://127.0.0.1:{port}/","port":{port},"action":"started"}}'],
        )
        info = server_info(port)
        self.assertEqual((info["app"], info["port"], info["pid"], info["user"]), ("cad-viewer", port, child.pid, os_user()))
        # Where a developer's relative links resolve: the folder it started in (macOS spells the
        # temporary directory through /private, so both sides are resolved).
        self.assertEqual(os.path.realpath(info["start"]), os.path.realpath(root))

    def test_this_users_viewer_at_this_identity_is_reused_from_any_folder(self) -> None:
        port, dist = free_port(), self.make_dist()
        first = self.launch(["--dist", dist, "--port", str(port), "--json"])
        started = self.json_line(self.wait_for_url_line(first))
        # Another folder: one viewer serves every file, so where a launch runs does not matter.
        code, stdout, stderr = self.run_to_exit(["--dist", dist, "--port", str(port), "--json"])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(
            [line for line in stdout.splitlines() if line.strip()],
            [json.dumps({"url": started["url"], "port": port, "action": "reused"}, separators=(",", ":"))],
        )
        self.assertRegex(stderr, r"Reusing CAD Viewer at ")
        code, stdout, _ = self.run_to_exit(["--dist", dist, "--port", str(port)])
        self.assertEqual((code, stdout.splitlines()[-1]), (0, f"CAD Viewer URL: http://127.0.0.1:{port}/"))
        self.assertEqual(server_info(port)["pid"], first.pid, "nothing was spawned")

    def test_new_binds_a_port_of_its_own_and_never_reuses(self) -> None:
        dist = self.make_dist()
        first = self.json_line(self.wait_for_url_line(self.launch(["--dist", dist, "--json", "--new"])))
        second = self.json_line(self.wait_for_url_line(self.launch(["--dist", dist, "--json", "--new"])))
        self.assertEqual((first["action"], second["action"]), ("started", "started"))
        self.assertNotEqual(first["port"], second["port"])
        self.assertIn(f":{first['port']}/", first["url"])
        # A server --new started is an ordinary viewer to every other launch.
        code, stdout, _ = self.run_to_exit(["--dist", dist, "--port", str(first["port"]), "--json"])
        self.assertEqual((code, self.json_line(stdout)["action"]), (0, "reused"))

    def test_a_port_another_program_holds_is_refused(self) -> None:
        port = self.hold_port()
        code, stdout, stderr = self.run_to_exit(["--dist", self.make_dist(), "--port", str(port), "--json"])
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn(f"Port {port} {TAKEN}", stderr)

    def test_another_users_viewer_is_refused_and_never_asked_to_exit(self) -> None:
        stranger = FakeViewer(user="someone-else" if os.name == "nt" else -1)
        self.addCleanup(stranger.close)
        code, _, stderr = self.run_to_exit(["--dist", self.make_dist(), "--port", str(stranger.port)])
        self.assertEqual(code, 1)
        self.assertIn(f"Port {stranger.port} {TAKEN}", stderr)
        self.assertEqual(stranger.shutdowns, [])


class AnnounceIsConnectable(LauncherFixture):
    """The printed URL is connectable the instant it appears.

    The CAD skills tell an agent to read the URL the command prints and fetch it;
    the launch smoke test does the same. Both are only sound if the announce
    follows the bind: the socket must be bound and LISTENING (and the real app
    attached) before either line is written, so the first request after reading
    the line answers 200 with no retry, no sleep, and no grace period. The 1s
    socket timeout is the pin.
    """

    ANNOUNCE_TO_200_BUDGET_SECONDS = 1.0

    def _first_request_after(self, child: subprocess.Popen, marker: str, port: int) -> None:
        stdout = self.wait_for_url_line(child, marker=marker)
        announced = next(line for line in stdout.split("\n") if line.startswith(marker))
        url = json.loads(announced)["url"] if marker == "{" else announced[len(marker):].strip()
        self.assertEqual(url, f"http://127.0.0.1:{port}/")
        started = time.monotonic()
        # One attempt. The timeout bounds connect AND the response read.
        with urllib.request.urlopen(f"{url}__cad/server", timeout=self.ANNOUNCE_TO_200_BUDGET_SECONDS) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["port"], port)
        self.assertLess(time.monotonic() - started, self.ANNOUNCE_TO_200_BUDGET_SECONDS)

    def test_the_human_url_line_answers_the_first_request(self) -> None:
        port = free_port()
        child = self.launch(["--dist", self.make_dist(), "--port", str(port)])
        self._first_request_after(child, "CAD Viewer URL: ", port)

    def test_the_json_line_answers_the_first_request(self) -> None:
        port = free_port()
        child = self.launch(["--dist", self.make_dist(), "--port", str(port), "--json"])
        self._first_request_after(child, "{", port)


class StagedApp(LauncherFixture):
    """A staged copy of the cadgen package, launched as its own installation.

    Everything below runs against a STAGED copy of the cadgen package + its own dist,
    so touching mtimes never dirties the real checkout. The staging is INSTALLED-WHEEL
    shaped by default (the package's parent is ``site-packages``, with no project file
    above it) so these launches are production launches: they do not watch their own
    code. ``stage_app(checkout=True)`` stages the other shape, for the development
    auto-reload.
    """

    def stage_app(self, *, checkout: bool = False) -> str:
        """Stage the package and a dist as one installation, and return its root.

        The sources go UNDER an ``install/`` level rather than beside the dist, which is
        where ``warn_when_dist_is_stale`` looks for the CLIENT sources belonging to
        ``<staged>/dist``.
        """
        staged = os.path.join(self._tmp.name, f"staged-{'checkout' if checkout else 'wheel'}")
        if os.path.isdir(staged):
            shutil.rmtree(staged)
        install = os.path.join(staged, "install")
        parent = "src" if checkout else "site-packages"
        # The whole package, not just cadgen/viewer: the child imports `cadgen`
        # first, and a half-package on PYTHONPATH would shadow the real one.
        shutil.copytree(
            str(PACKAGE_DIR.parent),
            os.path.join(install, parent, "cadgen"),
            ignore=shutil.ignore_patterns("__pycache__", "_runtime"),
        )
        if checkout:
            # What `running_from_source_checkout` looks for, and the only thing
            # separating these two stagings.
            Path(install, "pyproject.toml").write_text(
                '[project]\nname = "cadgen"\nversion = "0.0.0"\n', encoding="utf-8"
            )
        os.makedirs(os.path.join(staged, "dist"))
        Path(staged, "dist", "index.html").write_text("<html>viewer</html>", encoding="utf-8")
        return staged

    @staticmethod
    def staged_sources(staged: str) -> str:
        install = os.path.join(staged, "install")
        return os.path.join(install, "src" if os.path.isdir(os.path.join(install, "src")) else "site-packages")

    def launch_staged(self, staged: str, extra: list[str], *, stderr_path: str = "") -> subprocess.Popen:
        # A live process's stderr PIPE cannot be read without blocking, and these launches
        # never exit, so a test that reads the narration sends it to a file instead. BINARY,
        # deliberately: Popen hands the child the raw descriptor, so the bytes in it are the
        # child's own encoding — the platform code page on Windows.
        log = open(stderr_path, "wb") if stderr_path else subprocess.PIPE
        if stderr_path:
            self.addCleanup(log.close)
        child = subprocess.Popen(
            [*LAUNCH, "--json", *extra],
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            cwd=self.make_root(),
            env=self.env(
                PYTHONPATH=self.staged_sources(staged),
                # The default dist location is the identity's other half.
                CADGEN_VIEWER_DIST=os.path.join(staged, "dist"),
            ),
        )
        self._children.append(child)
        return child

    @staticmethod
    def change_runtime_code(staged: str) -> None:
        """Edit runtime code OUTSIDE cadgen.viewer, as a pull would: the viewer imports the
        daemon's transport, so this re-keys the identity and, in a checkout, trips the
        auto-reload watcher."""
        runtime_file = Path(StagedApp.staged_sources(staged), "cadgen", "daemon", "transport.py")
        runtime_file.write_text(
            runtime_file.read_text(encoding="utf-8") + "\n# changed runtime\n", encoding="utf-8"
        )

    def wait_for_identity_change(self, port: int, before: str, timeout: float = 30.0) -> dict:
        """The restarted server, answering the SAME port with a new identity, adopted: from
        this moment a process the fixture may never have spawned holds the port."""
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                info = server_info(port)
            except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
                last = error  # the port is closed for the moment it takes to re-bind
                time.sleep(0.1)
                continue
            if info["identityToken"] != before:
                return self.adopt_server(port)
            last = info
            time.sleep(0.1)
        self.fail(f"port {port} never came back with a new identity; last={last!r}")


class NewestWins(StagedApp):
    """This user's viewer running other code — a pull, a rebuilt client, another --dist — is
    asked to exit, and the launch takes its port: the newest code wins, on the same URL."""

    def test_a_viewer_running_other_code_is_replaced_on_its_port(self) -> None:
        staged, port = self.stage_app(), free_port()
        first = self.launch_staged(staged, ["--port", str(port)])
        self.assertEqual(self.json_line(self.wait_for_url_line(first))["action"], "started")
        token = server_info(port)["identityToken"]
        self.assertRegex(token, r"^[^:]*:[0-9a-f]{64}$", "the token is version:digest")
        self.assertIs(server_info(port)["autoReload"], False, "an installed wheel does not watch its own code")

        self.change_runtime_code(staged)
        second = self.launch_staged(staged, ["--port", str(port)])
        self.assertEqual(self.json_line(self.wait_for_url_line(second)), {
            "url": f"http://127.0.0.1:{port}/", "port": port, "action": "started"})
        self.assertEqual(first.wait(timeout=15), 0, "the old viewer exited cleanly")
        info = server_info(port)
        self.assertEqual(info["pid"], second.pid)
        self.assertNotEqual(info["identityToken"], token)

        # The client is the identity's other half: another --dist replaces it too.
        alternate = os.path.join(staged, "alternate-dist")
        os.makedirs(alternate)
        Path(alternate, "index.html").write_text("<html>viewer</html>", encoding="utf-8")
        third = self.launch_staged(staged, ["--port", str(port), "--dist", alternate])
        self.assertEqual(self.json_line(self.wait_for_url_line(third))["action"], "started")
        self.assertEqual(second.wait(timeout=15), 0)
        self.assertEqual(server_info(port)["pid"], third.pid)


class DevelopmentAutoReload(StagedApp):
    """A checkout restarts itself onto its own port; a wheel never does."""

    def test_a_checkout_restarts_itself_on_the_same_port_and_stays_reusable(self) -> None:
        staged, port = self.stage_app(checkout=True), free_port()
        log_path = os.path.join(self._tmp.name, "restart.log")
        first = self.launch_staged(staged, ["--port", str(port)], stderr_path=log_path)
        self.assertEqual(self.json_line(self.wait_for_url_line(first))["action"], "started")
        before = server_info(port)
        self.assertIs(before["autoReload"], True)

        self.change_runtime_code(staged)
        after = self.wait_for_identity_change(port, before["identityToken"])

        self.assertEqual(after["port"], port, "the URL the browser has open stays valid")
        self.assertEqual(after["start"], before["start"], "and its relative links resolve where they did")
        self.assertGreater(after["startedAt"], before["startedAt"], "it is a new server")
        # errors="replace": the child writes the PLATFORM's encoding, not ours.
        narration = Path(log_path).read_text(encoding="utf-8", errors="replace")
        self.assertIn(f"code changed; restarting on port {port}", narration)
        self.assertNotIn("older than the client sources", narration)

        # The launcher's contract still holds: `cadgen viewer` hands back THIS instance.
        relaunch = self.launch_staged(staged, ["--port", str(port)])
        stdout, _ = relaunch.communicate(timeout=30)
        self.assertEqual(self.json_line(stdout), {"url": f"http://127.0.0.1:{port}/", "port": port, "action": "reused"})

    def test_the_dev_server_backend_comes_back_on_its_port(self) -> None:
        # Exactly what apps/web/vite.config.mjs spawns. Vite reads the port off the announce
        # line ONCE and proxies there for the rest of the session, so a restart that moved
        # would strand the dev server.
        staged = self.stage_app(checkout=True)
        child = self.launch_staged(staged, ["--new", "--api-only"])
        port = self.json_line(self.wait_for_url_line(child))["port"]
        before = server_info(port)
        self.change_runtime_code(staged)
        after = self.wait_for_identity_change(port, before["identityToken"])
        self.assertEqual((after["port"], after["serverFeatures"]), (port, before["serverFeatures"]))


class DistFreshnessWarning(unittest.TestCase):
    """The dev-only staleness guard: one stderr line, detection only."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dist = os.path.join(self._tmp.name, "dist")
        os.makedirs(self.dist)
        Path(self.dist, "index.html").write_text("<html>viewer</html>", encoding="utf-8")

    def _warning_output(self) -> str:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            main_module.warn_when_dist_is_stale(self.dist)
        return stderr.getvalue()

    def _make_src(self, mtime: float) -> None:
        src = os.path.join(self._tmp.name, "src")
        os.makedirs(src)
        source = Path(src, "App.jsx")
        source.write_text("export default null\n", encoding="utf-8")
        os.utime(source, (mtime, mtime))

    def test_a_source_newer_than_the_dist_warns_and_names_the_rebuild(self) -> None:
        self._make_src(time.time() + 60)
        self.assertEqual(
            self._warning_output(),
            "dist/ is older than the client sources — rebuild with `npm run build`\n",
        )

    def test_a_current_dist_is_silent(self) -> None:
        self._make_src(time.time() - 3600)
        self.assertEqual(self._warning_output(), "")

    def test_structurally_silent_without_client_sources(self) -> None:
        self.assertEqual(self._warning_output(), "")


class ApiOnly(LauncherFixture):
    """`npm run dev` must work on a checkout that has never been built: dist/ is gitignored,
    and Vite serves the client and proxies only the API here."""

    def test_it_serves_the_api_with_no_dist_anywhere(self) -> None:
        child = self.launch(["--json", "--new", "--api-only"])
        port = self.json_line(self.wait_for_url_line(child))["port"]
        self.assertEqual(server_info(port)["port"], port)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__cad/catalog", timeout=5) as response:
            self.assertEqual(json.loads(response.read())["entries"], [])
        # The client is Vite's job in this mode, so the SPA routes are a plain 404.
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
        self.assertEqual(caught.exception.code, 404)

    def test_without_it_a_missing_client_refuses_before_asking_the_port(self) -> None:
        # CADGEN_VIEWER_DIST wins the default-dist resolution, so an EMPTY directory makes "no
        # client anywhere" true whether or not this checkout has built apps/web. The default
        # port is the developer's: the refusal comes before anything asks it.
        code, _, stderr = self.run_to_exit([], CADGEN_VIEWER_DIST=self.make_root())
        self.assertEqual(code, 1)
        self.assertIn("No built CAD Viewer client found", stderr)
        self.assertIn("--api-only", stderr, "the refusal must name the dev-mode escape")
        # Control: the same launch, given a client, starts.
        child = self.launch(["--json", "--new"], CADGEN_VIEWER_DIST=self.make_dist())
        self.assertEqual(self.json_line(self.wait_for_url_line(child))["action"], "started")


class Detach(LauncherFixture):
    """``--detach``: the launch RETURNS once its server has announced itself, so ``… --json
    2>&1 | tail -1`` ends; the server runs on in the background, writing to one log in the
    state directory."""

    def setUp(self) -> None:
        super().setUp()
        self.dist = self.make_dist()
        self.log = os.path.join(self.state, "viewer.log")

    def detach(self, port: int, *extra: str) -> tuple[int, str, str]:
        return self.run_to_exit(["--dist", self.dist, "--port", str(port), "--json", "--detach", *extra], timeout=60)

    def test_it_returns_with_one_json_line_and_leaves_a_reusable_server(self) -> None:
        port = free_port()
        code, stdout, stderr = self.detach(port)
        self.assertEqual(code, 0, stderr)
        lines = [line for line in stdout.splitlines() if line.strip()]
        self.assertEqual(lines, [json.dumps({"url": f"http://127.0.0.1:{port}/", "port": port, "action": "started"},
                                            separators=(",", ":"))])
        pid = self.adopt_server(port)["pid"]
        self.assertIn(f"Running in the background (pid {pid}); its output goes to {self.log}.", stderr)
        self.assertIn("Starting CAD Viewer at", Path(self.log).read_text(encoding="utf-8", errors="replace"))

        # A second detached launch reuses it, and returns just the same.
        code, stdout, stderr = self.detach(port)
        self.assertEqual((code, self.json_line(stdout)["action"]), (0, "reused"), stderr)

        code, stdout, _ = self.run_to_exit(["stop", "--port", str(port)])
        self.assertEqual((code, stdout), (0, f"Stopped CAD Viewer on port {port} (pid {pid}).\n"))
        self.assertFalse(port_answers(port))

    def test_a_server_that_dies_leaves_its_log_to_read(self) -> None:
        port = free_port()
        code, _, stderr = self.detach(port)
        self.assertEqual(code, 0, stderr)
        pid = self.adopt_server(port)["pid"]
        # Killed outright, as a crash or an OOM kill ends it. (SIGTERM is TerminateProcess on Windows.)
        os.kill(pid, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)
        deadline = time.monotonic() + 15
        while port_answers(port):
            self.assertLess(time.monotonic(), deadline, f"the killed server on port {port} still answers")
            time.sleep(0.05)
        self.assertIn(f"Starting CAD Viewer at http://127.0.0.1:{port}/",
                      Path(self.log).read_text(encoding="utf-8", errors="replace"))

    @unittest.skipIf(os.name == "nt", "a POSIX shell pipeline")
    def test_piped_into_tail_it_ends_on_the_json_line(self) -> None:
        port = free_port()
        command = " ".join([*(f"'{part}'" for part in LAUNCH), "--dist", f"'{self.dist}'", "--port", str(port),
                            "--json", "--detach", "2>&1", "|", "tail", "-1"])
        result = subprocess.run(["/bin/sh", "-c", command], cwd=self.make_root(), env=self.env(),
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout.strip())["action"], "started")
        self.adopt_server(port)

    def test_a_child_that_cannot_start_relays_its_refusal(self) -> None:
        port = self.hold_port()
        code, stdout, stderr = self.detach(port)
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn(f"Port {port} {TAKEN}", stderr)

    def test_a_launch_that_never_announces_exits_1(self) -> None:
        # The launcher kills a child that has not announced by the deadline; its -9 must not
        # become the launch's exit status (247).
        stderr = io.StringIO()
        with mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": self.state}), \
                mock.patch.object(main_module, "DETACH_READY_TIMEOUT_SECONDS", 0.0), \
                contextlib.redirect_stderr(stderr):
            code = main_module.launch_detached(["--port", "1"], as_json=True)
        self.assertEqual(code, 1)
        self.assertIn("no announcement within 0s; stopped it", stderr.getvalue())


class PrewarmsTheDaemon(LauncherFixture):
    """After its announcement a launch starts the build daemon, whose workers import
    build123d before any build asks: a session's first build finds them warm."""

    def test_a_launch_leaves_a_daemon_answering(self) -> None:
        from cadgen.daemon import client
        from tests.python.support.daemon_cleanup import retire_owned_daemon

        state = tempfile.mkdtemp(prefix="cgv-")  # short: a Unix socket path caps near 104 bytes
        daemon_env = {
            "CADGEN_DAEMON": "1",
            "CADGEN_DAEMON_STATE_DIR": state,
            "CADGEN_DAEMON_SOCKET": (rf"\\.\pipe\cadgen-test-{uuid.uuid4().hex}" if os.name == "nt"
                                     else os.path.join(state, "d.sock")),
            "CADGEN_CACHE_DIR": os.path.join(state, "store"),
        }
        self.addCleanup(shutil.rmtree, state, True)

        def retire() -> None:
            with mock.patch.dict(os.environ, daemon_env):
                if client.status() is not None:
                    retire_owned_daemon(daemon_env["CADGEN_DAEMON_SOCKET"])

        self.addCleanup(retire)  # before the fixture's directories go: the daemon stands in one
        child = self.launch(["--dist", self.make_dist(), "--json", "--new"], **daemon_env)
        self.wait_for_url_line(child)
        with mock.patch.dict(os.environ, daemon_env):
            deadline = time.monotonic() + 60
            while client.status() is None:
                if time.monotonic() >= deadline:
                    self.fail("no build daemon answered after the viewer started")
                time.sleep(0.1)


class Stop(LauncherFixture):
    def test_stop_asks_the_viewer_on_its_port_to_exit(self) -> None:
        port = free_port()
        child = self.launch(["--dist", self.make_dist(), "--port", str(port), "--json"])
        self.wait_for_url_line(child)
        code, stdout, _ = self.run_to_exit(["stop", "--port", str(port)])
        self.assertEqual((code, stdout), (0, f"Stopped CAD Viewer on port {port} (pid {child.pid}).\n"))
        self.assertEqual(child.wait(timeout=5), 0, "the server exits cleanly")
        code, _, stderr = self.run_to_exit(["stop", "--port", str(port)])
        self.assertEqual((code, stderr), (1, f"No CAD Viewer is running on port {port}.\n"))

    def test_stop_never_asks_another_program_or_another_users_viewer(self) -> None:
        stranger = FakeViewer(user="someone-else" if os.name == "nt" else -1)
        self.addCleanup(stranger.close)
        code, _, stderr = self.run_to_exit(["stop", "--port", str(stranger.port)])
        self.assertEqual((code, stderr), (1, f"The CAD Viewer on port {stranger.port} is another user's.\n"))
        self.assertEqual(stranger.shutdowns, [])
        port = self.hold_port()
        code, _, stderr = self.run_to_exit(["stop", "--port", str(port)])
        self.assertEqual((code, stderr), (1, f"No CAD Viewer is running on port {port}.\n"))


class InterpreterFloor(unittest.TestCase):
    """The floor is enforced at startup, not discovered on the first request."""

    def test_the_interpreter_running_this_suite_is_accepted(self) -> None:
        self.assertEqual(main_module.unsupported_python_message(), "")

    def test_an_interpreter_below_the_floor_is_named_along_with_the_way_out(self) -> None:
        message = main_module.unsupported_python_message(
            version_info=(3, 9, 6, "final", 0), executable="/usr/bin/python3"
        )
        self.assertIn("3.11", message, "the message must name the version required")
        self.assertIn("3.9.6", message, "and the version actually running")
        self.assertIn("/usr/bin/python3", message, "and WHICH interpreter that was")
        self.assertIn("VIEWER_PYTHON", message, "and how to point dev at another one")

    def test_the_guard_parses_and_fires_under_an_interpreter_that_predates_the_floor(self) -> None:
        # The refusal is worthless if the module cannot be PARSED by the interpreter it is
        # refusing: parse everything up to and including the guard against 3.9's grammar.
        source = Path(main_module.__file__).read_text(encoding="utf-8")
        guard, marker, _ = source.partition("_UNSUPPORTED_PYTHON = unsupported_python_message()")
        self.assertTrue(marker, "the startup guard moved; update this test")
        ast.parse(guard + marker, filename="main.py", feature_version=(3, 9))
        for version in ((3, 9, 6), (3, 10, 14), (2, 7, 18)):
            self.assertNotEqual(main_module.unsupported_python_message(version_info=version), "", str(version))
        self.assertEqual(main_module.unsupported_python_message(version_info=(3, 11, 0)), "")


class DistResolution(unittest.TestCase):
    def test_dist_resolution_falls_back_and_then_gives_up(self) -> None:
        # The default location pinned through CADGEN_VIEWER_DIST, so the checkout's own build
        # cannot mask a case.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dist, fallback, empty = (os.path.join(tmp.name, name) for name in ("dist", "fallback", "empty"))
        for directory in (dist, fallback):
            os.makedirs(directory)
            Path(directory, "index.html").write_text("<html>viewer</html>", encoding="utf-8")
        os.makedirs(empty)
        with mock.patch.dict(os.environ, {"CADGEN_VIEWER_DIST": fallback}):
            self.assertEqual(main_module.resolve_dist_dir(dist), os.path.abspath(dist))
            # realpath on both sides: macOS spells the temp dir through /var -> /private/var.
            self.assertEqual(os.path.realpath(main_module.resolve_dist_dir(empty)), os.path.realpath(fallback),
                             "an explicit --dist without index.html falls through to the default location")
        with mock.patch.dict(os.environ, {"CADGEN_VIEWER_DIST": empty}):
            self.assertEqual(main_module.resolve_dist_dir(""), "", "no index.html anywhere is no client")


class ArgumentGrammar(unittest.TestCase):
    """The parse rules, in-process: an unknown argument is a refusal naming the FIRST unknown
    token, and every refusal exits 2."""

    @staticmethod
    def parse(argv: list[str]) -> dict:
        return main_module.parse_args(argv)

    def refuses(self, argv: list[str]) -> str:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            self.parse(argv)
        self.assertEqual(caught.exception.code, 2, argv)
        return stderr.getvalue()

    def test_an_unknown_argument_is_a_refusal_naming_the_first_unknown(self) -> None:
        # `--dir /tmp` must name --dir, not the path that followed it.
        message = self.refuses(["--dir", "/tmp", "--json"])
        self.assertIn("unknown argument: --dir", message)
        self.assertNotIn("/tmp", message.splitlines()[0])
        # Retired: a viewer has no registry and no rolled port.
        for retired in ("--ephemeral", "--no-registry"):
            self.assertIn(f"unknown argument: {retired}", self.refuses([retired]))

    def test_port_zero_garbage_and_out_of_range_are_refused_not_defaulted(self) -> None:
        # --new is the spelling for "any free port".
        self.assertIn("port out of range", self.refuses(["--port", "0"]))
        self.assertIn("not a port number", self.refuses(["--port", "abc"]))
        for value in ("70000", "-1"):
            self.assertIn("port out of range", self.refuses(["--port", value]), value)
        self.assertIn("--port", self.refuses(["--port"]))

    def test_port_and_new_are_mutually_exclusive(self) -> None:
        self.assertIn("not allowed with", self.refuses(["--port", "3999", "--new"]))

    def test_the_port_is_3245_unless_named_and_new_binds_any(self) -> None:
        self.assertEqual((self.parse([])["port"], self.parse([])["new"]), (3245, False))
        self.assertEqual(self.parse(["--port", "3999"])["port"], 3999)
        self.assertEqual((self.parse(["--new"])["port"], self.parse(["--new"])["new"]), (0, True))

    def test_the_dev_flags_default_off_and_are_independent(self) -> None:
        defaults = self.parse([])
        self.assertEqual((defaults["new"], defaults["api_only"]), (False, False))
        self.assertEqual((self.parse(["--new"])["api_only"], self.parse(["--api-only"])["new"]), (False, False))

    def test_repeated_flags_take_the_last_value_and_nothing_abbreviates(self) -> None:
        self.assertEqual(self.parse(["--host", "a", "--host", "b"])["host"], "b")
        # `--ap` for --api-only is exactly the kind of accidental match a typo becomes.
        self.assertIn("unknown argument: --ap", self.refuses(["--ap"]))


class ArgumentSurface(unittest.TestCase):
    """A launcher that answers --help by starting a server reads as broken, and a tolerated
    typo silently changes what it does."""

    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([*LAUNCH, *argv], capture_output=True, text=True, timeout=30)

    def test_help_answers_on_stdout_and_starts_nothing(self) -> None:
        result = self._run("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: python -m cadgen.viewer", result.stdout)
        self.assertIn("--new", result.stdout)
        self.assertIn("python -m cadgen.viewer stop [--port N]", result.stdout)
        self.assertNotIn("--root", result.stdout, "the launcher has no directory flag")
        self.assertEqual(result.stderr, "")

    def test_the_front_door_names_itself_in_help(self) -> None:
        result = subprocess.run([sys.executable, "-m", "cadgen.cli", "viewer", "--help"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: cadgen viewer", result.stdout)
        self.assertIn("cadgen viewer stop", result.stdout)

    def test_unknown_and_retired_arguments_are_refused_not_ignored(self) -> None:
        # The FIRST unknown token, not the value that trailed it; `--root <dir>` and `list` are
        # retired (a viewer has no directory, and there is one per port), and `--json stop` is a
        # serve invocation: only argv[0] selects `stop`.
        for argv, unknown in ((("--dir", "/tmp"), "--dir"), (("--root", "/tmp"), "--root"), (("list",), "list"),
                              (("--json", "stop"), "stop")):
            with self.subTest(argv=argv):
                result = self._run(*argv)
                self.assertEqual(result.returncode, 2)
                self.assertIn(f"unknown argument: {unknown}", result.stderr)
                self.assertNotIn("/tmp", result.stderr.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
