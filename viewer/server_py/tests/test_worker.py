"""Tests for the persistent warm-OCCT CAD worker and its client.

Two tiers:
* OCP-free (always run): the worker's JSON-RPC protocol/dispatch logic in-process,
  and the client's real-subprocess lifecycle (spawn / respawn-on-crash / recycle /
  disabled-fallback) driven through OCP-free ``ping``.
* OCP integration (skipped without OpenCASCADE): a real build through the worker
  subprocess, asserting warm builds match a cold subprocess byte-for-byte on the
  recorded source closure (the warm-determinism guarantee).
"""

import importlib
import io
import json
import os
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from server_py import cadgen_bridge, worker, worker_client  # noqa: E402

_WORKTREE = pathlib.Path(__file__).resolve().parents[3]
_FIXTURE = _WORKTREE / "models/step/parts/basic_shape_mating_test_fixture.step.py"
_LOGICAL_STEP = _WORKTREE / "models/step/parts/basic_shape_mating_test_fixture.step"
_DESCRIPTOR = (
    _WORKTREE
    / "models/step/parts/__cadgen__/models/basic_shape_mating_test_fixture.step.py/assembly.json"
)


def _ocp_available() -> bool:
    if not (_WORKTREE / "packages/cadgen/src").is_dir():
        return False
    sys.path.insert(0, str(_WORKTREE / "packages/cadgen/src"))
    try:
        importlib.import_module("OCP")
        importlib.import_module("cadgen.step_artifact_cli")
        return True
    except Exception:
        return False


class WorkerProtocol(unittest.TestCase):
    """Drive worker.serve() in-process with a stub dispatch — no OCP, no subprocess."""

    def _run(self, requests):
        frames = []
        original_dispatch = worker._DISPATCH
        original_write = worker._write
        worker._DISPATCH = {
            "test.echo": lambda args, reset_runtime_closure=False: {
                "ok": True,
                "args": list(args),
                "reset": reset_runtime_closure,
            },
            "test.boom": lambda args, reset_runtime_closure=False: (_ for _ in ()).throw(
                RuntimeError("kaboom")
            ),
        }
        worker._write = frames.append  # capture frames instead of writing to fd
        try:
            stdin = io.StringIO("".join(json.dumps(r) + "\n" for r in requests))
            worker.serve(stdin)
        finally:
            worker._DISPATCH = original_dispatch
            worker._write = original_write
        return frames

    def test_ping(self):
        [frame] = self._run([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        self.assertEqual(frame["id"], 1)
        self.assertTrue(frame["result"]["ok"])
        self.assertEqual(frame["result"]["pid"], os.getpid())

    def test_invoke_routes_and_passes_reset_true(self):
        [frame] = self._run(
            [{"jsonrpc": "2.0", "id": 7, "method": "invoke",
              "params": {"module": "test.echo", "args": ["--x", "1"], "repo_root": ""}}]
        )
        self.assertEqual(frame["result"], {"ok": True, "args": ["--x", "1"], "reset": True})

    def test_invoke_unknown_module_is_failure_dict(self):
        [frame] = self._run(
            [{"jsonrpc": "2.0", "id": 2, "method": "invoke", "params": {"module": "cadgen.nope"}}]
        )
        self.assertFalse(frame["result"]["ok"])
        self.assertIn("Unknown cadgen module", frame["result"]["error"])

    def test_invoke_core_exception_is_failure_dict_not_protocol_error(self):
        [frame] = self._run(
            [{"jsonrpc": "2.0", "id": 3, "method": "invoke", "params": {"module": "test.boom"}}]
        )
        self.assertNotIn("error", frame)  # NOT a JSON-RPC protocol error
        self.assertFalse(frame["result"]["ok"])
        self.assertEqual(frame["result"]["error"], "kaboom")
        self.assertIn("traceback", frame["result"])

    def test_unknown_method_is_protocol_error(self):
        [frame] = self._run([{"jsonrpc": "2.0", "id": 4, "method": "bogus"}])
        self.assertEqual(frame["error"]["code"], worker.METHOD_NOT_FOUND)

    def test_bad_json_is_parse_error(self):
        frames = self._run([])  # serve handles raw lines; feed a bad line directly
        stdin = io.StringIO("{not json\n")
        captured = []
        ow = worker._write
        worker._write = captured.append
        try:
            worker.serve(stdin)
        finally:
            worker._write = ow
        self.assertEqual(captured[0]["error"]["code"], worker.PARSE_ERROR)

    def test_shutdown_stops_the_loop(self):
        frames = self._run(
            [{"jsonrpc": "2.0", "id": 5, "method": "shutdown"},
             {"jsonrpc": "2.0", "id": 6, "method": "ping"}]
        )
        self.assertEqual(len(frames), 1)  # ping after shutdown is never processed
        self.assertEqual(frames[0]["id"], 5)


class ClientLifecycle(unittest.TestCase):
    """Real worker subprocess, exercised OCP-free through ping()."""

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("VIEWER_CAD_WORKER", "VIEWER_CAD_WORKER_RECYCLE")}
        os.environ["VIEWER_CAD_WORKER"] = "1"
        os.environ.pop("VIEWER_CAD_WORKER_RECYCLE", None)
        self.client = worker_client.CadWorker()

    def tearDown(self):
        self.client.close()
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_spawns_and_pings(self):
        res = self.client.ping(str(_WORKTREE))
        self.assertTrue(res["ok"])
        self.assertIsInstance(res["pid"], int)

    def test_respawns_after_crash(self):
        pid1 = self.client.ping(str(_WORKTREE))["pid"]
        self.client._proc.kill()  # simulate an OCP segfault
        self.client._proc.wait()
        pid2 = self.client.ping(str(_WORKTREE))["pid"]  # transport fault -> respawn
        self.assertNotEqual(pid1, pid2)

    def test_recycles_to_bound_memory(self):
        os.environ["VIEWER_CAD_WORKER_RECYCLE"] = "1"
        pid1 = self.client.ping(str(_WORKTREE))["pid"]
        pid2 = self.client.ping(str(_WORKTREE))["pid"]  # invokes>=1 -> reap before send
        self.assertNotEqual(pid1, pid2)

    def test_disabled_raises_for_cold_fallback(self):
        os.environ["VIEWER_CAD_WORKER"] = "0"
        with self.assertRaises(worker_client._WorkerError):
            worker_client.run_cadgen("cadgen.step_artifact_cli", [], str(_WORKTREE))


@unittest.skipUnless(_ocp_available(), "OpenCASCADE / cadgen not importable")
class WorkerBuildIntegration(unittest.TestCase):
    """End-to-end: build the mating fixture through the warm worker subprocess and
    assert it matches a cold subprocess on the recorded source closure."""

    def setUp(self):
        os.environ["VIEWER_CAD_WORKER"] = "1"
        self.client = worker_client.CadWorker()

    def tearDown(self):
        self.client.close()

    def _build_args(self):
        return [
            "--repo-root", str(_WORKTREE),
            "--step", str(_LOGICAL_STEP),
            "--source-path", str(_FIXTURE),
            "--force",
        ]

    def _closure(self):
        data = json.loads(_DESCRIPTOR.read_text())
        return (data.get("sourceClosureHash"), tuple(data.get("sourceClosureFiles") or ()))

    def test_warm_builds_match_cold(self):
        cold = cadgen_bridge.run_cadgen_cold("cadgen.step_artifact_cli", self._build_args(), str(_WORKTREE))
        self.assertTrue(cold.get("ok"), cold)
        cold_closure = self._closure()

        warm1 = self.client.run_cadgen("cadgen.step_artifact_cli", self._build_args(), str(_WORKTREE))
        self.assertTrue(warm1.get("ok"), warm1)
        self.assertTrue(warm1.get("packagePath"))
        w1 = self._closure()

        warm2 = self.client.run_cadgen("cadgen.step_artifact_cli", self._build_args(), str(_WORKTREE))
        self.assertTrue(warm2.get("ok"), warm2)
        w2 = self._closure()

        # Model files only — the running runtime (cadgen, launchers) is excluded from
        # closures — and identical across cold/warm1/warm2.
        self.assertEqual(len(cold_closure[1]), 1, cold_closure)
        self.assertNotIn("cadgen", "".join(cold_closure[1]), cold_closure)
        self.assertEqual(w1, cold_closure)
        self.assertEqual(w2, cold_closure)


if __name__ == "__main__":
    unittest.main()
