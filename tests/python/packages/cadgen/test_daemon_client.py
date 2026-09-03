"""What the client says when the warm worker running its job dies.

The defect this pins: a 2,700-occurrence validate ran 35 minutes on a warm worker,
the worker was killed (out of memory, most likely), and the caller saw one line --
``cadgen-daemon: worker closed the connection`` -- and exit 1. Nothing said the
worker had died, nothing named the job, nothing said how to run it where the failure
could be seen. The fix is the MESSAGE, deliberately not a silent cold retry: a
half-hour job re-running unannounced is worse than the failure it hides.

Driven through ``_run_request`` with a scripted channel, so the wording is pinned at
the one place it is composed and no daemon has to be started.
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cadgen.daemon import client  # noqa: E402
from cadgen.daemon import pool as pool_mod  # noqa: E402
from cadgen.daemon import server  # noqa: E402


class _ScriptedChannel:
    """A transport channel that answers a request with a fixed sequence of frames."""

    def __init__(self, frames: list[dict]) -> None:
        self.sent: list[dict] = []
        self._frames = [json.dumps(frame).encode("utf-8") for frame in frames]

    def send(self, raw: bytes) -> None:
        self.sent.append(json.loads(raw.decode("utf-8")))

    def recv(self, timeout):
        if not self._frames:
            return b""  # closed
        return self._frames.pop(0)

    def close(self) -> None:
        pass


PAYLOAD = {
    "tool": "inspect",
    "prog": "cadgen step inspect",
    "argv": ["validate", "tmp/noexh/noexh.step", "--out", "validate.json"],
    "cwd": "/work",
    "env": {},
    "token": "t",
}


class DeadWorkerMessage(unittest.TestCase):
    def _run(self, frames: list[dict]) -> tuple[object, str, str]:
        channel = _ScriptedChannel(frames)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            outcome = client._run_request(channel, PAYLOAD)
        return outcome, out.getvalue(), err.getvalue()

    def test_the_death_is_explained_and_the_exit_code_kept(self):
        outcome, out, err = self._run([
            {"stream": "stdout", "data": ""},
            {"workerDied": {"pid": 4242, "detail": "worker 4242 was killed by SIGKILL (signal 9)",
                            "exitStatus": -9}},
            {"exit": 1},
        ])
        self.assertEqual(outcome, 1)
        self.assertEqual(out, "")
        # Every clause the caller needed and did not have.
        self.assertIn("the warm worker running", err)
        self.assertIn("died mid-job", err)
        self.assertIn("killed by SIGKILL (signal 9)", err)
        self.assertIn("out of memory", err)
        self.assertIn("`cadgen step inspect validate tmp/noexh/noexh.step --out validate.json`", err)
        self.assertIn("NOT retried", err)
        # The rerun spelling is the platform's, so ask the helper that composes it.
        # That makes this assertion only "the message carries the rerun"; the
        # exact text of BOTH spellings is pinned in ColdRerunSpelling below.
        self.assertIn(client.cold_rerun_command(PAYLOAD), err)
        self.assertNotIn("worker closed the connection", err)

    def test_a_job_with_no_prog_is_named_by_its_tool(self):
        payload = {**PAYLOAD, "prog": None, "argv": ["build", "a b.step", "out.step"]}
        text = client.worker_died_message(payload, {"detail": "worker 1 exited with code 139"})
        self.assertIn("`cadgen inspect build a b.step out.step`", text)
        self.assertIn("exited with code 139", text)
        if sys.platform != "win32":
            # The rerun quotes what the shell needs quoted.
            self.assertIn("CADGEN_DAEMON=0 cadgen inspect build 'a b.step' out.step", text)

    def test_a_model_script_run_is_named_and_rerun_as_python(self):
        # The decorator's warm handoff: prog `python <name>`, argv `[<path>, *args]`.
        payload = {"tool": "run", "prog": "python box.py", "argv": ["/work/src/box.py", "--force"]}
        text = client.worker_died_message(payload, {"detail": "worker 3 was killed by SIGKILL (signal 9)"})
        self.assertIn("`python box.py --force` died mid-job", text)
        self.assertNotIn("box.py /work/src/box.py", text)
        if sys.platform != "win32":
            self.assertIn("CADGEN_DAEMON=0 python /work/src/box.py --force", text)

    def test_an_ordinary_stderr_frame_is_still_just_relayed(self):
        outcome, _out, err = self._run([{"stream": "stderr", "data": "hello\n"}, {"exit": 0}])
        self.assertEqual(outcome, 0)
        self.assertEqual(err, "hello\n")


class ServerRelaysTheDeath(unittest.TestCase):
    """The supervisor turns WorkerGone into its own frame, before the exit frame,
    and logs it -- ``cadgen daemon status`` cannot show a worker that is gone."""

    class _DyingWorker:
        pid = 777

        def __init__(self) -> None:
            self.sent: list[dict] = []

        def send(self, request: dict) -> None:
            self.sent.append(request)

        def frames(self):
            yield {"stream": "stdout", "data": "partial "}
            raise pool_mod.WorkerGone(
                "worker 777 was killed by SIGKILL (signal 9)", exit_status=-9
            )

        def alive(self) -> bool:
            return False

    class _Conn:
        def __init__(self) -> None:
            self.frames: list[dict] = []

        def send(self, raw: bytes) -> None:
            self.frames.append(json.loads(raw.decode("utf-8")))

    def test_worker_died_frame_precedes_the_exit_frame(self):
        worker = self._DyingWorker()
        pool = mock.Mock()
        pool.acquire.return_value = worker
        conn = self._Conn()
        request = {"tool": "inspect", "argv": ["validate", "x.step"], "cwd": "/w", "prog": "cadgen step inspect"}
        logged: list[str] = []
        with mock.patch.object(server, "_POOL", pool), \
                mock.patch.object(server, "_log", logged.append), \
                mock.patch.object(server, "CLIENT_LIVENESS_INTERVAL_SECONDS", 60.0):
            server._handle_request(conn, request, mock.Mock(), mock.Mock())
        kinds = [next(iter(frame)) for frame in conn.frames if frame != {"stream": "stdout", "data": ""}]
        self.assertEqual(kinds, ["stream", "workerDied", "exit"])
        died = next(frame["workerDied"] for frame in conn.frames if "workerDied" in frame)
        self.assertEqual(died["pid"], 777)
        self.assertEqual(died["exitStatus"], -9)
        self.assertIn("SIGKILL", died["detail"])
        self.assertEqual(conn.frames[-1], {"exit": 1})
        pool.release.assert_called_once_with(worker, healthy=False)
        self.assertTrue(any("died mid-job" in line for line in logged), logged)

    def test_the_invoke_path_says_the_same_thing_in_its_payload(self):
        exc = pool_mod.WorkerGone("worker 5 exited with code 137", exit_status=137)
        text = server.worker_died_message(exc, job="cadgen.step_artifact_cli --step a.step")
        self.assertIn("died mid-job", text)
        self.assertIn("exited with code 137", text)
        self.assertIn("CADGEN_DAEMON=0", text)
        self.assertIn("not retried", text)


class DescribeExit(unittest.TestCase):
    def test_signal_code_and_open_pipe_are_told_apart(self):
        import signal

        expected = "was killed by SIGKILL (signal 9)" if hasattr(signal, "SIGKILL") else "was killed by signal 9"
        self.assertEqual(pool_mod.describe_exit(-9), expected)
        self.assertEqual(pool_mod.describe_exit(2), "exited with code 2")
        self.assertEqual(pool_mod.describe_exit(None), "closed its output while still running")

    def test_an_unnamed_signal_is_not_described_twice(self):
        """99 is not a signal on any host, so this is the Windows wording for 9 --
        `was killed by signal 9 (signal 9)` was the stutter it used to produce."""
        self.assertEqual(pool_mod.describe_exit(-99), "was killed by signal 99")

    def test_a_windows_exit_status_is_a_code_not_a_signal(self):
        """Windows' Popen.wait returns a non-negative DWORD: a TerminateProcess
        kill comes back as the exit CODE, never as a negative signal."""
        self.assertEqual(pool_mod.describe_exit(9), "exited with code 9")


class ColdRerunSpelling(unittest.TestCase):
    """The rerun has to be paste-able in the shell the user is actually in.

    `cold_rerun_command` returns the COMMAND only: the env prefix is
    shell-specific and this code cannot know the shell. `set X=0 && cmd` works
    in cmd.exe and, in PowerShell, assigns a variable literally named `X=0`
    before failing on `&&` -- so the message offers both spellings under a
    neutral instruction instead of guessing.
    """

    COMMAND = "cadgen step inspect validate tmp/noexh/noexh.step --out validate.json"

    def test_the_command_carries_no_env_prefix_on_either_platform(self):
        for name in ("posix", "nt"):
            with self.subTest(os_name=name), mock.patch.object(client.os, "name", name):
                spelled = client.cold_rerun_command(PAYLOAD)
                self.assertEqual(self.COMMAND, spelled)
                self.assertNotIn("CADGEN_DAEMON", spelled)

    def test_posix_keeps_the_one_line_env_prefix(self):
        with mock.patch.object(client.os, "name", "posix"):
            self.assertEqual(
                f"  CADGEN_DAEMON=0 {self.COMMAND}\n",
                client.cold_rerun_instructions(PAYLOAD),
            )

    def test_windows_offers_both_shells_under_a_neutral_instruction(self):
        with mock.patch.object(client.os, "name", "nt"):
            spelled = client.cold_rerun_instructions(PAYLOAD)
        self.assertIn("Set CADGEN_DAEMON=0 in the environment", spelled)
        self.assertIn(f"set CADGEN_DAEMON=0 && {self.COMMAND}", spelled)
        self.assertIn(f"$env:CADGEN_DAEMON='0'; {self.COMMAND}", spelled)
        # The bare command stands alone on its own line, so it is paste-able in
        # a shell neither spelling covers (Git Bash, fish, csh).
        self.assertIn(f"\n    {self.COMMAND}\n", spelled)

    def test_the_message_carries_the_spelling_for_the_running_platform(self):
        for name in ("posix", "nt"):
            with self.subTest(os_name=name), mock.patch.object(client.os, "name", name):
                message = client.worker_died_message(PAYLOAD, {"detail": "worker 1 exited with code 1"})
                self.assertIn(client.cold_rerun_instructions(PAYLOAD), message)
                self.assertIn("was NOT", message)

if __name__ == "__main__":
    unittest.main()
