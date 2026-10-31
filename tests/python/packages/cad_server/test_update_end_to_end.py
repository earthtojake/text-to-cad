"""The update end to end, as a person's machine runs it (``cad_server._internal.update``, ``switch``,
``releases``): release A set up by its own ``cad setup`` in a home of this test's own, its engine
started as any client starts it; release B published -- its wheel in a folder uv reads beside the
index (``CAD_UPDATE_FIND_LINKS``), and named by a version feed served here (``CAD_API_URL``);
then the button's request (``POST /__cad/update``, ``cad_server.viewer.http_app``), and the engine back on
the same port, with the same token, running B -- the answer a page reloads on --, A's folder kept as
the way back.

Each release is this source tree's library and server as wheels, the library's ``build123d`` extra naming
nothing: the update's path is what is tested, and the kernel's install is uv's (the base's own tests
make it). uv takes their dependencies from its cache where it holds them, as an update does on a
person's machine; the wheels it keeps there, under versions of this run's own, are taken out again
(``forget``)."""

from __future__ import annotations

import base64
import hashlib
import http.client
import http.server
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
import tomllib
import unittest
import zipfile
from pathlib import Path

from tests.python.support.paths import LIBRARY, SERVER, add_sources

add_sources()

from cad_server._internal import base, plugin, providers  # noqa: E402

# Each release's wheels, by distribution: its project, its packages, and what its wheel carries at its root.
DISTRIBUTIONS = {"cad": (LIBRARY, ("cad", "cadgen"), ("cad-lazy-kernel.pth",)),
                 "cad-server": (SERVER, ("cad_server",), ())}
# Releases of this run alone (the process's id in them): what uv keeps of their wheels is this run's
# to take out again, and a run beside it in another checkout builds others.
_RUN = os.getpid() % 100_000
A, B = f"9.{_RUN}.0", f"9.{_RUN}.1"
# The ports the person's own engines and other sessions' serve on: never this test's.
TAKEN = range(3245, 3251)
WINDOWS = os.name == "nt"


def plugin_files() -> dict[str, bytes]:
    """A plugin of the test's own where the server's wheel carries its plugin (``_runtime/plugin``): every
    file the plugin folder is written from, and a skill."""
    server = {"mcpServers": {"cad": {"command": "uvx", "args": ["--from", "cad-mcp==0.0.0", "cad-mcp"]}}}
    files = {name: b"bytes" for name in plugin.FILES}
    files.update({name: json.dumps({"name": "text-to-cad", "version": "0.0.0"}).encode() for name in plugin.MANIFESTS})
    files.update({name: json.dumps(server).encode() for name in ("claude.mcp.json", "codex.mcp.json", "cursor.mcp.json",
                                                                 "mcp.json")})
    files["gemini-extension.json"] = json.dumps({"name": "text-to-cad", "version": "0.0.0", **server}).encode()
    files[plugin.CATALOG] = json.dumps({"name": "x", "plugins": [{"name": "text-to-cad", "source": "./"}]}).encode()
    files["skills/cad/SKILL.md"] = b"---\nname: cad\n---\n"
    return {f"cad_server/_runtime/plugin/{name}": data for name, data in files.items()}


def wheel(distribution: str, version: str, folder: Path) -> Path:
    """This source tree's ``distribution`` as a wheel of release ``version``: its packages and package data
    but the built runtime (``_runtime``: nothing here serves a page; the plugin is the test's own,
    ``plugin_files``), what it carries at its root, its dependencies -- the library pinned at ``version``
    -- and command as ``pyproject.toml`` declares them, and a ``build123d`` extra that names nothing."""
    source, packages, roots = DISTRIBUTIONS[distribution]
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    stem = distribution.replace("-", "_")
    info = f"{stem}-{version}.dist-info"
    files: dict[str, bytes] = {name: (source / name).read_bytes() for name in roots}
    if distribution == "cad-server":
        files.update(plugin_files())
    for top in packages:
        package = source / "src" / top
        for path in sorted(package.rglob("*")):
            parts = path.relative_to(package).parts
            if (path.is_file() and parts[0] != "_runtime" and "__pycache__" not in parts and path.suffix != ".pyc"
                    and not path.name.startswith(".")):
                files["/".join((top, *parts))] = path.read_bytes()
    requirements = [f"cad=={version}" if requirement.startswith("cad==") else requirement
                    for requirement in project["dependencies"]]
    metadata = ["Metadata-Version: 2.4", f"Name: {distribution}", f"Version: {version}",
                f"Requires-Python: {project['requires-python']}",
                *(f"Requires-Dist: {requirement}" for requirement in requirements), "Provides-Extra: build123d"]
    files[f"{info}/METADATA"] = ("\n".join(metadata) + "\n").encode("utf-8")
    files[f"{info}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: text-to-cad tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    files[f"{info}/entry_points.txt"] = ("[console_scripts]\n" + "".join(
        f"{name} = {target}\n" for name, target in project.get("scripts", {}).items())).encode("utf-8")
    record = [f"{name},sha256={base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()},{len(data)}"
              for name, data in files.items()]
    files[f"{info}/RECORD"] = ("\n".join([*record, f"{info}/RECORD,,"]) + "\n").encode("utf-8")
    out = folder / f"{stem}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return out


def release(version: str, folder: Path) -> None:
    """Release ``version`` published to ``folder``: the library's wheel and the server's."""
    for distribution in DISTRIBUTIONS:
        wheel(distribution, version, folder)


class Feed(http.server.ThreadingHTTPServer):
    """The version feed (``GET /v1/versions``), saying ``latest``; anything else is not found."""

    def __init__(self) -> None:
        self.latest = A
        feed = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - http.server's name
                body = json.dumps({"latest": feed.latest}).encode("utf-8")
                self.send_response(200 if self.path == "/v1/versions" else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:
                pass

        super().__init__(("127.0.0.1", 0), Handler)


def forget(uv_cache: Path, versions: tuple[str, ...]) -> list[str]:
    """This run's wheels taken out of uv's cache: uv keeps each wheel a folder of wheels served it --
    its unpacked archive, and the index entry that names it -- after the folder is gone, about 5 MB a
    wheel. Found by what they are (``<distribution>-<version>.dist-info``, the entries named by the
    version), so nothing else of the cache is touched, and nothing at all where uv lays its cache out
    otherwise."""
    removed: list[str] = []
    root = uv_cache.resolve()
    names = [(distribution.replace("-", "_"), distribution) for distribution in DISTRIBUTIONS]
    for version in versions:
        for stem, _name in names:
            for found in root.glob(f"archive-v*/*/{stem}-{version}.dist-info"):
                shutil.rmtree(found.parent, ignore_errors=True)
                removed.append(str(found.parent))
        for entry in (entry for _stem, name in names for entry in root.glob(f"wheels-v*/index/*/{name}/{version}-*")):
            # A link to the archive (on Windows perhaps a junction: taken out, never followed), or its lock
            # or revision file; a real folder is not one of these, and is left.
            try:
                if entry.is_symlink() or os.path.isjunction(entry):
                    try:
                        entry.unlink()
                    except OSError:
                        os.rmdir(entry)
                elif entry.is_file():
                    entry.unlink()
                else:
                    continue
            except OSError:
                continue
            removed.append(str(entry))
    for folder in (folder for _stem, name in names for folder in root.glob(f"wheels-v*/index/*/{name}")):
        for empty in (folder, folder.parent):
            try:
                empty.rmdir()  # only an empty one: an index another run shares keeps its entries
            except OSError:
                break
    return removed


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert port not in TAKEN, port
    return port


def command(env: Path) -> Path:
    """The ``cad`` command of the environment at ``env``."""
    return env / ("Scripts/cad.exe" if WINDOWS else "bin/cad")


class UpdateEndToEndTest(unittest.TestCase):
    def setUp(self) -> None:
        # Short, under /tmp: the engine's door is a Unix socket in its folder, whose path caps near 104 bytes.
        self.work = Path(tempfile.mkdtemp(prefix="cu.", dir=None if WINDOWS else "/tmp")).resolve()
        self.addCleanup(shutil.rmtree, self.work, True)
        self.feed = Feed()
        threading.Thread(target=self.feed.serve_forever, daemon=True).start()
        self.addCleanup(self.feed.server_close)
        self.addCleanup(self.feed.shutdown)
        self.port = free_port()
        self.wheels = self.work / "wheels"
        self.wheels.mkdir()
        home = self.work / "home"
        # uv and uvx where uv's installer puts them, as the install command leaves them: Claude Desktop's
        # entry runs CAD's server with that uvx.
        tools = home / ".local" / "bin"
        tools.mkdir(parents=True)
        uv = Path(base.find_uv())
        for name in ("uv", "uvx"):
            found = shutil.which(name) or str(uv.with_name(name + uv.suffix))
            if not os.path.isfile(found):
                self.skipTest(f"no {name} here")
            try:
                (os.link if WINDOWS else os.symlink)(found, tools / Path(found).name)
            except OSError:  # another volume than the test's folder
                shutil.copy2(found, tools / Path(found).name)
        self.env = self.environment(home)
        # The engine and every process of it go, whatever this test reached (this test's alone: each runs
        # from this test's folder).
        self.addCleanup(self.stop)

    def environment(self, home: Path) -> dict[str, str]:
        """A machine of this test's own: its home, state, cache, engine and command folders; no agent app's
        command on PATH, nor the Codex app's; the feed and the folder of wheels; the port; no telemetry."""
        uv_cache = os.environ.get("UV_CACHE_DIR") or subprocess.run(
            [base.find_uv(), "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
        self.addCleanup(forget, Path(uv_cache), (A, B))
        dropped = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV", "CONDA_PREFIX", "CI", "CODEX_HOME",
                   "CLAUDE_CONFIG_DIR", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                   "XDG_BIN_HOME", "UV_INSTALL_DIR")
        env = {key: value for key, value in os.environ.items() if not key.startswith("CAD_") and key not in dropped}
        system = os.environ.get("SystemRoot", r"C:\Windows")
        bypass = ",".join(filter(None, ("127.0.0.1,localhost", os.environ.get("NO_PROXY") or os.environ.get("no_proxy"))))
        env.update({
            "HOME": str(home), "PATH": os.pathsep.join([rf"{system}\System32", system] if WINDOWS else ["/usr/bin", "/bin"]),
            "UV_CACHE_DIR": uv_cache, "NO_PROXY": bypass, "no_proxy": bypass, "DO_NOT_TRACK": "1",
            "BROWSER": "true", "CODEX_CLI": str(self.work / "no-codex"),
            "CAD_STATE_DIR": str(self.work / "state"), "CAD_CACHE_DIR": str(self.work / "cache"),
            "CAD_ENGINE_DIR": str(self.work / "engine"), "CAD_LAUNCHER_DIR": str(self.work / "bin"),
            "CAD_ENGINE_PORT": str(self.port), "CAD_API_URL": f"http://127.0.0.1:{self.feed.server_port}/v1",
            "CAD_UPDATE_FIND_LINKS": str(self.wheels),
        })
        if WINDOWS:
            env.update({"USERPROFILE": str(home), "APPDATA": str(home / "AppData" / "Roaming"),
                        "LOCALAPPDATA": str(home / "AppData" / "Local")})
        return env

    def run_here(self, argv: list, **options) -> subprocess.CompletedProcess:
        return subprocess.run([str(part) for part in argv], env=self.env, cwd=self.work, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", **options)

    def release(self, version: str) -> Path:
        return self.work / "state" / "releases" / version

    def stop(self) -> None:
        """The engine stopped, as any client stops it, and anything still running from this test's folder ended."""
        for version in (B, A):
            python = base.interpreter(self.release(version))
            if python.exists():
                self.run_here([python, "-c", "from cad.engine import client\n"
                               "client.request({'op': 'stop'}, start=False)\nclient.wait_gone(timeout=60)"], timeout=90)
                break
        if not WINDOWS:
            listed = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
            for line in listed.splitlines():
                pid, _, command = line.strip().partition(" ")
                if str(self.work) in command and pid.isdigit() and int(pid) != os.getpid():
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except OSError:
                        pass

    def version(self, token: str) -> tuple[int | None, dict]:
        """``GET /__cad/version`` on the port, as the page asks it: ``(status, answer)``; no status with no engine there."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("GET", "/__cad/version", headers={"Authorization": f"Bearer {token}"})
            response = connection.getresponse()
            body = response.read()
        except OSError:
            return None, {}
        finally:
            connection.close()
        return response.status, (json.loads(body) if response.status == 200 else {"body": body.decode("utf-8", "replace")})

    def said(self) -> str:
        log = self.work / "state" / "update.log"
        return log.read_text(encoding="utf-8", errors="replace") if log.exists() else "(no update log)"

    def test_the_button_installs_the_next_release_and_its_engine_takes_the_port_and_token(self) -> None:
        # Release A, as the install command sets it up: uvx's environment, whose `cad setup` makes A's
        # release folder and sets it up from there. Claude Desktop's folder is there: its config gets CAD's
        # server, A's, which the update moves to B's (an app updated with no app's command, no network).
        release(A, self.wheels)
        machine = providers.Machine(Path(self.env["HOME"]), self.env, platform=sys.platform, bundled={})
        desktop = providers.desktop_config(machine)
        desktop.parent.mkdir(parents=True)
        uv, boot = base.find_uv(), self.work / "uvx"
        made = self.run_here([uv, "venv", "--no-project", "--python", sys.executable, boot])
        self.assertEqual(made.returncode, 0, made.stderr)
        install = [uv, "pip", "install", "--python", base.interpreter(boot), "--find-links", self.wheels,
                   f"{base.SERVER}=={A}"]
        made = self.run_here([*install, "--offline"])
        if made.returncode != 0:
            made = self.run_here(install)
        self.assertEqual(made.returncode, 0, made.stderr)
        set_up = self.run_here([command(boot), "setup"], timeout=600)
        self.assertEqual(set_up.returncode, 0, set_up.stdout + set_up.stderr)
        self.assertEqual((self.work / "state" / "installations" / "current").read_text(encoding="utf-8"), A)
        self.assertTrue(desktop.is_file(), set_up.stdout + set_up.stderr)
        self.assertIn(f"cad-mcp=={A}", desktop.read_text(encoding="utf-8"))
        # The plugin folder every app is pointed at, A's.
        folder = self.work / "state" / plugin.FOLDER
        self.assertEqual(json.loads((folder / plugin.MANIFEST).read_text(encoding="utf-8"))["version"], A)

        # A's engine, started as any client starts it, serving on the port.
        started = self.run_here([base.interpreter(self.release(A)), "-c",
                                 "import json, sys\nfrom cad.engine import client\n"
                                 "print(json.dumps(client.request({'op': 'http', 'port': int(sys.argv[1])})))",
                                 str(self.port)], timeout=120)
        self.assertEqual(started.returncode, 0, started.stderr)
        token = json.loads(started.stdout.strip().splitlines()[-1])["token"]
        status, answer = self.version(token)
        self.assertEqual((status, answer.get("release"), answer.get("notice")), (200, A, None), answer)

        # B is published: its wheels where uv reads, the feed naming it.
        release(B, self.wheels)
        self.feed.latest = B

        # The click.
        clicked = time.monotonic()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        connection.request("POST", "/__cad/update", body=b"{}", headers={
            "Authorization": f"Bearer {token}", "x-cadgen-viewer": "1", "Content-Type": "application/json"})
        response = connection.getresponse()
        answer = json.loads(response.read())
        connection.close()
        self.assertEqual((response.status, answer["update"]["state"], answer["update"]["target"]),
                         (202, "working", B), answer)

        # What the page sees: the update's stages, the engine gone, then B's on the same port, admitting the
        # same token -- its release changed, which a page reloads on.
        stages: list[str] = []
        gone = back = None
        deadline = clicked + 300
        while back is None:
            self.assertLess(time.monotonic(), deadline, f"no engine of {B} answered\n{self.said()}")
            status, answer = self.version(token)
            if status is None:
                gone = gone or time.monotonic()
            elif status != 200:
                self.fail(f"the engine answered {status}: {answer}\n{self.said()}")
            elif answer["release"] == B:
                back = time.monotonic()
                break
            else:
                update = answer["update"]
                self.assertNotEqual(update["state"], "failed", f"{update.get('error')}\n{self.said()}")
                stage = (update.get("progress") or {}).get("stage")
                if stage and stage not in stages:
                    stages.append(stage)
            time.sleep(0.05)
        switched = json.loads((self.work / "state" / "update.json").read_text(encoding="utf-8"))
        self.assertEqual((switched["ok"], switched["from"], switched["to"], switched["port"]), (True, A, B, self.port),
                         switched)
        order = ("install", "build123d", "apps", "restart")  # cad_server._internal.update.STAGES: as the page saw them
        self.assertEqual(stages, sorted(stages, key=order.index))
        self.assertEqual((self.work / "state" / "installations" / "current").read_text(encoding="utf-8"), B)
        for version in (A, B):  # A's folder stays: the way back, and what a process of A's may still run from
            self.assertTrue((self.release(version) / "cadgen-release.json").is_file(), version)
        self.assertIn(f"cad-mcp=={B}", desktop.read_text(encoding="utf-8"))
        proxy = self.work / "bin" / ("cad.cmd" if WINDOWS else "cad")  # the cad command runs current
        self.assertEqual(self.run_here([proxy, "--version"]).stdout.strip(), f"cad {B}")
        # The plugin folder is B's, written by B's setup; the helper, once B's engine answered, had B write it
        # again (`cad plugin --refresh`), which found it already B's.
        self.assertEqual(json.loads((folder / plugin.MANIFEST).read_text(encoding="utf-8"))["version"], B)
        while f"text-to-cad {B}, up to date" not in self.said():
            self.assertLess(time.monotonic(), deadline, f"the helper did not have {B} write its plugin folder\n{self.said()}")
            time.sleep(0.05)
        print(f"\nupdate {A} -> {B}: {back - clicked:.1f} s from the click to {B}'s engine answering; no engine "
              f"for {switched['gapMs']} ms (the switch), {round((back - (gone or back)) * 1000)} ms as the page "
              "saw it", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
