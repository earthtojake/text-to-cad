"""On Windows, what the ``cad`` command writes to a pipe or a file is UTF-8, and so is what the program ``cad run`` runs
writes (``cad._internal.streams``): whatever reads a command's output there -- an agent, a log, Git Bash -- reads
UTF-8, and a profile folder with an accent arrived broken in the code page Python writes a pipe in. A console, and
every stream on other systems, is left as it is. The commands run here as an agent runs them, their output in a pipe,
from a folder whose name has an accent and a character no Western code page has; the Windows run is what proves it."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()

from cad._internal import streams  # noqa: E402

# A folder name with a Latin-1 accent and a Greek letter, which cp1252 cannot write at all.
NAME = "Zoë Ω"
# What the program says: the name, and the characters cad's own lines use.
SAID = f"said: {NAME} · × —"


class Stream(io.BytesIO):
    """A stream's bytes, a console or not."""

    def __init__(self, console: bool) -> None:
        super().__init__()
        self.console = console

    def isatty(self) -> bool:
        return self.console


class RuleTest(unittest.TestCase):
    def test_a_stream_that_is_no_console_is_switched_on_windows_alone(self) -> None:
        self.assertTrue(streams.switches(Stream(console=False), "nt"))
        self.assertFalse(streams.switches(Stream(console=True), "nt"))
        for console in (False, True):
            self.assertFalse(streams.switches(Stream(console=console), "posix"))
        self.assertFalse(streams.switches(None, "nt"), "no stream at all (pythonw): nothing to switch")

    def test_only_the_encoding_of_a_switched_stream_changes(self) -> None:
        def wrapped(console: bool, errors: str) -> io.TextIOWrapper:
            return io.TextIOWrapper(Stream(console), encoding="cp1252", errors=errors)

        for system, piped in (("nt", "utf-8"), ("posix", "cp1252")):
            with self.subTest(system=system):
                out, err = wrapped(False, "backslashreplace"), wrapped(True, "strict")
                with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
                    streams.utf8(system)
                self.assertEqual((out.encoding, out.errors), (piped, "backslashreplace"), "its own handler kept")
                self.assertEqual((err.encoding, err.errors), ("cp1252", "strict"), "a console: as it was")
                out.write(NAME)
                out.flush()
                self.assertEqual(out.buffer.getvalue(), NAME.encode(piped, "backslashreplace"))


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(os.path.realpath(tempfile.mkdtemp(prefix="cad-encoding-")))
        self.addCleanup(shutil.rmtree, root, True)
        self.folder = root / NAME
        self.folder.mkdir()
        # The environment as an agent's is, but for what would choose the encoding instead of cad.
        keep = {key: value for key, value in os.environ.items()
                if key not in ("PYTHONIOENCODING", "PYTHONUTF8", "PYTHONLEGACYWINDOWSSTDIO", "CAD_INSTALLATION_VERSION")}
        self.env = {**keep, "PYTHONPATH": SRC, "CAD_STATE_DIR": str(self.folder / "state"),
                    "CAD_CACHE_DIR": str(self.folder / "cache"), "CAD_ENGINE_DIR": str(self.folder / "engine"),
                    "CAD_LAUNCHER_DIR": str(self.folder / "bin"), "CAD_UPDATE_CHECK": "0", "DO_NOT_TRACK": "1"}

    def cad(self, *argv: str, cwd: Path | None = None) -> tuple[int, str, str]:
        """``cad ARGV`` with both outputs in a pipe: its exit status, and the outputs read strictly as UTF-8."""
        done = subprocess.run([sys.executable, "-m", "cad_server.cli", *argv], cwd=cwd or self.folder, env=self.env,
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
        return done.returncode, done.stdout.decode("utf-8"), done.stderr.decode("utf-8")

    def test_a_command_s_output_in_a_pipe_is_utf_8_with_the_folder_s_name_intact(self) -> None:
        # The report alone: no server, nothing written. Its status is the report's, not this test's.
        _, out, err = self.cad("doctor", "--check")
        self.assertIn(NAME, unicodedata.normalize("NFC", out), f"the cache folder, as the report names it\n{out}{err}")

    def test_what_cad_run_s_program_writes_to_a_pipe_is_utf_8(self) -> None:
        project = self.folder / "project"
        project.mkdir()
        (project / "say.py").write_text(f"import sys\nprint({SAID!r})\nprint({SAID!r}, file=sys.stderr)\n",
                                        encoding="utf-8")
        self.addCleanup(subprocess.run, [sys.executable, "-m", "cad_server.engine", "stop"], env=self.env,
                        capture_output=True, timeout=120)
        engine_daemon.start(self.env)  # which makes the program's environment
        code, out, err = self.cad("run", "say.py", cwd=project)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out.splitlines(), [SAID])
        self.assertEqual(err.splitlines()[-1], SAID)


if __name__ == "__main__":
    unittest.main()
