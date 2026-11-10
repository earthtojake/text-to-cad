"""cadgen's stills drawn by OCCT through the engine (`engine/render`): the render process the daemon
keeps warm per served document, a still drawn in this process with ``daemon=False``, and on Linux an
engine that draws on a display of its own where its request names none. The stills themselves are
`test_render.py`'s, which says where a test that draws can make its OpenGL context."""

from __future__ import annotations

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

import numpy as np

from cad.engine.render import context
from tests.python.support import opengl
from tests.python.support.paths import add_sources
from tests.python.support.render_stills import PLATFORM, X_VARIABLES, drawn, gl, mismatch

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them


PAIR = """
import build123d as bd
from cad.engine import xbf

SIZE = {size}


@xbf("XBF/pair.xbf")
def pair():
    block = bd.Box(SIZE, 4, 2)
    block.label = "block"
    peg = bd.Pos(20, 0, 0) * bd.Cylinder(2, 5)
    peg.label = "peg"
    return bd.Compound(children=[block, peg], label="pair")

if __name__ == "__main__":
    pair()
"""


class DaemonRenderTest(unittest.TestCase):
    """`cad <type> snapshot` drawn by OCCT through the daemon: a render process per served
    document, warm from its second picture, sent its file's new version by the next picture with
    only the parts it lacks, gone with the daemon; and in this process with ``daemon=False`` from Python. Nothing is written but
    the pictures, and the daemon's door, lock and clients' pipes."""

    def setUp(self) -> None:
        gl()
        self.folder = Path(tempfile.mkdtemp(prefix="engine-render-daemon-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)).resolve()
        self.env = {**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(self.state),
                    "CAD_ENGINE_MESH": "inline"}
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.state, ignore_errors=True)
        self.addCleanup(self.cli, "stop")

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "cad_server.engine", *args], cwd=self.folder, env=self.env,
                              capture_output=True, text=True, timeout=300)

    def snapshot(self, out: str, *flags: str) -> dict:
        done = self.cli("snapshot", "XBF/pair.xbf", out, "--width", "200", "--height", "150", "--json", *flags)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def build(self, size: int, *, daemon: bool = True) -> None:
        (self.folder / "pair.py").write_text(textwrap.dedent(PAIR.format(size=size)), encoding="utf-8")
        # ``python pair.py`` asks the daemon; ``Model.build(daemon=False)`` builds in its own process.
        argv = ["pair.py"] if daemon else ["-B", "-c", "import pair; pair.pair.build(daemon=False)"]
        done = subprocess.run([sys.executable, *argv], cwd=self.folder, env=self.env, capture_output=True, text=True,
                              timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr)

    def renders(self) -> list[dict]:
        return json.loads(self.cli("status", "--json").stdout)["renders"]

    def test_a_served_document_is_drawn_warm_and_follows_its_builds(self) -> None:
        self.build(10)
        first = self.snapshot("first.png")
        self.assertEqual(first["renderer"], "occt")
        pid = first["process"]["pid"]
        warm = self.snapshot("warm.png")
        self.assertEqual(warm["process"]["pid"], pid)
        self.assertFalse({"meshMs", "holdMs", "sceneMs"} & set(warm["timings"]), warm["timings"])
        self.build(14)  # the file is rewritten: the next picture reads it, and makes the new part alone
        version = f"{(self.folder / 'XBF/pair.xbf').stat().st_mtime_ns}-{(self.folder / 'XBF/pair.xbf').stat().st_size}"
        edited = self.snapshot("edited.png")
        self.assertEqual(edited["process"]["pid"], pid, "the same process, sent the file's new version")
        [render] = self.renders()
        self.assertEqual((render["version"], render["held"]["made"], render["held"]["kept"]), (version, 1, 1))
        self.assertNotEqual((self.folder / "edited.png").read_bytes(), (self.folder / "first.png").read_bytes())
        # A model, by its id, is drawn from the document its worker holds, in that worker.
        from cad.engine.ids import model_id

        done = self.cli("snapshot", model_id(self.folder / "pair.py", "pair"), "model.png", "--width", "200", "--height",
                        "150", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        model = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual((model["renderer"], "process" in model), ("occt", False))
        # The daemon's socket (on Windows the port file standing in for it) and its lock, nothing else.
        self.assertEqual({path.suffix or path.name for path in self.state.iterdir()},
                         {".port", ".lock"} if os.name == "nt" else {".door", ".lock", "clients"})
        self.assertEqual(sorted(path.relative_to(self.folder).as_posix() for path in self.folder.rglob("*") if path.is_file()),
                         ["XBF/pair.xbf", "edited.png", "first.png", "model.png", "pair.py", "warm.png"])
        self.cli("stop")
        if os.name != "nt":  # os.kill(pid, 0) asks after a process on POSIX alone
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and _alive(pid):
                time.sleep(0.1)
            self.assertFalse(_alive(pid), "gone with the daemon")

    def test_daemon_false_draws_in_this_process(self) -> None:
        # A seam of the Python function's alone: no command draws outside the engine.
        self.build(10, daemon=False)
        code = ("import json; from cad.engine import api; print(json.dumps(api.snapshot('XBF/pair.xbf', "
                "'cold.png', width=200, height=150, display='exploded=0.5', daemon=False).report))")
        done = subprocess.run([sys.executable, "-c", code], cwd=self.folder, env=self.env, capture_output=True,
                              text=True, timeout=300)
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual((report["renderer"], report["exploded"]), ("occt", 0.5))
        self.assertNotIn("process", report)
        self.assertEqual([path for path in self.state.iterdir() if path.suffix == ".door"], [], "no daemon started")


@unittest.skipUnless(PLATFORM == "linux", "Linux draws on an X display; macOS and Windows on a hidden window")
class EngineDisplayTest(unittest.TestCase):
    """A Linux engine draws a model's still and a file's where the request names no ``DISPLAY``
    (``cad_server.engine.display``): on the daemon's own display where it has one, and on an Xvfb it
    starts itself where it has none -- no X server of the test's, no ``xvfb-run``: the CI job installs
    Xvfb and runs its suite under ``xvfb-run``, and this test takes that display away from the engine
    and every request it sends. The pictures are the ones drawn on the test's own display. The wheels'
    OpenGL is GLX alone (``render/context.py``), so this is the off-screen route there is."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-display-")).resolve()
        self.state = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.state, ignore_errors=True)
        self.bare = {**{key: value for key, value in os.environ.items() if key not in X_VARIABLES},
                     "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(self.state), "CAD_ENGINE_MESH": "inline"}
        self.addCleanup(self.run_in, self.bare, "-m", "cad_server.engine", "stop")
        (self.folder / "pair.py").write_text(textwrap.dedent(PAIR.format(size=10)), encoding="utf-8")

    def run_in(self, env: dict[str, str], *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, *argv], cwd=self.folder, env=env, capture_output=True, text=True,
                              timeout=300)

    def pictures(self, env: dict[str, str]) -> dict[str, np.ndarray]:
        """The model and its file drawn through the engine, asked with ``env``: each picture's pixels."""
        from cad.engine.ids import model_id

        found = {}
        for name, source in (("model", model_id(self.folder / "pair.py", "pair")), ("file", "XBF/pair.xbf")):
            done = self.run_in(env, "-m", "cad_server.engine", "snapshot", source, f"{name}.png", "--width", "200",
                               "--height", "150", "--json")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1])["renderer"], "occt")
            found[name] = drawn((self.folder / f"{name}.png").read_bytes(), (200, 150))
        return found

    def drawn_here(self) -> np.ndarray | None:
        """The file drawn in a process of its own on the test's display (``daemon=False``), where it has one."""
        if not os.environ.get("DISPLAY") or context.available() is not None:
            return None
        code = ("from cad.engine import api; api.snapshot('XBF/pair.xbf', 'here.png', width=200, height=150, "
                "daemon=False)")
        done = self.run_in({**os.environ, "PYTHONPATH": str(SRC), "CAD_ENGINE_DIR": str(self.state)}, "-c", code)
        self.assertEqual(done.returncode, 0, done.stderr)
        return drawn((self.folder / "here.png").read_bytes(), (200, 150))

    def test_an_engine_with_no_display_draws_on_an_xvfb_of_its_own(self) -> None:
        if shutil.which("Xvfb") is None:
            opengl.require("Xvfb is not on PATH (apt-get install xvfb libgl1-mesa-dri)", "no Xvfb for the engine")
        done = self.run_in(self.bare, "pair.py")  # the daemon starts here, with no display
        self.assertEqual(done.returncode, 0, done.stderr)
        found = self.pictures(self.bare)
        here = self.drawn_here()
        for name, picture in found.items():
            if here is not None:
                self.assertLessEqual(mismatch(picture, here), 0.015, name)
        # The Xvfb is the daemon's: gone with it.
        xvfb = _xvfb_pids(self.state)
        self.assertTrue(xvfb, "the engine started no Xvfb")
        self.run_in(self.bare, "-m", "cad_server.engine", "stop")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and any(_alive(pid) for pid in xvfb):
            time.sleep(0.1)
        self.assertFalse([pid for pid in xvfb if _alive(pid)], "the engine's Xvfb outlived it")

    def test_a_request_with_no_display_draws_on_the_engine_s(self) -> None:
        # The field's failure: a daemon started where there is a display, asked from a shell with none.
        if not os.environ.get("DISPLAY"):
            opengl.require("no DISPLAY to start the engine on", "no display")
        gl()
        done = self.run_in({**self.bare, "DISPLAY": os.environ["DISPLAY"],
                            **({"XAUTHORITY": os.environ["XAUTHORITY"]} if "XAUTHORITY" in os.environ else {})},
                           "pair.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        found = self.pictures(self.bare)
        here = self.drawn_here()
        for name, picture in found.items():
            self.assertLessEqual(mismatch(picture, here), 0.015, name)
        self.assertEqual(_xvfb_pids(self.state), [], "the engine had a display: it starts no Xvfb")


def _xvfb_pids(engine: Path) -> list[int]:
    """The Xvfb processes the engine in the folder ``engine`` started (``display.py``): each under the shell
    that stops it with its daemon, whose environment names that folder; by /proc."""
    def read(pid: str, name: str) -> list[bytes]:
        try:
            return Path(f"/proc/{pid}/{name}").read_bytes().split(b"\0")
        except OSError:
            return [b""]

    def parent(pid: str) -> str:
        try:
            return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rpartition(")")[2].split()[1]
        except (OSError, IndexError):
            return "0"

    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or Path(read(entry.name, "cmdline")[0].decode(errors="replace")).name != "Xvfb":
            continue
        shell = parent(entry.name)
        if any(b"read -r _ <&3" in part for part in read(shell, "cmdline")) and \
                f"CAD_ENGINE_DIR={engine}".encode() in read(parent(shell), "environ"):
            found.append(int(entry.name))
    return found


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
