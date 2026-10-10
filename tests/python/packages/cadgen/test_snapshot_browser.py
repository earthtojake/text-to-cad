"""The snapshot browser installs itself: snapshot_core.launch_with_browser.

Playwright is a dependency of every cadgen install, but its browser is a download of its own.
The first snapshot fetches it rather than failing with "run playwright install"; a Linux host
missing the browser's libraries gets them (or the exact command). A snapshot started while
another cadgen command installs it waits for that install (a launch of a half-unpacked browser
fails with "spawn ENOEXEC", which is how new installs' first snapshots failed when a skill
rendered several views at once). Stubbed here: the real download is ~100 MB, and the
installed-wheel test is where a real browser runs.
"""

from __future__ import annotations

import asyncio
import io
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import snapshot_core  # noqa: E402

MISSING = "BrowserType.launch: Executable doesn't exist at /cache/chromium_headless_shell-1243/chrome-headless-shell"
LIBRARIES = "BrowserType.launch: Host system is missing dependencies to run browsers."
HALF_UNPACKED = "BrowserType.launch: spawn ENOEXEC"
SLOW_FIRST_START = "BrowserType.launch: Timeout 15000ms exceeded."

# A cadgen command installing the browser: holds the install lock until told to finish, then
# leaves the browser it installed (a file) behind.
HOLDER = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from cadgen.snapshot_core import browser_install_lock
with browser_install_lock():
    print("held", flush=True)
    sys.stdin.readline()
    Path(sys.argv[2]).write_text("installed")
"""
# Exits 3 when another process holds the install lock, rather than waiting for it.
PROBE = """
import sys
sys.path.insert(0, sys.argv[1])
from cadgen import snapshot_core
snapshot_core._say = lambda line: sys.exit(3)
with snapshot_core.browser_install_lock():
    pass
"""


def launcher(*failures: str):
    """A launch that raises each failure in turn, then returns a browser."""
    remaining = list(failures)

    async def launch():
        if remaining:
            raise RuntimeError(remaining.pop(0))
        return "browser"

    return launch


class SnapshotBrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        state = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp / "state")})
        state.start()
        self.addCleanup(state.stop)

    def run_launch(self, *failures: str) -> tuple[object, list[str]]:
        fixed: list[str] = []
        browser = asyncio.run(snapshot_core.launch_with_browser(launcher(*failures), fixed.append))
        return browser, fixed

    def test_a_missing_browser_is_installed_then_launched(self) -> None:
        self.assertEqual(self.run_launch(MISSING), ("browser", ["browser"]))

    def test_a_host_missing_libraries_gets_them_after_the_browser(self) -> None:
        self.assertEqual(self.run_launch(MISSING, LIBRARIES), ("browser", ["browser", "libraries"]))

    def test_any_other_failure_has_the_install_checked_and_is_tried_once_more(self) -> None:
        # A browser another program is still unpacking, or one a killed install left half done:
        # `playwright install` waits for the one or finishes the other.
        self.assertEqual(self.run_launch(HALF_UNPACKED), ("browser", ["start"]))
        # A first launch held past the startup timeout (a virus scan of the new executable).
        self.assertEqual(self.run_launch(MISSING, SLOW_FIRST_START), ("browser", ["browser", "start"]))

    def test_a_failure_that_outlasts_its_fix_is_raised(self) -> None:
        # Still failing after its fix: the launch's own error is the one to read, not a loop.
        with self.assertRaisesRegex(RuntimeError, "Executable doesn't exist"):
            self.run_launch(MISSING, MISSING)
        with self.assertRaisesRegex(RuntimeError, "target closed"):
            self.run_launch("target closed", "target closed")

    def test_a_launch_waits_for_the_install_another_command_is_running(self) -> None:
        installed = self.tmp / "browser"
        holder = subprocess.Popen(
            [sys.executable, "-c", HOLDER, str(Path(snapshot_core.__file__).parents[1]), str(installed)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=os.environ.copy())
        self.addCleanup(lambda: (holder.kill(), holder.wait(), holder.stdin.close(), holder.stdout.close()))
        self.assertEqual(holder.stdout.readline().strip(), "held")

        said: list[str] = []
        waiting = threading.Event()

        def say(line: str) -> None:
            said.append(line)
            if "waiting for the snapshot browser" in line:
                waiting.set()

        async def launch():
            # Before the install finished, this was a half-unpacked browser.
            if not installed.exists():
                raise RuntimeError(HALF_UNPACKED)
            return "browser"

        fixed: list[str] = []
        outcome: list[object] = []

        def snapshot() -> None:
            try:
                outcome.append(asyncio.run(snapshot_core.launch_with_browser(launch, fixed.append)))
            except BaseException as error:  # noqa: BLE001 - reported below
                outcome.append(error)

        with mock.patch.object(snapshot_core, "_say", say):
            thread = threading.Thread(target=snapshot)
            thread.start()
            self.assertTrue(waiting.wait(60), "the launch did not wait for the install")
            holder.stdin.write("done\n")
            holder.stdin.flush()
            thread.join(60)
        self.assertEqual(holder.wait(60), 0)
        self.assertEqual(outcome, ["browser"])
        self.assertEqual(fixed, [], "it launched before the install finished")

    def test_the_install_reports_through_any_stderr_and_names_why_it_failed(self) -> None:
        # A model script's snapshot in a build worker has a stderr with no file descriptor.
        captured = io.StringIO()
        script = ("import sys; print('Downloading Chrome Headless Shell'); "
                  "print('Error: connect ECONNREFUSED 127.0.0.1:9', file=sys.stderr); "
                  "print('    at TCPConnectWrap.afterConnect'); sys.exit(1)")
        with mock.patch.object(sys, "stderr", captured):
            self.assertEqual(snapshot_core._run_to_stderr([sys.executable, "-c", script]),
                             (1, "Error: connect ECONNREFUSED 127.0.0.1:9"))
        self.assertIn("Downloading Chrome Headless Shell", captured.getvalue())

        def install(command: list[str]) -> tuple[int, str]:
            # Under the lock: another command finds it held (its `waiting` is called, and says so).
            probe = subprocess.run([sys.executable, "-c", PROBE, str(Path(snapshot_core.__file__).parents[1])],
                                   env=os.environ.copy(), timeout=60)
            self.assertEqual(probe.returncode, 3, "the install ran without the lock")
            return 1, "Error: connect ECONNREFUSED"

        with mock.patch.object(snapshot_core, "_run_to_stderr", install), mock.patch.object(snapshot_core, "_say"):
            with self.assertRaises(snapshot_core.SnapshotError) as refused:
                snapshot_core.install_browser("browser")
        message = str(refused.exception)
        self.assertIn("Error: connect ECONNREFUSED", message)
        self.assertIn("needs the network", message)
        self.assertIn("-m playwright install --only-shell chromium", message)


if __name__ == "__main__":
    unittest.main()
