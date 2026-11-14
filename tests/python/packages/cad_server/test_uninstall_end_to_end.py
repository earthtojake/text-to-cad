"""``cad uninstall`` with a thread open, as a person's machine runs it (found on a real device, 2026-11-14): release A
set up by its own ``cad setup`` in a home of this test's own, and an app's thread holding A's server through its
launcher (``cad-mcp`` as version A on the default channel, started as an app starts it: its ``initialize`` and one
request, so its hold is up). The uninstall takes the default channel off before it stops the server, so the launcher,
finding its server gone, starts none again: the uninstall exits 0, A's code is removed and its data kept, nothing runs
from A's folder, and the thread's next tool call is answered with the line that says its channel is not on this
computer any more. The install command run again, the same thread is served again.

The launcher is this checkout's ``cad_mcp`` told its version (``CAD_INSTALLATION_VERSION``, as a development install
names its build): the shim's code as a release's wheel carries it, reaching the version this test installed. The machine
is ``test_update_end_to_end.Machine``'s (its home, state, engine and command folders; release A this source tree's
library and server as wheels, the kernel's extra naming nothing)."""

from __future__ import annotations

import itertools
import json
import queue
import subprocess
import sys
import threading
import time
import unittest

from tests.python.packages.cad_server.test_update_end_to_end import A, WINDOWS, Machine, command, release
from tests.python.support.paths import SHIM

from cad_mcp import engine

# How long one answer of the launcher, or one wait on the machine, may take: a server's start, an install from uv's
# cache. A bound on a hang, not on the work.
SECONDS = 300.0


class Launcher:
    """The launcher an app starts for a thread (``cad-mcp``), as version ``version`` on the default channel, talking
    MCP on its standard input and output: each answer read on a thread of its own and handed to the call that waits
    for its id, so several calls can be in flight, as an app's are."""

    def __init__(self, machine: Machine, version: str) -> None:
        # Not Claude Code's (a test run from it inherits its mark, and its sessions list no tools).
        env = {key: value for key, value in machine.env.items() if key not in ("CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE")}
        env.update({"PYTHONPATH": str(SHIM / "src"), engine.INSTALLATION_ENV: version})
        self.process = subprocess.Popen([sys.executable, "-m", "cad_mcp"], env=env, cwd=machine.work,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, encoding="utf-8")
        self.lock = threading.Lock()
        self.waiting: dict[int, queue.Queue] = {}
        self.ids = itertools.count(1)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.process.stdout:
            message = json.loads(line)
            with self.lock:
                found = self.waiting.pop(message.get("id"), None)
            if found is not None:
                found.put(message)

    def send(self, message: dict) -> None:
        with self.lock:
            self.process.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
            self.process.stdin.flush()

    def call(self, method: str, params: dict) -> dict:
        """Request ``method`` and its answer."""
        ident, answered = next(self.ids), queue.Queue()
        with self.lock:
            self.waiting[ident] = answered
        self.send({"id": ident, "method": method, "params": params})
        try:
            return answered.get(timeout=SECONDS)
        except queue.Empty:
            raise AssertionError(f"the launcher did not answer {method} within {SECONDS:.0f} s") from None

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(60)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process.stdout.close()


class UninstallWithAThreadOpenTest(Machine):
    def from_version(self, version: str) -> list[str]:
        """The processes running from version ``version``'s folder, each its id and command line."""
        if WINDOWS:
            listing = ["powershell", "-NoProfile", "-Command",
                       "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"]
        else:
            listing = ["ps", "-axo", "pid=,command="]
        listed = subprocess.run(listing, capture_output=True, text=True, timeout=60).stdout
        folder = str(self.work / "state" / "versions" / version)
        return [line.strip() for line in listed.splitlines() if folder in line]

    def until(self, condition, what: str):
        deadline = time.monotonic() + SECONDS
        while not (found := condition()):
            self.assertLess(time.monotonic(), deadline, f"{what}, not within {SECONDS:.0f} s\n{self.said()}")
            time.sleep(0.1)
        return found

    def test_a_thread_open_starts_no_server_after_an_uninstall_and_is_served_again_after_an_install(self) -> None:
        release(A, self.wheels)
        boot = self.installer(A)
        set_up = self.run_here([command(boot), "setup"], timeout=600)
        self.assertEqual(set_up.returncode, 0, set_up.stdout + set_up.stderr)
        state = self.work / "state"
        self.assertEqual((state / "default").read_text(encoding="utf-8").strip(), A)

        # A thread: its launcher, its initialize and one request; its server is A's, held.
        launcher = Launcher(self, A)
        self.addCleanup(launcher.close)
        started = launcher.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                  "clientInfo": {"name": "test-uninstall", "version": "0"}})
        self.assertIn("result", started, started)
        launcher.send({"method": "notifications/initialized", "params": {}})
        listed = launcher.call("tools/list", {})
        self.assertTrue(listed.get("result", {}).get("tools"), listed)
        self.assertTrue(self.from_version(A), "A's server runs")

        # The uninstall: the cad command on macOS and Linux, as the device ran it. On Windows the install command's
        # own (`install.ps1 --uninstall` runs `cad uninstall` from uvx's environment): there the system refuses to
        # remove the code a command runs from, which the cad command's is (then its code stays, and the run says so).
        # All through it, the thread's view asks its server something, one call after another (an open CAD view syncs
        # every second): a launcher that starts its server again as it finds it gone did so here, from the code being
        # removed, and the uninstall failed.
        uninstall = command(boot) if WINDOWS else self.work / "bin" / "cad"
        uninstalling, asked = threading.Event(), []

        def asking() -> None:
            while not uninstalling.is_set():
                asked.append(launcher.call("tools/call", {"name": "cad_show", "arguments": {}}))

        poller = threading.Thread(target=asking, daemon=True)
        poller.start()
        try:
            done = self.run_here([uninstall, "uninstall", "--yes"], timeout=600)
        finally:
            uninstalling.set()
            poller.join(SECONDS)
        self.assertGreater(len(asked), 1, "the thread asked all through the uninstall")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr + self.running())
        self.assertFalse((state / "versions" / A / "code").exists(), done.stdout)
        self.assertTrue((state / "versions" / A / "data").is_dir(), "its data kept for a later install")
        self.assertFalse((state / "default").exists())

        # The thread's next tool call: answered by its launcher, which starts no server again.
        line = engine.removed_line(A, None)
        answer = launcher.call("tools/call", {"name": "cad_show", "arguments": {}})
        self.assertEqual(answer.get("result"), {"content": [{"type": "text", "text": line}], "isError": True}, answer)
        self.until(lambda: not self.from_version(A), f"nothing running from {A}'s folder")

        # The install command again: the same thread is served by A's server.
        set_up = self.run_here([command(boot), "setup"], timeout=600)
        self.assertEqual(set_up.returncode, 0, set_up.stdout + set_up.stderr)
        answer = launcher.call("tools/call", {"name": "cad_show", "arguments": {}})
        self.assertNotIn(line, json.dumps(answer), answer)
        self.assertIn("result", answer, answer)
        self.assertTrue(self.from_version(A), "A's server started again for the thread")


if __name__ == "__main__":
    unittest.main()
