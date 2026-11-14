"""A machine of a test's own, and releases of this source tree published to it.

``Machine``: its home, state, cache, engine and command folders (``CAD_STATE_DIR``, ``CAD_CACHE_DIR``,
``CAD_ENGINE_DIR``, ``CAD_LAUNCHER_DIR``), a version feed served here (``Feed``, ``CAD_API_URL``) and a folder of
wheels uv reads beside the index (``CAD_UPDATE_FIND_LINKS``); every server of it stopped, and every process from its
folder ended, as the test ends. ``release``: this source tree's library and server as wheels of a release of this run
(the library's ``build123d`` extra naming nothing: the kernel's install is uv's, which the base's own tests make).
uv takes their dependencies from its cache where it holds them; the wheels it keeps there, under versions of this
run's own, are taken out again (``forget``). Used by ``test_uninstall_end_to_end`` and
``scripts/test/rehearse-update.py``.
"""

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

from cad_server._internal import base  # noqa: E402

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


def wheel(distribution: str, version: str, folder: Path) -> Path:
    """This source tree's ``distribution`` as a wheel of release ``version``: its packages and package data
    but the built runtime (``_runtime``: nothing here serves a page), what it carries at its root, its dependencies -- the library pinned at ``version``
    -- and command as ``pyproject.toml`` declares them, and a ``build123d`` extra that names nothing."""
    source, packages, roots = DISTRIBUTIONS[distribution]
    project = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    stem = distribution.replace("-", "_")
    info = f"{stem}-{version}.dist-info"
    files: dict[str, bytes] = {name: (source / name).read_bytes() for name in roots}
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


class Machine(unittest.TestCase):
    """A machine of the test's own (``environment``), a version feed served here and a folder of wheels uv reads; every
    server of it stopped, and every process from its folder ended, as the test ends. No test of its own."""

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
        # uv and uvx where uv's installer puts them, as the install command leaves them.
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
        """A machine of this test's own: its home, state, cache, engine and command folders; a PATH of the system's
        alone; the feed and the folder of wheels; the port; no telemetry."""
        uv_cache = os.environ.get("UV_CACHE_DIR") or subprocess.run(
            [base.find_uv(), "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
        self.addCleanup(forget, Path(uv_cache), (A, B))
        dropped = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "VIRTUAL_ENV", "CONDA_PREFIX", "CI", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                   "XDG_BIN_HOME", "UV_INSTALL_DIR")
        env = {key: value for key, value in os.environ.items() if not key.startswith("CAD_") and key not in dropped}
        system = os.environ.get("SystemRoot", r"C:\Windows")
        bypass = ",".join(filter(None, ("127.0.0.1,localhost", os.environ.get("NO_PROXY") or os.environ.get("no_proxy"))))
        env.update({
            "HOME": str(home), "PATH": os.pathsep.join([rf"{system}\System32", system] if WINDOWS else ["/usr/bin", "/bin"]),
            "UV_CACHE_DIR": uv_cache, "NO_PROXY": bypass, "no_proxy": bypass, "DO_NOT_TRACK": "1",
            "BROWSER": "true",
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
        """Version ``version``'s server environment (``versions/<version>/code/server``)."""
        return self.work / "state" / "versions" / version / "code" / "server"

    def stop(self) -> None:
        """Each version's server stopped, as any client of it stops it, and anything still running from this test's
        folder ended."""
        versions = self.work / "state" / "versions"
        for version in sorted(os.listdir(versions), reverse=True) if versions.is_dir() else []:
            python = base.interpreter(self.release(version))
            if python.exists():
                self.run_here([python, "-c", "from cad.engine import client\n"
                               "client.request({'op': 'stop'}, start=False)\nclient.wait_gone(timeout=60)"], timeout=90)
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
        """``GET /api/v1/server`` on the port, as the page asks it: ``(status, answer)``; no status with no engine there."""
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request("GET", "/api/v1/server", headers={"Authorization": f"Bearer {token}"})
            response = connection.getresponse()
            body = response.read()
        except (OSError, http.client.HTTPException):
            # Refused or reset, or an answer cut short as the engine went (its headers sent, its body not:
            # http.client's IncompleteRead, which is no OSError): no engine there, as the page's fetch finds.
            return None, {}
        finally:
            connection.close()
        return response.status, (json.loads(body) if response.status == 200 else {"body": body.decode("utf-8", "replace")})

    def said(self) -> str:
        """What the state folder holds: the pointer, the mirror, the versions present."""
        state = self.work / "state"
        read = lambda path: path.read_text(encoding="utf-8").strip() if path.exists() else "(none)"  # noqa: E731
        versions = sorted(os.listdir(state / "versions")) if (state / "versions").is_dir() else []
        return (f"default {read(state / 'default')}, current {read(state / 'installations' / 'current')}, "
                f"versions {versions}")

    def running(self) -> str:
        """Every process still running from this test's folder, its pid and command line."""
        if WINDOWS:
            listing = ["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"]
        else:
            listing = ["ps", "-axo", "pid=,command="]
        try:
            listed = subprocess.run(listing, capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError) as error:
            return f"(could not list the processes: {error})"
        found = [line.strip() for line in listed.splitlines() if str(self.work) in line]
        return "processes from the test's folder:\n" + ("\n".join(found) if found else "(none)")

    def installer(self, version: str) -> Path:
        """Release ``version``'s server environment as the install command makes it (uvx's, outside the state folder),
        from the folder of wheels: what its ``cad setup`` and ``cad uninstall`` run from."""
        uv, boot = base.find_uv(), self.work / f"uvx-{version}"
        made = self.run_here([uv, "venv", "--no-project", "--python", sys.executable, boot])
        self.assertEqual(made.returncode, 0, made.stderr)
        install = [uv, "pip", "install", "--python", base.interpreter(boot), "--find-links", self.wheels,
                   f"{base.SERVER}=={version}"]
        made = self.run_here([*install, "--offline"])
        if made.returncode != 0:
            made = self.run_here(install)
        self.assertEqual(made.returncode, 0, made.stderr)
        return boot
