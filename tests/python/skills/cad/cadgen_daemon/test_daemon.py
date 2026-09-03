import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory


from cadgen.daemon import client as daemon_client
from cadgen.daemon import transport

DAEMON_DIR = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "daemon"
SPAWN_WAIT_SECONDS = 90.0  # daemon startup pays the full OCP import once

# The hardest kill the host has. Windows has no SIGKILL; there os.kill with any
# non-CTRL_* signal is TerminateProcess with the signal number as the exit code,
# so the kill is just as real -- it simply comes back as an exit CODE, which is
# why the assertions below ask describe_exit rather than spelling a signal.
KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)

BOX_SOURCE = """\
import build123d


from cadgen import step
@step
def model():
    return build123d.Box(10.0, 8.0, 4.0)


if __name__ == "__main__":
    model()
"""


def _authkey() -> bytes:
    key = transport.read_authkey(daemon_client.daemon_identity())
    if not key:
        raise RuntimeError("the daemon has not written its auth key")
    return key


def _raw_request(address: str, payload: dict) -> list[dict]:
    """One request, straight over the transport, bypassing the client's retry logic."""
    channel = transport.connect(str(address), _authkey())
    frames: list[dict] = []
    try:
        channel.send(json.dumps(payload).encode("utf-8"))
        while True:
            raw = channel.recv(30.0)
            if not raw:
                break
            frames.append(json.loads(raw.decode("utf-8")))
    finally:
        channel.close()
    return frames


class CadgenDaemonTests(unittest.TestCase):
    """One daemon serves the whole class; methods are ordered (test_a/b/c) and
    test_c deliberately stops the daemon via the staleness path."""

    server: subprocess.Popen | None = None

    @classmethod
    def setUpClass(cls) -> None:
        # AF_UNIX paths are length-limited (~104 bytes on macOS), so the socket gets a
        # short dir rather than the repo tmp root. A Windows pipe name is not a path and
        # has no such ceiling, so it is simply named after this test run.
        cls.socket_dir = tempfile.TemporaryDirectory(
            prefix="cadgen-daemon-",
            dir=None if os.name == "nt" else "/tmp",
            ignore_cleanup_errors=True,
        )
        if os.name == "nt":
            cls.address = rf"\\.\pipe\cadgen-daemon-test-{os.getpid()}"
        else:
            cls.address = str(Path(cls.socket_dir.name) / "daemon.sock")
        cls.model_tmp = temporary_directory(prefix="cadgen-daemon-model-")
        cls.model_dir = Path(cls.model_tmp.name)
        (cls.model_dir / "box.py").write_text(BOX_SOURCE, encoding="utf-8")

        # Build inline (cold) first so the daemon request is a warm current-skip.
        build_env = {k: v for k, v in os.environ.items() if k != "CADGEN_DAEMON"}
        build_env["CADGEN_DAEMON"] = "0"  # inline: the daemon under test starts below
        build = subprocess.run(
            [sys.executable, "box.py"],
            cwd=cls.model_dir,
            env=build_env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if build.returncode != 0:
            raise RuntimeError(f"inline warm-up build failed:\n{build.stdout}\n{build.stderr}")

        cls.log_path = Path(cls.socket_dir.name) / "daemon.log"
        cls._start_server()

    @classmethod
    def _start_server(cls) -> None:
        env = dict(os.environ)
        env["CADGEN_DAEMON_SOCKET"] = str(cls.address)
        env["CADGEN_DAEMON_IDLE_TIMEOUT"] = "300"  # orphan self-cleans if teardown is skipped
        with open(cls.log_path, "ab") as log_file:
            cls.server = subprocess.Popen(
                [sys.executable, str(DAEMON_DIR / "__main__.py")],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
        deadline = time.monotonic() + SPAWN_WAIT_SECONDS
        while time.monotonic() < deadline:
            if cls.server.poll() is not None:
                raise RuntimeError(f"daemon exited during startup:\n{cls.log_path.read_text(encoding='utf-8')}")
            try:
                probe = transport.connect(str(cls.address), _authkey())
            except (OSError, RuntimeError):
                time.sleep(0.1)
                continue
            probe.close()
            break
        else:
            raise RuntimeError(f"daemon address never appeared:\n{cls.log_path.read_text(encoding='utf-8')}")

    @classmethod
    def _live_worker_pids(cls) -> set[int]:
        """The pool's worker pids, asked while the supervisor still answers."""
        env = {"CADGEN_DAEMON": "1", "CADGEN_DAEMON_SOCKET": str(cls.address)}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("CADGEN_DAEMON_CHILD", None)
            status = daemon_client.status() or {}
        return {int(worker["pid"]) for worker in (status.get("workers") or []) if worker.get("pid")}

    @classmethod
    def tearDownClass(cls) -> None:
        workers: set[int] = set()
        if cls.server is not None and cls.server.poll() is None:
            # Asked here and nowhere earlier: a pid noted mid-run may have died
            # and been recycled by teardown, and os.kill on a recycled pid kills
            # a stranger. The pool cannot spawn between this answer and the
            # terminate() below because nothing is asking it for work.
            workers = cls._live_worker_pids()
            cls.server.terminate()
            try:
                cls.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.server.kill()
        # The workers are the supervisor's children, not ours, and terminate() is
        # TerminateProcess on Windows -- the SIGTERM handler that would reach
        # _POOL.shutdown() never runs there, so the workers outlive the daemon.
        # A worker mid-job is chdir'd into model_dir (between jobs it parks in
        # the system temp dir, see worker._park), and Windows refuses to remove a
        # live process's current directory, so an unreaped worker turns the
        # cleanup below into WinError 32. Reaping is unconditional: the same
        # leak is simply invisible on POSIX.
        for pid in workers:
            with contextlib.suppress(OSError):
                os.kill(pid, KILL_SIGNAL)
        leaked: list[int] = []
        if os.name != "nt":
            # os.kill(pid, 0) is a liveness probe only on POSIX; on Windows it
            # would terminate the process rather than ask about it. There the
            # wait is the cleanup's own WinError 32 ladder: TerminateProcess is
            # asynchronous, so the handles can outlast the call that ended them.
            deadline = time.monotonic() + 10.0
            alive = workers
            while alive and time.monotonic() < deadline:
                still: set[int] = set()
                for pid in alive:
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        continue
                    still.add(pid)
                alive = still
                if alive:
                    time.sleep(0.1)
            leaked = sorted(alive)
        try:
            cls.model_tmp.cleanup()
        finally:
            # The daemon's log handle can outlive terminate() by a moment, and Windows
            # refuses to delete a file another process still holds open (WinError 32).
            # That is a teardown race over a temp directory, not a defect worth failing a
            # suite for -- the OS reclaims it either way.
            cls.socket_dir.cleanup()
        # After the cleanups, never before: a diagnostic must not leak the two
        # directories it was added to protect.
        if leaked:
            raise AssertionError(f"daemon workers outlived the teardown: {leaked}")

    def _warm_run(self, argv: list[str]) -> tuple[int | None, str]:
        env = {"CADGEN_DAEMON": "1", "CADGEN_DAEMON_SOCKET": str(self.address)}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env):
            os.environ.pop("CADGEN_DAEMON_CHILD", None)
            with redirect_stdout(out), redirect_stderr(err):
                exit_code = daemon_client.run_via_daemon("run", argv, cwd=str(self.model_dir))
        return exit_code, out.getvalue() + err.getvalue()

    def test_a_warm_gen_request_skips_current_model(self) -> None:
        exit_code, output = self._warm_run(["box.py"])
        self.assertEqual(0, exit_code, output)
        self.assertIn("is current", output)

    def test_b_second_request_is_fast_and_correct(self) -> None:
        started = time.perf_counter()
        exit_code, output = self._warm_run(["box.py"])
        elapsed = time.perf_counter() - started
        self.assertEqual(0, exit_code, output)
        self.assertIn("is current", output)
        self.assertLess(elapsed, 2.0, f"warm request took {elapsed:.2f}s")

    def test_c_version_token_mismatch_triggers_restart(self) -> None:
        frames = _raw_request(
            self.address,
            {"tool": "run", "argv": ["box.py"], "cwd": str(self.model_dir), "token": -1},
        )
        self.assertEqual([{"restart": True}], frames)
        # The server clears its address BEFORE replying, then exits cleanly. Only POSIX
        # leaves anything to clear: a named pipe vanishes with the process that served it.
        if os.name != "nt":
            self.assertFalse(Path(self.address).exists())
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if self.server is None or self.server.poll() is not None:
                break
            time.sleep(0.1)
        else:
            self.fail("daemon did not exit after the restart reply")

    def test_d_client_disconnect_kills_the_worker_not_the_daemon(self) -> None:
        # test_c leaves the daemon exited via the staleness path; start fresh.
        type(self)._start_server()

        # A model the daemon has NOT built yet, so the request is a real
        # multi-second build rather than an instant current-skip.
        (self.model_dir / "box_orphan.py").write_text(
            BOX_SOURCE.replace("10.0, 8.0, 4.0", "9.0, 7.0, 3.0"), encoding="utf-8"
        )

        # Send a valid request, then close the connection without reading the response —
        # the daemon-side view of a killed client. The liveness watchdog must stop the
        # orphaned build.
        #
        # This used to require the DAEMON to exit: the build ran inside it, so there was
        # no smaller thing to stop, and every queued request died with it. Now the job
        # runs in a pooled worker, so the watchdog kills that one worker and the
        # supervisor keeps serving — which is what the assertions below check.
        channel = transport.connect(str(self.address), _authkey())
        try:
            channel.send(json.dumps({
                "tool": "run",
                "argv": ["box_orphan.py"],
                "cwd": str(self.model_dir),
                "token": daemon_client.compute_version_token(),
            }).encode("utf-8"))
            time.sleep(0.3)  # let the job start before the client "dies"
        finally:
            channel.close()

        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if "killing worker" in self.log_path.read_text(encoding="utf-8"):
                break
            time.sleep(0.2)
        else:
            self.fail(
                "watchdog never killed the orphaned job's worker:\n"
                f"{self.log_path.read_text(encoding='utf-8')}"
            )

        # The supervisor survived, which is the point of moving work into workers.
        self.assertIsNone(
            self.server.poll(),
            "the daemon exited; a lost client should cost one worker, not the daemon",
        )

        # And it still serves: the pool replaces the killed worker on the next acquire.
        # run_via_daemon gates on CADGEN_DAEMON, which this test process does not set.
        with mock.patch.dict(
            os.environ,
            {"CADGEN_DAEMON": "1", "CADGEN_DAEMON_SOCKET": str(self.address)},
        ):
            exit_code = daemon_client.run_via_daemon(
                "run", ["box_orphan.py"], str(self.model_dir)
            )
        self.assertEqual(exit_code, 0, self.log_path.read_text(encoding="utf-8"))

    def test_e_a_worker_killed_mid_job_is_reported_with_the_cold_rerun(self) -> None:
        """The 35-minute validate that ended in `worker closed the connection`.

        A real worker, a real kill (SIGKILL is what the OOM killer sends), the
        real relay: the client must say the worker died and how, name the job,
        and print the exact cold rerun -- and must NOT quietly run the job cold."""
        import threading

        if self.server is None or self.server.poll() is not None:
            type(self)._start_server()
        # A model that sleeps inside its entry: long enough to be killed mid-job
        # deterministically, and never current, so the worker really runs it.
        (self.model_dir / "box_sleepy.py").write_text(
            BOX_SOURCE.replace(
                "def model():\n", "def model():\n    import time; time.sleep(30)\n"
            ),
            encoding="utf-8",
        )
        outcome: dict = {}
        script = self.model_dir / "box_sleepy.py"

        def run() -> None:
            # The decorator's real handoff shape: the script path leads argv and
            # prog is how the user spelled it (cadgen.authoring._build).
            env = {"CADGEN_DAEMON": "1", "CADGEN_DAEMON_SOCKET": str(self.address)}
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.dict(os.environ, env):
                os.environ.pop("CADGEN_DAEMON_CHILD", None)
                with redirect_stdout(out), redirect_stderr(err):
                    outcome["exit"] = daemon_client.run_via_daemon(
                        "run", [str(script), "--force"], cwd=str(self.model_dir),
                        prog="python box_sleepy.py",
                    )
            outcome["output"] = out.getvalue() + err.getvalue()

        thread = threading.Thread(target=run)
        thread.start()
        env = {"CADGEN_DAEMON": "1", "CADGEN_DAEMON_SOCKET": str(self.address)}
        busy_pid = None
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline and busy_pid is None:
            with mock.patch.dict(os.environ, env):
                os.environ.pop("CADGEN_DAEMON_CHILD", None)
                status = daemon_client.status() or {}
            for worker in status.get("workers") or []:
                if worker.get("busy"):
                    busy_pid = int(worker["pid"])
            time.sleep(0.2)
        self.assertIsNotNone(busy_pid, "no worker ever went busy on the sleeping model")
        time.sleep(1.0)  # let the job be well inside model() before the kill
        os.kill(busy_pid, KILL_SIGNAL)
        thread.join(timeout=60.0)
        self.assertFalse(thread.is_alive(), "the client never returned after its worker died")

        self.assertEqual(outcome["exit"], 1, outcome["output"])
        output = outcome["output"]
        self.assertIn("the warm worker running `python box_sleepy.py --force` died mid-job", output)
        # How the death reads, and how the rerun is spelled, are both the
        # platform's: a POSIX wait status is the negated signal, a Windows one is
        # the exit code TerminateProcess was given. Ask the same helpers the
        # production message uses instead of hardcoding the POSIX answers.
        from cadgen.daemon import pool as pool_mod

        status_code = int(KILL_SIGNAL) if os.name == "nt" else -int(KILL_SIGNAL)
        self.assertIn(pool_mod.describe_exit(status_code), output)
        self.assertIn("out of memory", output)
        self.assertIn("NOT retried", output)
        self.assertIn(
            daemon_client.cold_rerun_command(
                {"tool": "run", "prog": "python box_sleepy.py", "argv": [str(script), "--force"]}
            ),
            output,
        )
        self.assertNotIn("worker closed the connection", output)
        # And the supervisor is still up, serving the next request.
        self.assertIsNone(self.server.poll())


if __name__ == "__main__":
    unittest.main()
