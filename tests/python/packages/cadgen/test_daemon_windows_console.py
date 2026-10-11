"""A detached daemon's workers open no console window on Windows (#597).

The daemon is started detached (``client.detach_kwargs``) and starts its workers, and
they their builds, Node and ffmpeg, as plain console programs. Started DETACHED_PROCESS,
the daemon had no console, so Windows gave every worker a new console with a window of
its own: a window per worker for as long as it lived, and closing one ended the worker
with STATUS_CONTROL_C_EXIT -- "worker ... exited with 0xC000013A (STATUS_CONTROL_C_EXIT)
before announcing itself". Pinned the way it broke: a process started as the daemon is
starts a child as ``pool.Worker`` does, and the child reports its console window.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cadgen.daemon import client  # noqa: E402

# The worker: report the console window it was given, then wait to be released.
_CHILD = textwrap.dedent("""
    import ctypes, json, sys
    print(json.dumps({"window": ctypes.windll.kernel32.GetConsoleWindow()}), flush=True)
    sys.stdin.read()
""")

# The daemon: start the worker as pool.Worker does -- pipes, no creation flags -- and
# relay its report to the log this process writes, as the daemon's stdout is.
_PARENT = textwrap.dedent("""
    import ctypes, json, subprocess, sys
    child = subprocess.Popen([sys.executable, "-c", sys.argv[1]], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
    report = json.loads(child.stdout.readline())
    child.stdin.close()
    child.wait()
    report["parent_window"] = ctypes.windll.kernel32.GetConsoleWindow()
    print(json.dumps(report), flush=True)
""")


@unittest.skipUnless(os.name == "nt", "console windows are Windows': POSIX detaches into a new session")
class DetachedDaemonWorkersOpenNoWindow(unittest.TestCase):
    def test_a_worker_of_a_detached_daemon_has_no_console_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "daemon.log"
            with open(log, "wb") as out:
                daemon = subprocess.Popen(
                    [sys.executable, "-c", _PARENT, _CHILD],
                    stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, cwd=tmp,
                    **client.detach_kwargs(),
                )
                # A hang guard, not a wait for time to pass: both processes exit at once.
                self.assertEqual(daemon.wait(timeout=120), 0, log.read_text(encoding="utf-8", errors="replace"))
            report = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(report["parent_window"], 0, "the detached daemon itself has a console window")
        self.assertEqual(report["window"], 0, "a worker of the detached daemon opened a console window")


if __name__ == "__main__":
    unittest.main()
