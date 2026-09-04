"""A warm build must produce exactly what a cold build produces.

This is the regression net for turning the daemon into a worker pool. It is deliberately
written and landed BEFORE that refactor: a harness that only exists afterwards proves
nothing about the change it was meant to guard.

Three paths must agree, byte for byte:

* cold — the tool runs in the invoking process
* warm sequential — the tool runs in a daemon that already imported OCP
* warm parallel — several builds through one daemon at once

What is compared: every file the build writes under ``__cadgen__`` by sha256, the exit
code, and stdout/stderr with the tmp path masked. Plus ``--help`` for every daemon-served
command, which is the input contract made visible — dispatch hands off before argparse
runs, so warm ``--help`` genuinely round-trips through the daemon.

Fixtures are written here rather than copied from ``models/``: the repo's generators
import sibling modules (``simple_model_library``), so a single copied file does not build.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
CADGEN_SRC = REPO_ROOT / "packages" / "cadgen" / "src"

PART = """from build123d import Box, BuildPart, Cylinder, Locations, Mode

from cadgen import step
@step
def model():
    with BuildPart() as part:
        Box(30, 20, 10)
        with Locations((0, 0, 0)):
            Cylinder(4, 40, mode=Mode.SUBTRACT)
    return part.part


if __name__ == "__main__":
    model()
"""

ASSEMBLY = """from build123d import Box, BuildPart, Location, Pos

from cadgen import step
@step
def model():
    with BuildPart() as base:
        Box(40, 40, 5)
    with BuildPart() as post:
        Box(8, 8, 20)
    post.part.locate(Location(Pos(0, 0, 12.5)))
    return base.part + post.part


if __name__ == "__main__":
    model()
"""

DRAWING = """from cadgen import build123d as bd
from cadgen import dxf


@dxf
def drawing():
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
        bd.Circle(8, mode=bd.Mode.SUBTRACT)
    return cut.sketch


if __name__ == "__main__":
    drawing()
"""


def _env(**extra) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(CADGEN_SRC), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    )
    env.pop("CADGEN_DAEMON", None)
    env.update({k: v for k, v in extra.items() if v is not None})
    return env


def _run(argv: list[str], cwd: pathlib.Path, **env_extra) -> tuple[int, str]:
    # Library-first: a model script is its own entrypoint (python <model>.py);
    # cadgen.cli commands still route the non-generation tools.
    launcher = [] if argv and argv[0].endswith(".py") else ["-m", "cadgen.cli"]
    proc = subprocess.run(
        [sys.executable, *launcher, *argv],
        cwd=str(cwd), env=_env(**env_extra), capture_output=True, text=True, timeout=600,
    )
    # The tmp root differs per run and is not part of the contract; everything else is.
    output = re.sub(re.escape(str(cwd)), "<CWD>", proc.stdout + proc.stderr)
    output = re.sub(r"/private/var/folders/\S+", "<TMP>", output)
    output = re.sub(r"/(?:var|tmp)/\S*tmp\S+", "<TMP>", output)
    # The build tree's JSONL transitions carry wall-clock elapsed times and, warm, arrive
    # relayed through the daemon; they narrate the build and are not its output.
    output = "".join(line for line in output.splitlines(keepends=True) if not line.startswith('{"model":'))
    return proc.returncode, output


# Fields that record WHEN a build ran rather than WHAT it produced. Two cold builds a
# second apart differ in these too, so comparing them would test the clock. Lives in the
# source sidecar (source.json) now — the descriptor is a pure function of the STEP bytes
# and carries no timestamp at all.
_VOLATILE_JSON_FIELDS = {"generatedAt"}


def _canonical(value):
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items()) if k not in _VOLATILE_JSON_FIELDS}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def _digest(path: pathlib.Path) -> str:
    """sha256 of a built file, with build-time stamps masked out of JSON."""
    raw = path.read_bytes()
    if path.suffix == ".json":
        try:
            return hashlib.sha256(
                json.dumps(_canonical(json.loads(raw)), sort_keys=True).encode()
            ).hexdigest()
        except ValueError:
            pass  # not JSON after all; fall through to the raw bytes
    return hashlib.sha256(raw).hexdigest()


def _manifest(root: pathlib.Path) -> dict[str, str]:
    """Digest of every built file for the models in ``root``: the store
    packages their artifacts resolve to (content-keyed), plus the model-folder
    outputs themselves (.step documents and source sidecars).

    Lock and progress files are transient scaffolding, not output.
    """
    from cadgen.catalog import result_view_dir

    out: dict[str, str] = {}
    for artifact in sorted(root.rglob("*")):
        if not artifact.is_file():
            continue
        rel = artifact.relative_to(root).as_posix()
        if artifact.suffix in {".step", ".stp", ".dxf"} or rel.endswith(".step.json"):
            out[rel] = _digest(artifact)
        if artifact.suffix in {".step", ".stp"}:
            package = result_view_dir(artifact)
            if package.is_dir():
                for entry in sorted(package.rglob("*")):
                    if entry.is_file():
                        out[f"<store>/{entry.relative_to(package.parent).as_posix()}"] = _digest(entry)
    return out


sys.path.insert(0, str(CADGEN_SRC))
from cadgen.daemon import client as daemon_client  # noqa: E402


def _daemon_available() -> bool:
    """Whether a daemon can be reached at all on this platform."""
    return daemon_client.daemon_supported()


class _Daemon:
    """A real daemon on a private address, so tests never touch a developer's."""

    def __init__(self, tmp: pathlib.Path):
        # A pipe name is not a filesystem path, so a temp FILE is not a usable address on
        # Windows. Handing one over does not fail loudly either -- the daemon simply never
        # binds, every "warm" run is quietly cold, and the comparison stops meaning
        # anything. served_a_job() is what catches that, and it caught exactly this.
        if os.name == "nt":
            self.address = rf"\\.\pipe\cadgen-warm-eq-{tmp.name}"
        else:
            self.address = str(tmp / "d.sock")
        # Ask the client where it will put the log rather than guessing: on POSIX that is
        # a sibling of the socket, on Windows it cannot be.
        self.log = daemon_client.log_path(self.address)

    def env(self) -> dict:
        return {"CADGEN_DAEMON": "1", "CADGEN_DAEMON_SOCKET": str(self.address)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        subprocess.run(
            [sys.executable, "-m", "cadgen.daemon", "--stop"],
            env=_env(**self.env()), capture_output=True, timeout=60,
        )
        return False

    def served_a_job(self) -> bool:
        """Proof the warm run was actually warm, so a silent cold fallback cannot pass.

        Looks for a completed job (`gen [...] -> exit 0`), not just the daemon's startup
        line: a daemon can be running while the client still fell back to cold.
        """
        return self.log.is_file() and "-> exit" in self.log.read_text(encoding="utf-8", errors="replace")


# The whole harness compares a WARM run against a cold one, so it needs a daemon to
# exist. Every platform we ship on has a transport now -- AF_UNIX on POSIX, AF_PIPE on
# Windows -- so this normally runs everywhere. It is asked of cadgen rather than of
# os.name so that a platform which somehow has neither skips instead of failing, and so
# that a silent cold fallback still shows up as a failure rather than a pass.
_DAEMON_AVAILABLE = _daemon_available()


@unittest.skipUnless(_DAEMON_AVAILABLE, "no daemon transport on this platform")
class WarmOutputEquivalence(unittest.TestCase):
    maxDiff = None

    def _tree(self, name: str, source: str) -> pathlib.Path:
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="tmp-warm-eq-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (tmp / name).write_text(source, encoding="utf-8")
        return tmp

    def _cold(self, name: str, source: str, argv: list[str]):
        tree = self._tree(name, source)
        code, output = _run(argv, tree, CADGEN_DAEMON="0")
        self.assertEqual(code, 0, output)
        return _manifest(tree), output

    def test_a_part_builds_identically_warm(self):
        argv = ["widget.py"]
        cold, cold_out = self._cold("widget.py", PART, argv)
        self.assertTrue(cold, "the cold build produced nothing to compare")

        tree = self._tree("widget.py", PART)
        with _Daemon(tree) as daemon:
            code, warm_out = _run(argv, tree, **daemon.env())
            self.assertEqual(code, 0, warm_out)
            self.assertTrue(daemon.served_a_job(), "the warm run fell back to cold")
            self.assertEqual(_manifest(tree), cold)
        self.assertEqual(warm_out, cold_out)

    def test_an_assembly_builds_identically_warm(self):
        argv = ["rig.py"]
        cold, _ = self._cold("rig.py", ASSEMBLY, argv)
        tree = self._tree("rig.py", ASSEMBLY)
        with _Daemon(tree) as daemon:
            code, out = _run(argv, tree, **daemon.env())
            self.assertEqual(code, 0, out)
            self.assertEqual(_manifest(tree), cold)

    def test_four_parallel_builds_through_one_daemon_all_match_cold(self):
        """The case the pool exists for. Today this serialises; it must still be correct."""
        argv = ["widget.py"]
        cold, _ = self._cold("widget.py", PART, argv)

        trees = [self._tree("widget.py", PART) for _ in range(4)]
        shared = pathlib.Path(tempfile.mkdtemp(prefix="tmp-warm-eq-sock-")).resolve()
        self.addCleanup(shutil.rmtree, shared, ignore_errors=True)
        with _Daemon(shared) as daemon:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda t: _run(argv, t, **daemon.env()), trees))
            for index, (code, out) in enumerate(results):
                with self.subTest(build=index):
                    self.assertEqual(code, 0, out)
            for index, tree in enumerate(trees):
                with self.subTest(build=index):
                    self.assertEqual(_manifest(tree), cold)

    def test_a_drawing_package_is_byte_identical_warm(self):
        """DXF is the format that USED to have a determinism hazard: ezdxf's emitted
        order followed the hash seed, and a warm worker's environment differs from a
        cold run's. The emitter engineers that away, so warm and cold must now agree
        on the bytes with no seed pinning anywhere."""
        argv = ["plate.py"]
        cold, _ = self._cold("plate.py", DRAWING, argv)
        self.assertTrue(cold, "the cold DXF build produced nothing to compare")
        tree = self._tree("plate.py", DRAWING)
        code, out = _run(argv, tree, CADGEN_DAEMON="1")
        self.assertEqual(code, 0, out)
        self.assertEqual(_manifest(tree), cold)

    def test_a_failing_build_fails_the_same_way_warm(self):
        """Exit code and message are contract too, not just successful output."""
        broken = (
            "from cadgen import step\n"
            "@step\n"
            "def model():\n"
            "    raise ValueError('bad radius')\n"
            "if __name__ == '__main__':\n"
            "    model()\n"
        )
        tree = self._tree("broken.py", broken)
        cold_code, cold_out = _run(["broken.py"], tree, CADGEN_DAEMON="0")
        self.assertNotEqual(cold_code, 0)

        tree2 = self._tree("broken.py", broken)
        with _Daemon(tree2) as daemon:
            warm_code, warm_out = _run(["broken.py"], tree2, **daemon.env())
        self.assertEqual(warm_code, cold_code)
        # Deliberately not asserting the message TEXT: cadgen masks a raising generator
        # with "model() must return one value" rather than surfacing the original
        # error (a pre-existing quirk, not this refactor's business). What matters here is
        # that whatever cold says, warm says exactly the same.
        self.assertEqual(warm_out, cold_out)
        self.assertIn("FAILED", warm_out)


@unittest.skipUnless(_DAEMON_AVAILABLE, "no daemon transport on this platform")
class InputSurfaceEquivalence(unittest.TestCase):
    """`--help` is the input contract made visible.

    Dispatch hands off to the daemon before argparse runs, so a warm `--help` exercises
    the handoff path rather than short-circuiting around it.
    """

    maxDiff = None

    def test_help_is_identical_cold_and_warm(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="tmp-warm-eq-help-")).resolve()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        from cadgen.cli import _DAEMON_TOOLS

        with _Daemon(tmp) as daemon:
            for command in sorted(_DAEMON_TOOLS):
                argv = [*command.split(), "--help"]
                with self.subTest(command=command):
                    cold_code, cold_help = _run(argv, tmp)
                    warm_code, warm_help = _run(argv, tmp, **daemon.env())
                    self.assertEqual(cold_code, warm_code)
                    self.assertEqual(warm_help, cold_help)


if __name__ == "__main__":
    unittest.main()
