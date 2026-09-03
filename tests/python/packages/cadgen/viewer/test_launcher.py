"""The launcher contract: launch is unconditional (roll + keyed reuse, ``--new``
escape), explicit ``--port`` stays strict, and the stdout lines agents parse.

Ported from ``main.test.mjs``, and deliberately still SUBPROCESS tests rather
than in-process ones. The subject here IS the process: stdout flushing on a
server that never exits, the exit codes, signal shutdown, and the registry file
another process reads. Calling ``main()`` in-process would test none of that and
would silently pass the buffering bug that hangs the real launch.

Every launch redirects TMPDIR so the registry is private — the real one is
shared with the viewer the developer is using, and reuse and reaping are both
destructive.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from cadgen.viewer import main as main_module

PACKAGE_DIR = Path(main_module.__file__).resolve().parent
# The documented module spelling, so the child resolves the SAME cadgen this
# suite imports (PYTHONPATH is inherited through ``env``).
LAUNCH = [sys.executable, "-m", "cadgen.viewer"]


class LauncherFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.registry_home = os.path.join(self._tmp.name, "reg")
        os.makedirs(self.registry_home)
        self._children: list[subprocess.Popen] = []
        self.addCleanup(self._teardown)

    def _teardown(self) -> None:
        for child in self._children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            for pipe in (child.stdout, child.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        self._tmp.cleanup()

    def env(self, **overrides) -> dict:
        env = dict(os.environ)
        env.update(
            {
                "TMPDIR": self.registry_home,
                "TEMP": self.registry_home,
                "TMP": self.registry_home,
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
        # The launcher has no directory flag: the cwd IS the served directory,
        # so fixtures choose what a launch serves by choosing its cwd.
        child = subprocess.Popen(
            [*LAUNCH, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
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
        never exits to flush on close.
        """
        deadline = time.monotonic() + timeout
        lines = []
        while time.monotonic() < deadline:
            if child.poll() is not None and child.stdout.closed:
                break
            line = child.stdout.readline()
            if not line:
                if child.poll() is not None:
                    break
                continue
            lines.append(line)
            if line.startswith(marker):
                return "".join(lines)
        self.fail(f"no {marker!r} line before timeout; got: {''.join(lines)!r} stderr={child.stderr.read()!r}")
        return ""

    @staticmethod
    def json_line(stdout: str) -> dict:
        for line in stdout.split("\n"):
            if line.startswith("{"):
                return json.loads(line)
        raise AssertionError(f"no JSON line in: {stdout!r}")


class ExplicitPort(LauncherFixture):
    def test_prints_the_url_contract_and_a_second_explicit_start_refuses(self) -> None:
        dist = self.make_dist()
        root = self.make_root()
        # Below the roll base, so it can never collide with a rolled instance.
        port = 3201
        child = self.launch(["--dist", dist, "--port", str(port), "--json"], cwd=root)
        stdout = self.wait_for_url_line(child)

        self.assertIn(f"Starting CAD Viewer at http://127.0.0.1:{port}/ (serving ", stdout)
        self.assertIn(f"CAD Viewer URL: http://127.0.0.1:{port}/", stdout)
        self.assertEqual(
            self.json_line(stdout),
            {"url": f"http://127.0.0.1:{port}/", "port": port, "action": "started"},
        )

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__cad/server", timeout=5) as response:
            info = json.loads(response.read())
        self.assertEqual(info["app"], "cad-viewer")
        self.assertEqual(info["port"], port, "serverInfo must name the port actually bound")
        self.assertEqual(info["pid"], child.pid, "the registry probe compares this pid")

        # An explicit port is a demand: refuse when taken, never roll, never reuse.
        code, _, stderr = self.run_to_exit(["--dist", dist, "--port", str(port)], cwd=root)
        self.assertEqual(code, 1)
        self.assertRegex(stderr, r"already")

    def test_the_json_line_is_compact(self) -> None:
        # The launch smoke test greps for the literal '"action":"started"'.
        # Python's default json.dumps separators would break it.
        dist = self.make_dist()
        child = self.launch(["--dist", dist, "--port", "3202", "--json"], cwd=self.make_root())
        stdout = self.wait_for_url_line(child)
        line = next(line for line in stdout.split("\n") if line.startswith("{"))
        self.assertIn('"action":"started"', line)
        self.assertIn('"port":3202', line)
        self.assertNotIn(", ", line)


class AnnounceIsConnectable(LauncherFixture):
    """The printed URL is connectable the instant it appears.

    The cad-viewer skill tells an agent to read the URL the command prints and
    fetch it; the launch smoke test does the same. Both are only sound if the
    announce follows the bind: the socket must be bound and LISTENING (and the
    real app attached) before either the human ``CAD Viewer URL:`` line or the
    ``--json`` line is written, so the first request after reading the line
    answers 200 with no retry, no sleep, and no grace period. The 1s socket
    timeout is the pin: an announce printed before the bind refuses the
    connection outright, and one printed before the app is attached (or before
    ``serve_forever`` is reachable) leaves the request hanging past it.
    """

    ANNOUNCE_TO_200_BUDGET_SECONDS = 1.0

    def _first_request_after(self, child: subprocess.Popen, marker: str, port: int) -> float:
        stdout = self.wait_for_url_line(child, marker=marker)
        announced = next(line for line in stdout.split("\n") if line.startswith(marker))
        if marker == "{":
            url = json.loads(announced)["url"]
        else:
            url = announced[len(marker):].strip()
        self.assertEqual(url, f"http://127.0.0.1:{port}/")

        started = time.monotonic()
        # One attempt. The timeout bounds connect AND the response read.
        with urllib.request.urlopen(f"{url}__cad/server", timeout=self.ANNOUNCE_TO_200_BUDGET_SECONDS) as response:
            self.assertEqual(response.status, 200)
            info = json.loads(response.read())
        elapsed = time.monotonic() - started
        self.assertEqual(info["port"], port)
        self.assertLess(
            elapsed,
            self.ANNOUNCE_TO_200_BUDGET_SECONDS,
            f"the announced URL took {elapsed:.3f}s to answer its first request",
        )
        return elapsed

    def test_the_human_url_line_answers_the_first_request(self) -> None:
        port = 3203
        child = self.launch(["--dist", self.make_dist(), "--port", str(port)], cwd=self.make_root())
        self._first_request_after(child, "CAD Viewer URL: ", port)

    def test_the_json_line_answers_the_first_request(self) -> None:
        port = 3204
        child = self.launch(["--dist", self.make_dist(), "--port", str(port), "--json"], cwd=self.make_root())
        self._first_request_after(child, "{", port)


class RollAndReuse(LauncherFixture):
    def test_default_launch_rolls_and_a_second_root_rolls_past_the_first(self) -> None:
        dist = self.make_dist()
        first = self.launch(["--dist", dist, "--json"], cwd=self.make_root())
        a = self.json_line(self.wait_for_url_line(first))
        self.assertEqual(a["action"], "started")
        self.assertGreaterEqual(a["port"], 3245, "rolled port must be >= the base")

        # Different directory, no reuse match -> its own instance on another port.
        second = self.launch(["--dist", dist, "--json"], cwd=self.make_root())
        b = self.json_line(self.wait_for_url_line(second))
        self.assertEqual(b["action"], "started")
        self.assertNotEqual(b["port"], a["port"], "an occupied candidate is rolled past, not refused")

    def test_same_root_reuses_and_new_forces_a_fresh_instance(self) -> None:
        dist = self.make_dist()
        root = self.make_root()
        first = self.launch(["--dist", dist, "--json"], cwd=root)
        a = self.json_line(self.wait_for_url_line(first))

        # Reuse: same realpath(served dir) x identity token -> the existing URL,
        # exit 0, no spawn. Note NO --dist: the dist check happens after the
        # reuse lookup.
        code, stdout, _ = self.run_to_exit(["--json"], cwd=root)
        self.assertEqual(code, 0)
        self.assertEqual(
            self.json_line(stdout), {"url": a["url"], "port": a["port"], "action": "reused"}
        )
        self.assertRegex(stdout, r"Reusing CAD Viewer at ")

        # Reuse must also work when launched from a symlinked spelling of the
        # same directory (the reuse key is the realpath).
        alias_parent = tempfile.mkdtemp(dir=self._tmp.name, prefix="cad-alias-")
        alias = os.path.join(alias_parent, "link")
        os.symlink(root, alias)
        code, stdout, _ = self.run_to_exit(["--json"], cwd=alias)
        self.assertEqual(code, 0)
        self.assertEqual(self.json_line(stdout)["action"], "reused")

        # --new bypasses the lookup and starts a second instance.
        fresh = self.launch(["--dist", dist, "--json", "--new"], cwd=root)
        c = self.json_line(self.wait_for_url_line(fresh))
        self.assertEqual(c["action"], "started")
        self.assertNotEqual(c["port"], a["port"])

    def test_a_no_registry_instance_is_never_reused(self) -> None:
        # The dev backend runs --no-registry precisely so a later real launch
        # from the same directory starts fresh instead of handing back a Vite
        # proxy target.
        dist = self.make_dist()
        root = self.make_root()
        dev = self.launch(["--dist", dist, "--json", "--ephemeral", "--no-registry"], cwd=root)
        a = self.json_line(self.wait_for_url_line(dev))
        self.assertEqual(a["action"], "started")

        code, stdout, _ = self.run_to_exit(["list", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.strip()), [], "a --no-registry instance must not be listed")

        real = self.launch(["--dist", dist, "--json"], cwd=root)
        b = self.json_line(self.wait_for_url_line(real))
        self.assertEqual(b["action"], "started", "must start fresh, not reuse the dev backend")
        self.assertNotEqual(b["port"], a["port"])

    def test_ephemeral_binds_a_free_port_and_reports_it(self) -> None:
        # --ephemeral exists because `--port 0` means STRICT 3245 (Number(0) is
        # falsy but still sets portExplicit), so it could not be overloaded.
        dist = self.make_dist()
        child = self.launch(["--dist", dist, "--json", "--ephemeral"], cwd=self.make_root())
        payload = self.json_line(self.wait_for_url_line(child))
        self.assertGreater(payload["port"], 0)
        self.assertIn(f":{payload['port']}/", payload["url"])
        with urllib.request.urlopen(f"http://127.0.0.1:{payload['port']}/__cad/server", timeout=5) as r:
            self.assertEqual(json.loads(r.read())["port"], payload["port"])


class IdentityToken(LauncherFixture):
    """Reuse identity is the version SALTED with the app files' newest mtime.

    The version alone is frozen between releases, so in a checkout a `git pull`
    followed by a launch reused a resident server running last week's code.
    With the salt, a resident whose code has since changed on disk fails the
    match, a fresh instance starts, and the old one is left alone.

    Everything runs against a STAGED copy of the cadgen package + its own dist,
    so touching mtimes never dirties the real checkout — whose developer may
    have a live viewer keyed on those very files.
    """

    def stage_app(self) -> str:
        staged = os.path.join(self._tmp.name, "staged-identity")
        # The whole package, not just cadgen/viewer: the child imports `cadgen`
        # first, and a half-package on PYTHONPATH would shadow the real one.
        shutil.copytree(
            str(PACKAGE_DIR.parent),
            os.path.join(staged, "src", "cadgen"),
            ignore=shutil.ignore_patterns("__pycache__", "_runtime"),
        )
        os.makedirs(os.path.join(staged, "dist"))
        Path(staged, "dist", "index.html").write_text("<html>viewer</html>", encoding="utf-8")
        return staged

    def launch_staged(self, staged: str, root: str) -> subprocess.Popen:
        child = subprocess.Popen(
            [*LAUNCH, "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=root,
            env=self.env(
                PYTHONPATH=os.path.join(staged, "src"),
                # The default dist location is the salt's other half.
                CADGEN_VIEWER_DIST=os.path.join(staged, "dist"),
            ),
        )
        self._children.append(child)
        return child

    @staticmethod
    def server_info(port: int) -> dict:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__cad/server", timeout=5) as response:
            return json.loads(response.read())

    def test_a_stale_resident_fails_the_match_and_is_left_alone(self) -> None:
        staged = self.stage_app()
        root = self.make_root()
        first = self.launch_staged(staged, root)
        a = self.json_line(self.wait_for_url_line(first))
        self.assertEqual(a["action"], "started")

        # Same code on disk -> reused, exactly as before the salt existed.
        relaunch = self.launch_staged(staged, root)
        reused_stdout, _ = relaunch.communicate(timeout=30)
        self.assertEqual(self.json_line(reused_stdout)["action"], "reused")

        token_at_start = self.server_info(a["port"])["identityToken"]
        self.assertRegex(token_at_start, r"^[^:]*:\d+$", "the token is version:mtime")

        # A pull: a server source's mtime moves forward.
        future = time.time() + 60
        os.utime(os.path.join(staged, "src", "cadgen", "viewer", "scanner.py"), (future, future))

        # The resident answers with the token computed AT ITS OWN START —
        # never a re-read, which would let a stale server claim freshness.
        self.assertEqual(self.server_info(a["port"])["identityToken"], token_at_start)

        # The next launch computes a token the resident's entry no longer
        # matches: a NEW instance starts, and the old one is left alone.
        second = self.launch_staged(staged, root)
        b = self.json_line(self.wait_for_url_line(second))
        self.assertEqual(b["action"], "started")
        self.assertNotEqual(b["port"], a["port"])
        self.assertNotEqual(self.server_info(b["port"])["identityToken"], token_at_start)
        self.assertEqual(
            self.server_info(a["port"])["pid"], first.pid, "the stale resident keeps running"
        )

        # The dist is the other half of the app: a rebuilt client re-keys too.
        os.utime(os.path.join(staged, "dist", "index.html"), (future + 60, future + 60))
        third = self.launch_staged(staged, root)
        c = self.json_line(self.wait_for_url_line(third))
        self.assertEqual(c["action"], "started", "a rebuilt dist must not reuse the old client")
        self.assertNotIn(c["port"], (a["port"], b["port"]))


class DistFreshnessWarning(unittest.TestCase):
    """The dev-only staleness guard: one stderr line, detection only.

    Exists because a stale locally-built client manufactured a false bug
    report (a pose-preset 'bug' that was just an old bundle). Tested at the
    function: the launch path calls it once, right before binding.
    """

    main_module = main_module

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dist = os.path.join(self._tmp.name, "dist")
        os.makedirs(self.dist)
        Path(self.dist, "index.html").write_text("<html>viewer</html>", encoding="utf-8")

    def _warning_output(self) -> str:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.main_module.warn_when_dist_is_stale(self.dist)
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
        # A published bundle ships dist/ with no src/ beside it: nothing to
        # compare, no walk, no warning — by construction, not by tuning.
        self.assertEqual(self._warning_output(), "")


class ApiOnly(LauncherFixture):
    """`npm run dev` must work on a checkout that has never been built.

    dist/ is gitignored, so a fresh clone has none — and the dev server does not
    need one, because Vite serves the client and proxies only the API here.
    Requiring a build made `npm run dev` fail on first contact, reported through
    the proxy as a backend that died at startup.
    """

    def test_it_serves_the_api_with_no_dist_anywhere(self) -> None:
        # No --dist, and --api-only never consults the fallback either, so a
        # built checkout cannot mask the regression this pins.
        child = self.launch(
            ["--json", "--ephemeral", "--no-registry", "--api-only"], cwd=self.make_root()
        )
        stdout = self.wait_for_url_line(child)
        port = self.json_line(stdout)["port"]
        self.assertIn("Starting CAD Viewer API at ", stdout)

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__cad/server", timeout=5) as response:
            self.assertEqual(json.loads(response.read())["port"], port)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__cad/catalog", timeout=5) as response:
            self.assertIn("entries", json.loads(response.read()))

        # The client is Vite's job in this mode, so the SPA routes are a plain
        # 404 rather than a boot failure.
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
        self.assertEqual(caught.exception.code, 404)

    def test_without_it_a_missing_client_still_refuses_to_start(self) -> None:
        # The exemption must be exactly as wide as --api-only: a PRODUCTION launch
        # with no built client stays a hard, named failure.
        #
        # CADGEN_VIEWER_DIST wins the default-dist resolution, so pointing it
        # at an EMPTY directory makes "no client anywhere" true regardless of
        # whether this checkout has built apps/viewer. Skipping when the
        # developer's own checkout happens to be built would mean skipping in
        # CI too, which builds the client before it runs the tests.
        nowhere = self.make_root()
        code, _, stderr = self.run_to_exit([], cwd=self.make_root(), CADGEN_VIEWER_DIST=nowhere)
        self.assertEqual(code, 1)
        self.assertIn("No built CAD Viewer client found", stderr)
        self.assertIn("--api-only", stderr, "the refusal must name the dev-mode escape")

    def test_the_same_launch_starts_once_it_is_given_a_client(self) -> None:
        # Control for the test above: same command, the env now naming a real
        # dist. Without this, a refusal caused by something unrelated would
        # read as the dist check working.
        child = self.launch(
            ["--json", "--ephemeral", "--no-registry"],
            cwd=self.make_root(),
            CADGEN_VIEWER_DIST=self.make_dist(),
        )
        self.assertEqual(self.json_line(self.wait_for_url_line(child))["action"], "started")


class InterpreterFloor(unittest.TestCase):
    """The floor is enforced at startup, not discovered on the first request.

    macOS ships 3.9 as `python3` — the default the dev server spawns — and on
    3.9 this server used to boot, print the URL contract, and then answer the
    catalog with a raw ``realpath() got an unexpected keyword argument
    'strict'``.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.main_module = main_module

    def test_the_interpreter_running_this_suite_is_accepted(self) -> None:
        self.assertEqual(self.main_module.unsupported_python_message(), "")

    def test_an_interpreter_below_the_floor_is_named_along_with_the_way_out(self) -> None:
        message = self.main_module.unsupported_python_message(
            version_info=(3, 9, 6, "final", 0), executable="/usr/bin/python3"
        )
        self.assertIn("3.11", message, "the message must name the version required")
        self.assertIn("3.9.6", message, "and the version actually running")
        self.assertIn("/usr/bin/python3", message, "and WHICH interpreter that was")
        self.assertIn("VIEWER_PYTHON", message, "and how to point dev at another one")

    def test_the_guard_parses_and_fires_under_an_interpreter_that_predates_the_floor(self) -> None:
        # The refusal is worthless if the module cannot be PARSED by the
        # interpreter it is refusing: a SyntaxError anywhere above the guard
        # replaces the friendly message with a traceback. Parse everything up to
        # and including the guard against 3.9's grammar.
        source = Path(self.main_module.__file__).read_text(encoding="utf-8")
        guard, marker, _ = source.partition("_UNSUPPORTED_PYTHON = unsupported_python_message()")
        self.assertTrue(marker, "the startup guard moved; update this test")
        ast.parse(guard + marker, filename="main.py", feature_version=(3, 9))

        # ...and check the guard itself trips for every version below the floor.
        for version in ((3, 9, 6), (3, 10, 14), (2, 7, 18)):
            self.assertNotEqual(
                self.main_module.unsupported_python_message(version_info=version), "", str(version)
            )
        self.assertEqual(
            self.main_module.unsupported_python_message(version_info=(3, 11, 0)),
            "",
            "3.11 is the floor, not the first version above it",
        )


class Refusals(LauncherFixture):
    @unittest.skipIf(os.name == "nt", "Windows refuses to delete a process's cwd")
    def test_a_cwd_deleted_underfoot_refuses_before_binding(self) -> None:
        # The served directory is the cwd, and a cwd always exists — unless it
        # was deleted underneath the shell, in which case os.getcwd() raises.
        # That must surface as a clean one-line refusal, not a traceback:
        # booting anyway would answer every request with a 404 that looks like
        # a missing model rather than a missing directory. In-process rather
        # than a subprocess because Popen(cwd=...) refuses a missing directory
        # in the PARENT, so a child can never be started inside one.
        dist = self.make_dist()
        doomed = tempfile.mkdtemp(dir=self._tmp.name, prefix="cad-doomed-")
        held = os.getcwd()
        os.chdir(doomed)
        try:
            os.rmdir(doomed)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = main_module.main(["--dist", dist, "--port", "3999"])
        finally:
            os.chdir(held)
        self.assertEqual(code, 1)
        self.assertIn("no longer exists", stderr.getvalue())

    def test_dist_resolution_falls_back_and_then_gives_up(self) -> None:
        # Tested at the function, with the default location pinned through
        # CADGEN_VIEWER_DIST so the checkout's own build cannot mask a case.
        dist = self.make_dist()
        fallback = self.make_dist()
        empty = self.make_root()  # a directory with no index.html
        previous = os.environ.get("CADGEN_VIEWER_DIST")
        try:
            os.environ["CADGEN_VIEWER_DIST"] = fallback
            self.assertEqual(main_module.resolve_dist_dir(dist), os.path.abspath(dist))
            # realpath on both sides: the env resolver canonicalizes, and macOS
            # spells the temp dir through a /var -> /private/var symlink.
            self.assertEqual(
                os.path.realpath(main_module.resolve_dist_dir(empty)),
                os.path.realpath(fallback),
                "an explicit --dist without index.html falls through to the default location",
            )
            os.environ["CADGEN_VIEWER_DIST"] = empty
            self.assertEqual(main_module.resolve_dist_dir(""), "", "no index.html anywhere is no client")
        finally:
            if previous is None:
                os.environ.pop("CADGEN_VIEWER_DIST", None)
            else:
                os.environ["CADGEN_VIEWER_DIST"] = previous


class ListAndStop(LauncherFixture):
    def test_list_reports_a_running_instance_and_stop_terminates_it(self) -> None:
        dist = self.make_dist()
        root = self.make_root()
        child = self.launch(["--dist", dist, "--json"], cwd=root)
        started = self.json_line(self.wait_for_url_line(child))
        port = started["port"]

        code, stdout, _ = self.run_to_exit(["list"])
        self.assertEqual(code, 0)
        self.assertIn("1 CAD Viewer running:", stdout)
        # The launch smoke test greps for this exact two-space-separated token.
        self.assertIn(f"port {port}", stdout)
        # The registry records os.getcwd()'s spelling of the root, which is the
        # PHYSICAL path on macOS (/var is a symlink to /private/var) and the 8.3
        # short form on Windows when TEMP is spelled that way (RUNNER~1). Resolve
        # both sides rather than pinning one platform's spelling.
        serving = [
            line.split("serving", 1)[1].strip()
            for line in stdout.splitlines()
            if line.strip().startswith("serving  ")
        ]
        self.assertEqual(len(serving), 1, stdout)
        self.assertEqual(os.path.realpath(serving[0]), os.path.realpath(root))

        code, stdout, _ = self.run_to_exit(["list", "--json"])
        entries = json.loads(stdout.strip())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["port"], port)
        self.assertEqual(entries[0]["pid"], child.pid)

        code, stdout, _ = self.run_to_exit(["stop", "--port", str(port)])
        self.assertEqual(code, 0)
        self.assertIn("Stopped CAD Viewer", stdout)
        # A BOUNDED wait, not an instantaneous poll. `stop` returns as soon as
        # the port stops ANSWERING, and main.py deliberately allows itself up to
        # another 0.5s to leave after that (the os._exit fallback, so an
        # in-flight stream cannot outlive the stop budget). Reading "the socket
        # closed" as "the process is reaped" made this assertion a coin flip
        # that any millisecond-scale change elsewhere in the server could tip.
        # What the contract promises is that it exits, promptly — so wait for
        # that, well inside the 3s `stop` itself budgets.
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - the failure this guards
            self.fail("the server process must have exited after stop")

        code, stdout, _ = self.run_to_exit(["list"])
        self.assertIn("No CAD Viewer is running.", stdout)

    def test_stop_without_a_selector_exits_2(self) -> None:
        code, _, stderr = self.run_to_exit(["stop"])
        self.assertEqual(code, 2)
        self.assertIn("Specify which viewer to stop", stderr)

    def test_stop_for_an_unknown_port_exits_1(self) -> None:
        code, _, stderr = self.run_to_exit(["stop", "--port", "3987"])
        self.assertEqual(code, 1)
        self.assertIn("No running CAD Viewer for port 3987.", stderr)

    def test_list_with_no_instances(self) -> None:
        code, stdout, _ = self.run_to_exit(["list"])
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "No CAD Viewer is running.\n")


class ArgumentGrammar(unittest.TestCase):
    """The parse rules, in-process — no launch needed to pin argument handling.

    argparse now, with the launcher's refusal shape kept: an unknown argument is
    a refusal naming the FIRST unknown token, and every refusal exits 2.
    """

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

    def test_port_zero_and_garbage_are_refused_not_defaulted(self) -> None:
        # The old hand-rolled parser read `--port 0` and `--port abc` as a
        # STRICT 3245 — a typo silently changed what the launcher did. Both are
        # refusals now; --ephemeral is the spelling for "any free port".
        self.assertIn("port out of range", self.refuses(["--port", "0"]))
        self.assertIn("not a port number", self.refuses(["--port", "abc"]))

    def test_an_out_of_range_port_is_refused(self) -> None:
        for value in ("70000", "-1"):
            self.assertIn("port out of range", self.refuses(["--port", value]), value)

    def test_a_valueless_trailing_port_is_refused(self) -> None:
        self.assertIn("--port", self.refuses(["--port"]))

    def test_port_and_ephemeral_are_mutually_exclusive(self) -> None:
        # One asks for THIS port, the other for ANY port; both at once is a
        # contradiction the old parser resolved silently in --ephemeral's favour.
        self.assertIn("not allowed with", self.refuses(["--port", "3999", "--ephemeral"]))

    def test_an_explicit_port_is_strict_and_the_default_is_not(self) -> None:
        explicit = self.parse(["--port", "3999"])
        self.assertEqual(explicit["port"], 3999)
        self.assertTrue(explicit["port_explicit"])
        default = self.parse([])
        self.assertEqual(default["port"], 3245)
        self.assertFalse(default["port_explicit"])

    def test_the_three_dev_flags_default_off_and_are_independent(self) -> None:
        defaults = self.parse([])
        for flag in ("ephemeral", "no_registry", "api_only"):
            self.assertFalse(defaults[flag], flag)
        for argument, key in (
            ("--ephemeral", "ephemeral"),
            ("--no-registry", "no_registry"),
            ("--api-only", "api_only"),
        ):
            args = self.parse([argument])
            self.assertTrue(args[key], argument)
            others = {"ephemeral", "no_registry", "api_only"} - {key}
            for other in others:
                self.assertFalse(args[other], f"{argument} must not imply --{other}")

    def test_repeated_flags_take_the_last_value(self) -> None:
        self.assertEqual(self.parse(["--host", "a", "--host", "b"])["host"], "b")

    def test_no_abbreviations(self) -> None:
        # `--ap` for --api-only is exactly the kind of accidental match a typo
        # becomes. argparse abbreviates by default; the launcher must not.
        self.assertIn("unknown argument: --ap", self.refuses(["--ap"]))

    def test_the_served_directory_is_the_cwd_with_no_special_cases(self) -> None:
        # No flag, no environment variable: the cwd IS the served directory,
        # even inside the package itself — serving the Viewer's own directory
        # is legitimate, and refusing it would be a special case to explain.
        for cwd in (str(PACKAGE_DIR), str(PACKAGE_DIR.parent)):
            with self.subTest(cwd=cwd):
                held = os.getcwd()
                os.chdir(cwd)
                try:
                    self.assertEqual(main_module.served_directory(), cwd)
                finally:
                    os.chdir(held)


class ArgumentSurface(unittest.TestCase):
    """A launcher that answers --help by starting a server reads as broken, and
    a tolerated typo silently changes what it serves.

    Both were real: `--help` used to fall through the parser and boot an
    instance, and a misspelled flag started a viewer on the invocation directory
    and served an empty catalog while looking fine.
    """

    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [*LAUNCH, *argv],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_help_answers_on_stdout_and_starts_nothing(self) -> None:
        result = self._run("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: python -m cadgen.viewer", result.stdout)
        self.assertIn("--host", result.stdout)
        self.assertIn("python -m cadgen.viewer list", result.stdout, "the manager verbs are in the usage")
        self.assertIn("python -m cadgen.viewer stop", result.stdout)
        self.assertNotIn("--root", result.stdout, "the launcher has no directory flag")
        self.assertEqual(result.stderr, "")

    def test_short_help_is_the_same_answer(self) -> None:
        self.assertEqual(self._run("-h").returncode, 0)

    def test_the_front_door_names_itself_in_help(self) -> None:
        # Through `cadgen viewer` the same parser says "cadgen viewer", so the
        # usage a user reads matches the command they typed.
        result = subprocess.run(
            [sys.executable, "-m", "cadgen.cli", "viewer", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: cadgen viewer", result.stdout)
        self.assertIn("cadgen viewer list", result.stdout)

    def test_an_unknown_argument_is_refused_not_ignored(self) -> None:
        result = self._run("--dir", "/tmp")
        self.assertEqual(result.returncode, 2)
        # The FIRST unknown token, not the value that trailed it.
        self.assertIn("unknown argument: --dir", result.stderr)
        self.assertNotIn("/tmp", result.stderr.splitlines()[0])

    def test_the_retired_root_flag_is_refused_not_silently_dropped(self) -> None:
        # The served directory is the cwd now. An old-style `--root <dir>`
        # invocation must refuse rather than boot a viewer serving the wrong
        # directory (the cwd) while looking successful.
        result = self._run("--root", "/tmp")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown argument: --root", result.stderr)

    def test_a_manager_verb_after_a_flag_is_a_serve_refusal(self) -> None:
        # Only argv[0] selects list/stop: `--json list` is a serve invocation
        # with an unknown argument, not a list.
        result = self._run("--json", "list")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown argument: list", result.stderr)


if __name__ == "__main__":
    unittest.main()
