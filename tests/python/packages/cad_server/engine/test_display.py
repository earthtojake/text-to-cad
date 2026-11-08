"""The engine's X display (``cad_server/engine/display.py``): what a process that draws is started with on
Linux -- the daemon's own ``DISPLAY``, else an Xvfb the daemon starts once and stops with it, else nothing --
and nothing on macOS or Windows. Xvfb here is a stand-in that says a display and waits; the real one draws
in ``test_render.py``'s ``EngineDisplayTest``, on Linux."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

from cad_server.engine import display
from tests.python.support.paths import add_sources

SRC = add_sources()

# Says display 7 on the descriptor -displayfd names, notes its pid and the times it started, and waits.
FAKE = """\
#!/bin/sh
echo "$*" > "${FAKE_XVFB_LOG%/*}/argv"
while [ $# -gt 0 ]; do case "$1" in -displayfd) fd=$2; shift;; esac; shift; done
echo $$ >> "$FAKE_XVFB_LOG"
eval "echo 7 >&$fd"
exec /bin/sleep 600
"""
# Exits saying why, with no display.
BROKEN = """\
#!/bin/sh
echo "Fatal server error: no screens found" >&2
exit 1
"""


@unittest.skipIf(os.name == "nt", "Windows draws on a window of its own, and has no /bin/sh")
class EngineDisplayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-display-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.log = self.folder / "started"
        self.addCleanup(display.stop)
        environment = {key: value for key, value in os.environ.items() if key != "DISPLAY"}
        # The stand-in alone on PATH: never a real Xvfb of the machine's.
        environment.update(PATH=str(self.folder), FAKE_XVFB_LOG=str(self.log))
        patched = mock.patch.dict(os.environ, environment, clear=True)
        patched.start()
        self.addCleanup(patched.stop)
        linux = mock.patch.object(display, "_linux", return_value=True)
        linux.start()
        self.addCleanup(linux.stop)

    def xvfb(self, script: str) -> None:
        path = self.folder / "Xvfb"
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)

    def started(self) -> list[int]:
        return [int(line) for line in self.log.read_text(encoding="utf-8").split()] if self.log.exists() else []

    def gone(self, pid: int) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and _alive(pid):
            time.sleep(0.05)
        self.assertFalse(_alive(pid), f"Xvfb {pid} outlived the engine")

    def test_macos_and_windows_are_given_nothing(self) -> None:
        self.xvfb(FAKE)
        with mock.patch.object(display, "_linux", return_value=False):
            self.assertEqual(display.environment(), {})
        self.assertEqual(self.started(), [])

    def test_a_daemon_with_a_display_gives_its_own(self) -> None:
        self.xvfb(FAKE)
        with mock.patch.dict(os.environ, {"DISPLAY": ":3"}):
            self.assertEqual(display.environment(), {"CAD_ENGINE_DISPLAY": ":3"})
            with mock.patch.dict(os.environ, {"XAUTHORITY": "/run/user/1000/gdm/Xauthority"}):  # and what admits it
                self.assertEqual(display.environment(), {"CAD_ENGINE_DISPLAY": ":3",
                                                         "CAD_ENGINE_XAUTHORITY": "/run/user/1000/gdm/Xauthority"})
        self.assertEqual(self.started(), [])

    def test_a_daemon_with_none_starts_one_xvfb_and_stops_it(self) -> None:
        import stat
        import struct

        self.xvfb(FAKE)
        given = display.environment()
        self.assertEqual(given["CAD_ENGINE_DISPLAY"], ":7")
        self.assertEqual(display.environment(), given)
        [pid] = self.started()  # once, for every process after
        # Its cookie, for any display here (FamilyWild), which only this user can read: no other user draws on it.
        cookie = Path(given["CAD_ENGINE_XAUTHORITY"])
        self.assertEqual(stat.S_IMODE(cookie.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(cookie.parent.stat().st_mode), 0o700)
        data = cookie.read_bytes()
        self.assertEqual(struct.unpack(">HHHH", data[:8]), (0xFFFF, 0, 0, 18))
        self.assertEqual((data[8:26], struct.unpack(">H", data[26:28])[0], len(data)), (b"MIT-MAGIC-COOKIE-1", 16, 44))
        self.assertIn(f"-auth {cookie}", (self.folder / "argv").read_text(encoding="utf-8"))
        display.stop()
        self.gone(pid)
        self.assertFalse(cookie.parent.exists(), "its cookie goes with it")

    def test_its_xvfb_goes_with_a_daemon_that_is_killed(self) -> None:
        self.xvfb(FAKE)
        code = textwrap.dedent("""
            import sys
            from unittest import mock
            from cad_server.engine import display
            with mock.patch.object(display, "_linux", return_value=True):
                print(display.name(), flush=True)
            sys.stdin.read()
        """)
        daemon = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True, env={**os.environ, "PYTHONPATH": str(SRC)})
        self.addCleanup(daemon.wait)
        self.addCleanup(daemon.kill)
        self.assertEqual(daemon.stdout.readline().strip(), ":7")
        [pid] = self.started()
        daemon.kill()
        self.gone(pid)

    def test_none_on_path_starts_nothing_and_is_looked_for_again(self) -> None:
        self.assertEqual(display.environment(), {})
        self.xvfb(FAKE)  # installed meanwhile: the next process finds it
        self.assertEqual(display.environment()["CAD_ENGINE_DISPLAY"], ":7")

    def test_one_that_does_not_start_is_said_once_and_not_started_again(self) -> None:
        self.xvfb(BROKEN)
        with self.assertLogs("cad_server.engine.display", "WARNING") as said:
            self.assertEqual(display.environment(), {})
        self.assertIn("no screens found", "".join(said.output))
        self.xvfb(FAKE)
        self.assertEqual(display.environment(), {})
        self.assertEqual(self.started(), [])


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A child of the shell that exited is a zombie until reaped: gone all the same.
    try:
        state = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    except OSError:
        return True
    return bool(state) and not state.startswith("Z")


if __name__ == "__main__":
    unittest.main()
