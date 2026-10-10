"""The build daemon's telemetry (``cadgen/daemon/telemetry.py``): which requests are builds and how each one
ended, what a command hands the daemon to count (``client.hand_over``), and that none of it starts, waits on or
fails anything. Driven without a daemon: a request and its ledger job in, the batch the daemon's recorder would
send out (``cadgen/analytics.py``)."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from cadgen import analytics
from cadgen.daemon import client, telemetry
from cadgen.results import SnapshotFile, SnapshotResult
from cadgen.snapshot_cli import SnapshotOptions, _count_snapshot

RUN = {"tool": "run", "argv": ["plate.py"], "env": {}}


class DaemonTelemetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp), "DO_NOT_TRACK": "", "CADGEN_TELEMETRY": "",
                                                   "CADGEN_DAEMON": ""})
        environment.start()
        self.addCleanup(environment.stop)
        analytics.choose(True, by="cli", path=self.tmp / "settings.json")
        self.sent: list[dict] = []
        self.recorder = analytics.Recorder(process="daemon", path=self.tmp / "settings.json",
                                           send=lambda payload: self.sent.append(payload) or True)
        serving = mock.patch.object(telemetry, "_RECORDER", self.recorder)
        serving.start()
        self.addCleanup(serving.stop)

    def events(self) -> list[dict]:
        self.assertTrue(self.recorder.flush())
        return self.sent[-1]["events"]

    def test_a_build_is_counted_once_for_whoever_asked_and_by_how_it_ended(self) -> None:
        built = telemetry.build(RUN, {"id": "e:job-1", "outputs": ["/w/plate.step", "/w/plate.stl"]})
        for state in ("queued", "building", "done"):
            built.observe({"model": "/w/plate.py", "state": state, "job": "e:job-1"})
        built.finish(0, None, 2.5)
        # Its model was current: the store's answer, with nothing built. Another job's events are that job's.
        current = telemetry.build(RUN, {"id": "e:job-2", "outputs": ["/w/plate.step"]})
        current.observe({"model": "/w/plate.py", "state": "current", "job": "e:job-2"})
        current.observe({"model": "/w/other.py", "state": "building", "job": "e:job-9"})
        current.finish(0, None, 0.5)
        # A child this model announced makes it an assembly; it failed.
        assembly = telemetry.build(RUN, {"id": "e:job-3", "outputs": ["/w/arm.step"]})
        assembly.observe({"model": "/w/link.py", "state": "current", "job": "e:job-3", "parent": "/w/arm.py"})
        assembly.observe({"model": "/w/arm.py", "state": "building", "job": "e:job-3"})
        telemetry.exited({"exit": 1, "failure": "kernel_error"}, assembly)  # why, as its worker decided
        assembly.finish(1, None, 4.0)
        # A failure its worker named nothing for, or named outside the vocabulary: ``other``.
        telemetry.build(RUN, {"id": "e:job-8", "outputs": ["/w/plate.step"]}).finish(1, None, 0.5)
        unnamed = telemetry.build(RUN, {"id": "e:job-9", "outputs": ["/w/plate.step"]})
        telemetry.exited({"exit": 1, "failure": "No module named secret_lib"}, unnamed)
        unnamed.finish(1, None, 0.5)
        telemetry.build(RUN, {"id": "e:job-4", "outputs": ["/w/plate.step"]}).finish(1, "crashed", 1.0)
        telemetry.worker_died(-11)  # what ended that build: a crash, with its exit status
        telemetry.build(RUN, {"id": "e:job-5", "outputs": ["/w/plate.step"]}).finish(1, "cancelled", 1.0)
        # A drawing its worker says came from the store: the daemon cannot see that in its events.
        dxf = telemetry.build(RUN, {"id": "e:job-6", "outputs": ["/w/sketch.dxf"]})
        telemetry.exited({"exit": 0, "reused": True}, dxf)
        dxf.finish(0, None, 0.5)
        telemetry.build({"tool": "stl-build", "argv": ["plate.py"], "env": {}}, {"id": "e:job-7", "outputs": []}).finish(0, None, 0.5)
        telemetry.worker_died(None)  # a worker that never started, and said nothing as it went
        self.assertEqual(self.events(), [
            {"name": "build", "kind": "dxf", "via": "script", "count": 1, "failed": 0, "crashed": 0, "cancelled": 0, "cached": 1,
             "seconds": 0.5, "longest": 0.5},
            {"name": "build", "kind": "step", "via": "script", "count": 7, "failed": 3, "crashed": 1, "cancelled": 1, "cached": 1,
             "seconds": 10.0, "longest": 4.0},
            {"name": "build", "kind": "stl", "via": "command", "count": 1, "failed": 0, "crashed": 0, "cancelled": 0, "cached": 0,
             "seconds": 0.5, "longest": 0.5},
            # Every failed build once, by why: the reasons add up to ``failed``.
            {"name": "build_failure", "kind": "step", "via": "script", "reason": "kernel_error", "count": 1},
            {"name": "build_failure", "kind": "step", "via": "script", "reason": "other", "count": 2},
            {"name": "feature", "feature": "assembly", "count": 1},
            {"name": "feature", "feature": "declared_mesh", "count": 1},
            {"name": "health", "workers": 0, "crashes": 2, "recycles": 0, "refusals": 0},
            {"name": "exception", "where": "build", "type": "WorkerDied", "handled": False, "frames": [], "status": -11, "count": 1},
            {"name": "exception", "where": "build", "type": "WorkerDied", "handled": False, "frames": [], "count": 1},
        ])
        self.assertEqual(self.sent[-1]["process"], "daemon")
        self.assertNotIn("/w/", json.dumps(self.sent))
        self.assertNotIn("secret", json.dumps(self.sent))

    def test_a_jobs_crashes_and_its_reuse_ride_its_exit_frame(self) -> None:
        # In a build worker (worker.serve): what cadgen decided as the job ran, for the daemon.
        crash = {"where": "build", "type": "KeyError", "handled": True,
                 "frames": [{"file": "cadgen/_internal/generation.py", "function": "build", "line": 7}]}
        telemetry.job_started()
        telemetry.job_reused(True)
        telemetry.job_crashed(crash)
        self.assertEqual(telemetry.job_finished(), {"reused": True, "crashes": [crash]})
        telemetry.job_started()
        for reused in (True, False):  # one part from the store, one built: not the store's answer
            telemetry.job_reused(reused)
        self.assertEqual(telemetry.job_finished(), {})
        telemetry.job_reused(True)  # outside a job, as in any other process: nothing kept
        telemetry.job_crashed(crash)
        self.assertEqual(telemetry.job_finished(), {})
        # The daemon takes a worker's crashes as another process's: checked before they are noted.
        telemetry.exited({"exit": 1, "crashes": [crash, {**crash, "frames": [{"file": "/Users/someone/x.py", "function": "f"}]}]}, None)
        self.assertEqual([event for event in self.events() if event["name"] == "exception"], [{"name": "exception", **crash, "count": 1}])

    def test_a_commands_result_says_whether_it_was_the_stores(self) -> None:
        from cadgen.results import BuildResult, CompileResult, MeshExportFile, MeshExportResult

        def reused(result) -> dict:
            telemetry.job_started()
            telemetry.job_result(result)
            return telemetry.job_finished()

        mesh = lambda skipped: MeshExportFile(path=Path("/w/a.stl"), fmt="stl", skipped=skipped)  # noqa: E731
        self.assertEqual(reused(CompileResult(ok=True, document=None, tree="t", skipped=True)), {"reused": True})
        self.assertEqual(reused(BuildResult(ok=True, document=None, tree="t", skipped=False, sidecar_only=True)), {"reused": True})
        self.assertEqual(reused(BuildResult(ok=True, document=None, tree="t", skipped=False)), {})
        self.assertEqual(reused(MeshExportResult(ok=True, files=(mesh(True), mesh(True)))), {"reused": True})
        self.assertEqual(reused(MeshExportResult(ok=True, files=(mesh(True), mesh(False)))), {})
        self.assertEqual(reused(object()), {}, "a result that says nothing of the store")

    def test_what_is_not_a_build_is_not_counted(self) -> None:
        job = {"id": "e:job-1", "outputs": ["/w/plate.step"]}
        for request in (
            {**RUN, "dependency": True},  # a child's build, or a compile a build asked for: that build's work
            {"tool": "artifact", "argv": [], "env": {}},  # a view's
            {"tool": "step-build", "argv": ["plate.py", "--help"], "env": {}},
            {**RUN, "env": {"DO_NOT_TRACK": "1"}},  # a client whose environment says no, whatever the daemon's said
            {**RUN, "env": {"CADGEN_TELEMETRY": "off"}},
            {"tool": "a-tool-of-tomorrow", "argv": [], "env": {}},
        ):
            with self.subTest(request=request):
                self.assertIsNone(telemetry.build(request, job))
        # Nor anything at all outside a daemon that serves.
        with mock.patch.object(telemetry, "_RECORDER", None):
            self.assertIsNone(telemetry.build(RUN, job))
            telemetry.counted({"snapshots": [{"format": "step", "ok": True, "seconds": 1.0}]})
            telemetry.worker_died(-11)
        self.assertFalse(self.recorder.flush())
        # The variables that say no travel with every build a client asks for.
        self.assertLessEqual(set(analytics.ENVIRONMENT), set(client.FORWARDED_ENV_VARS))

    def test_a_command_hands_its_counts_over_and_the_daemon_takes_only_what_it_knows(self) -> None:
        handed: list[dict] = []

        class Channel:
            def send(self, raw: bytes) -> None:
                handed.append(json.loads(raw.decode("utf-8")))

            def close(self) -> None:
                pass

        with mock.patch.object(client, "daemon_supported", return_value=True), \
                mock.patch.object(client, "_connect", return_value=Channel()):
            client.hand_over({"snapshots": [{"format": "step", "ok": True, "seconds": 1.5},
                                            {"format": "stl", "ok": False, "seconds": 0.5},
                                            {"format": "docx", "ok": True, "seconds": 1.0},
                                            {"format": "step", "ok": "yes", "seconds": 1.0},
                                            "step"],
                              "features": ["kinematics", "secret_sauce", ["animation"]]})
        [message] = handed
        self.assertEqual(message["kind"], "count")
        telemetry.counted(message)  # what the daemon does with it, on its accept thread (server.serve)
        telemetry.counted({"crashes": [{"where": "command", "type": "TypeError", "handled": False, "frames": [],
                                        "message": "a secret"}]})  # a crash it would not have made: dropped
        self.assertEqual(self.events(), [
            {"name": "feature", "feature": "kinematics", "count": 1},
            {"name": "snapshot", "kind": "step", "count": 1, "failed": 0, "seconds": 1.5},
            {"name": "snapshot", "kind": "stl", "count": 1, "failed": 1, "seconds": 0.5},
            {"name": "snapshot_failure", "kind": "stl", "reason": "other", "count": 1},  # an older command's: no reason
        ])

    def test_a_hand_over_never_starts_a_daemon_nor_waits_on_one(self) -> None:
        with mock.patch.object(client, "_spawn_daemon") as spawn, \
                mock.patch.dict(os.environ, {"CADGEN_DAEMON_SOCKET": str(self.tmp / "none.sock")}):
            client.hand_over({"snapshots": []})  # none running: nothing to tell
        spawn.assert_not_called()
        hang = threading.Event()
        self.addCleanup(hang.set)
        with mock.patch.object(client, "daemon_supported", return_value=True), \
                mock.patch.object(client, "_connect", side_effect=lambda address: hang.wait(30)):
            began = time.monotonic()
            client.hand_over({"snapshots": []})  # one that never answers is given up on
            self.assertLess(time.monotonic() - began, client.HAND_OVER_SECONDS + 1)
        for environment in ({"DO_NOT_TRACK": "1"}, {"CADGEN_DAEMON": "0"}):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment), \
                    mock.patch.object(client, "daemon_supported", return_value=True), \
                    mock.patch.object(client, "_connect") as connect:
                client.hand_over({"snapshots": []})
            connect.assert_not_called()

    def test_with_no_daemon_a_commands_counts_wait_for_the_next_process_that_sends(self) -> None:
        settings, kept = self.tmp / "settings.json", self.tmp / analytics.SPOOL
        counts = {"snapshots": [{"format": "step", "ok": True, "seconds": 1.5}], "features": ["drawing"]}
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON": "0"}), mock.patch.object(client, "_connect") as connect:
            client.hand_over(counts)  # the daemon turned off: never asked
        connect.assert_not_called()
        with mock.patch.object(client, "daemon_supported", return_value=True), \
                mock.patch.object(client, "_connect", side_effect=ConnectionRefusedError):
            client.hand_over({"features": ["kinematics"]})  # none running
            client.hand_over({"snapshots": []})  # nothing counted: nothing kept
        self.assertEqual(len(kept.read_text(encoding="utf-8").splitlines()), 2)
        # Any process that sends takes them all, once, and the file with them.
        self.assertEqual(self.events(), [
            {"name": "feature", "feature": "drawing", "count": 1},
            {"name": "feature", "feature": "kinematics", "count": 1},
            {"name": "snapshot", "kind": "step", "count": 1, "failed": 0, "seconds": 1.5},
        ])
        self.assertFalse(kept.exists())
        # What was kept under another answer is dropped there, and a no deletes what is kept at once.
        self.assertTrue(analytics.spool(counts, path=settings))
        with mock.patch("cadgen.analytics.time.time", return_value=time.time() + 60):
            analytics.choose(True, by="cli", path=settings)  # a later yes: another answer
        self.assertFalse(self.recorder.flush())
        self.assertTrue(analytics.spool(counts, path=settings))
        analytics.choose(False, by="cli", path=settings, forget=lambda id: True)
        self.assertFalse(kept.exists())
        self.assertFalse(analytics.spool(counts, path=settings), "nothing is kept while sharing is off")
        # Past its size, nothing more is kept.
        analytics.choose(True, by="cli", path=settings)
        with mock.patch.object(analytics, "SPOOL_BYTES", 200):
            self.assertTrue(analytics.spool(counts, path=settings))
            self.assertFalse(analytics.spool(counts, path=settings))

    def test_a_build_no_daemon_answered_is_counted_where_it_ran(self) -> None:
        handed: list[dict] = []
        with mock.patch.object(client, "hand_over", side_effect=handed.append):
            def assembly() -> int:
                telemetry.job_child()
                telemetry.job_reused(False)
                # A build inside it is its own work, not another build.
                self.assertEqual(telemetry.cold_build("step", "script", lambda: 0), 0)
                return 0

            def current() -> int:
                telemetry.job_reused(True)
                return 0

            def interrupted() -> int:
                raise KeyboardInterrupt

            self.assertEqual(telemetry.cold_build("step", "script", assembly, meshes=True), 0)
            self.assertEqual(telemetry.cold_build("stl", "command", current), 0)
            self.assertEqual(telemetry.cold_build("dxf", "script", lambda: 1), 1)
            with self.assertRaises(KeyboardInterrupt):
                telemetry.cold_build("step", "script", interrupted)
            with mock.patch.dict(os.environ, {"CADGEN_DAEMON_CHILD": "1"}):
                telemetry.cold_build("step", "script", lambda: 0)  # a daemon worker's job: the daemon counts it
            with mock.patch.dict(os.environ, {"DO_NOT_TRACK": "1"}):
                telemetry.cold_build("step", "script", lambda: 0)
        self.assertFalse(telemetry.building())
        self.assertEqual([(build["kind"], build["via"], build["outcome"], build["cached"])
                          for counts in handed for build in counts["builds"]],
                         [("step", "script", "ok", False), ("stl", "command", "ok", True), ("dxf", "script", "failed", False),
                          ("step", "script", "cancelled", False)])
        self.assertEqual(handed[0]["features"], ["assembly", "declared_mesh"])
        for counts in handed:
            telemetry.counted(counts)  # what a running daemon, or the next sender, does with them
        builds = [event for event in self.events() if event["name"] == "build"]
        self.assertEqual([(event["kind"], event["via"], event["count"], event["failed"], event["cancelled"], event["cached"])
                          for event in builds],
                         [("dxf", "script", 1, 1, 0, 0), ("step", "script", 2, 0, 1, 0), ("stl", "command", 1, 0, 0, 1)])

    def test_why_a_build_failed_is_decided_where_it_failed_with_a_daemon_or_without(self) -> None:
        from cadgen._internal.cli_from_function import report_failure

        def model() -> None:
            raise ValueError("the secret part did not fit")

        def failing() -> int:  # a model script's run: its failure ends in the one failure envelope
            try:
                exec(compile("model()", "/home/someone/secret_plate.py", "exec"), {"model": model})  # noqa: S102
            except ValueError as error:
                return report_failure(error, prog="python secret_plate.py", as_json=True, stdout=io.StringIO())
            return 0

        # In a build worker: decided there, it rides the job's exit frame, and the daemon counts it.
        frames = []
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_CHILD": "1"}):
            for run in (failing, lambda: 2, lambda: 1):  # its own failure; arguments refused; one nothing named
                telemetry.job_started()
                telemetry.job_ended(run())
                frames.append(telemetry.job_finished())
        self.assertEqual(frames, [{"failure": "model_error"}, {"failure": "arguments"}, {}])
        for index, frame in enumerate(frames):
            build = telemetry.build(RUN, {"id": f"e:job-{index}", "outputs": ["/w/plate.step"]})
            telemetry.exited({"exit": 1, **frame}, build)
            build.finish(1, None, 1.0)
        # With none: decided where it ran, and handed over with the build.
        handed: list[dict] = []

        def escaped() -> int:
            raise RuntimeError("past every report")

        with mock.patch.object(client, "hand_over", side_effect=handed.append):
            telemetry.cold_build("step", "script", failing)
            telemetry.cold_build("stl", "command", lambda: 2)
            with self.assertRaises(RuntimeError):
                telemetry.cold_build("stl", "command", escaped)
            telemetry.cold_build("dxf", "script", lambda: 1)
            telemetry.cold_build("dxf", "script", lambda: 0)
        self.assertEqual([build.get("reason") for counts in handed for build in counts["builds"]],
                         ["model_error", "arguments", "bug", "other", None])
        for counts in handed:
            telemetry.counted(counts)
        failures = {(event["kind"], event["via"], event["reason"]): event["count"] for event in self.events()
                    if event["name"] == "build_failure"}
        self.assertEqual(failures, {("step", "script", "model_error"): 2, ("step", "script", "arguments"): 1,
                                    ("step", "script", "other"): 1, ("stl", "command", "arguments"): 1,
                                    ("stl", "command", "bug"): 1, ("dxf", "script", "other"): 1})
        self.assertNotIn("secret", json.dumps(self.sent))

    def test_why_a_snapshot_failed_is_decided_as_it_failed(self) -> None:
        import asyncio

        from cadgen.snapshot_cli import run_snapshot
        from cadgen.snapshot_core import launch_with_browser

        handed: list[dict] = []
        options = SnapshotOptions(input=str(self.tmp / "secret.step"), output=str(self.tmp / "a.png"))
        with mock.patch.object(client, "hand_over", side_effect=handed.append):
            for kinds in (("step",), ("step",), ("stl",)):  # not there; not STEP; a door that takes no STEP
                with self.assertRaises(Exception):
                    run_snapshot(options, kinds=kinds)
                (self.tmp / "secret.step").write_text("not STEP at all", encoding="utf-8")
        self.assertEqual([counts["snapshots"][0]["reason"] for counts in handed], ["no_file", "input_error", "bad_request"])
        self.assertNotIn("secret", json.dumps(handed))

        # A browser that will not start, even once fixed: named where it is launched, whatever it says.
        async def launch() -> None:
            raise RuntimeError("Executable doesn't exist at /secret")

        error = None
        try:
            asyncio.run(launch_with_browser(launch, fix=lambda problem: None))
        except RuntimeError as failed:
            error = failed
        self.assertEqual(analytics.snapshot_failure(error, "render_error"), "browser")

    def test_a_snapshot_counts_each_documents_format_and_the_features_it_used(self) -> None:
        handed: list[dict] = []
        options = SnapshotOptions(input="/w/arm.step", output="/w/arm.png", joint_values_specified=True)
        files = tuple(SnapshotFile(path=Path(f"/w/{index}.png"), kind="png", input=name)
                      for index, name in enumerate(("/w/arm.step", "/w/arm.step", "/w/base.STL")))
        with mock.patch.object(client, "hand_over", side_effect=handed.append):
            _count_snapshot(options, SnapshotResult(ok=True, files=files), 3.0)
            # It raised: what it was asked to render failed, for why the error says.
            _count_snapshot(options, None, 1.0, FileNotFoundError("/w/arm.step"))
            _count_snapshot(options, SnapshotResult(ok=False, files=()), 1.0)  # rendered, and said it failed
            _count_snapshot(SnapshotOptions(job="/w/job.json"), None, 1.0)  # a packet it never read names nothing
            with mock.patch.object(client, "hand_over", side_effect=RuntimeError("broken")):
                _count_snapshot(options, None, 1.0)  # never fails the snapshot it counts
        self.assertEqual([sorted(snapshot["format"] for snapshot in counts["snapshots"]) for counts in handed],
                         [["step", "stl"], ["step"], ["step"]])
        self.assertEqual([(snapshot["ok"], snapshot["seconds"]) for snapshot in handed[0]["snapshots"]], [(True, 1.5), (True, 1.5)])
        self.assertEqual(handed[1]["snapshots"], [{"format": "step", "ok": False, "seconds": 1.0, "reason": "no_file"}])
        self.assertEqual(handed[2]["snapshots"], [{"format": "step", "ok": False, "seconds": 1.0, "reason": "render_error"}])
        self.assertEqual(handed[0]["features"], ["kinematics"])
        self.assertNotIn("/w/", json.dumps(handed))

    def test_each_batch_takes_the_pools_new_counts_and_the_last_goes_as_the_daemon_stops(self) -> None:
        stats = {"imports": 2, "recycles": 0, "memoryRefusals": 0, "crashes": 5}
        with mock.patch.object(telemetry, "_RECORDER", None):
            telemetry.start(lambda: dict(stats))
            recorder = telemetry._RECORDER
            recorder._send = lambda payload: self.sent.append(payload) or True
            self.assertTrue(recorder.flush())
            stats.update(imports=3, recycles=1, memoryRefusals=2, crashes=9)
            telemetry.close()  # its last batch is kept for the next process to send
            self.assertIsNone(telemetry._RECORDER)
            self.assertEqual(len(self.sent), 1)
        analytics.Recorder(path=self.tmp / "settings.json", send=lambda payload: self.sent.append(payload) or True).send_kept()
        # The pool's own crash count is never read here: crashes are counted as each job ends.
        self.assertEqual([payload["events"] for payload in self.sent], [
            [{"name": "health", "workers": 2, "crashes": 0, "recycles": 0, "refusals": 0}],
            [{"name": "health", "workers": 1, "crashes": 0, "recycles": 1, "refusals": 2}],
        ])
        self.assertEqual({payload["process"] for payload in self.sent}, {"daemon"})


if __name__ == "__main__":
    unittest.main()
