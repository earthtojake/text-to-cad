"""Typed artifact work preserves source isolation, exact pins and broker leases."""
from __future__ import annotations

import concurrent.futures
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import types
import unittest
from unittest import mock

from cadgen.daemon import artifacts, broker, client, server, transport, worker
from cadgen.daemon.jobs import JobLedger
from tests.python.support.tmp_root import generated_cad_directory


PRODUCER = {"scheme": 19, "surfFormat": 2, "build123d": "0.10", "ocp": "7.9.3.1", "cadqueryOcp": "7.9.3.1.1"}


def surface_request(**changes):
    request = {"kind": "surfaces", "tree": "a" * 64, "cids": ["b" * 16, "c" * 16],
               "producer": dict(PRODUCER), "expected_objects": {"d" * 64: "e" * 64}, "force": False}
    request.update(changes)
    return request


class Connection:
    def __init__(self, frames=()):
        self.frames = []
        self.incoming = iter(frames)
        self.closed = False
        self.disconnected = threading.Event()

    def send(self, raw):
        if self.disconnected.is_set():
            raise OSError("client left")
        self.frames.append(json.loads(raw))

    def recv(self, timeout=None):
        if self.disconnected.is_set():
            return b""
        return next(self.incoming, None)

    def close(self):
        self.closed = True


class ResultWorker:
    pid = 999
    extra = False

    def __init__(self, *, fail=False, no_result=False):
        self.ready, self.finish = threading.Event(), threading.Event()
        self.killed = False
        self.fail, self.no_result = fail, no_result

    def send(self, request):
        self.request = request

    def alive(self):
        return not self.killed

    def kill(self):
        self.killed = True
        self.finish.set()

    def frames(self, **kwargs):
        if not self.no_result:
            yield {"artifactResult": artifacts.result_frame(self.request["artifact"], {"producer": PRODUCER})}
        self.ready.set()
        if not self.finish.wait(5):
            raise AssertionError("test did not release worker")
        if self.fail:
            yield {"stream": "stderr", "data": "RuntimeError: native derivation failed\n"}
        yield {"exit": 1 if self.fail else 0}


class ArtifactRequests(unittest.TestCase):
    def test_closed_requests_are_owned_sorted_and_include_every_pin_in_the_key(self):
        request = surface_request(cids=["c" * 16, "b" * 16])
        normalized = artifacts.normalize_request(request)
        key = artifacts.request_key(request)
        self.assertEqual(normalized["cids"], ["b" * 16, "c" * 16])
        self.assertEqual(key, artifacts.request_key(surface_request()))
        request["producer"]["ocp"] = "changed"
        request["expected_objects"]["d" * 64] = "f" * 64
        self.assertEqual(normalized, surface_request())
        for change in ({"tree": "f" * 64}, {"cids": ["b" * 16]}, {"producer": {**PRODUCER, "ocp": "new"}},
                       {"producer": {**PRODUCER, "cadqueryOcp": "other"}}, {"force": True},
                       {"expected_objects": {"d" * 64: "f" * 64}}, {"expected_objects": {"f" * 64: "e" * 64}}):
            with self.subTest(change=change):
                self.assertNotEqual(key, artifacts.request_key(surface_request(**change)))

    def test_unknown_fields_bad_pins_versions_and_nonboolean_force_fail_before_dispatch(self):
        invalid = [{"kind": "producer", "path": "source.py"}, {"kind": "compile"},
                   surface_request(script="model.py"), surface_request(tree="part.step"),
                   surface_request(cids=["B" * 16]), surface_request(cids=["b" * 16] * 2),
                   surface_request(force=1), surface_request(expected_objects={"short": "e" * 64}),
                   surface_request(producer={**PRODUCER, "ocp": "unknown"}),
                   surface_request(producer={**PRODUCER, "scheme": True})]
        with mock.patch.object(client, "run_artifact") as dispatch:
            for request in invalid:
                with self.subTest(request=request), self.assertRaises(ValueError):
                    artifacts.submit_artifact(request)
            dispatch.assert_not_called()

    def test_importing_artifact_client_supervisor_and_worker_is_kernel_free(self):
        script = """import sys
from cadgen.daemon import artifacts, client, server, worker
assert not any(k == 'OCP' or k.startswith('OCP.') or k == 'build123d' or k.startswith('build123d.') for k in sys.modules)
assert 'cadgen.store.surfaces' not in sys.modules
print('kernel-free')
"""
        result = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("kernel-free", result.stdout)

    def test_result_is_exactly_bound_and_has_no_native_or_mutable_alias(self):
        request = surface_request()
        value = {"components": ["b" * 16]}
        payload = artifacts.result_frame(request, value)
        value["components"].append("not retained")
        self.assertEqual(artifacts.validate_result(request, payload), {"components": ["b" * 16]})
        with self.assertRaises(artifacts.ArtifactJobError):
            artifacts.validate_result(surface_request(force=True), payload)
        with self.assertRaises(TypeError):
            artifacts.result_frame(request, object())
        with self.assertRaises(ValueError):
            artifacts.result_frame(request, float("nan"))

    def test_ledger_never_parses_source_or_advertises_declared_outputs(self):
        ledger = JobLedger()
        with mock.patch("cadgen.daemon.jobs.declared_outputs", side_effect=AssertionError("source scan")):
            job = ledger.start_artifact(surface_request(), store_root="/store/a", root_id="root", dependency=True)
            legacy = ledger.start(tool="artifact", subject="/readable/source.py", argv=[])
        self.assertEqual(job["outputs"], [])
        self.assertEqual(legacy["subject"], "")
        self.assertFalse(job["editingProducer"])
        self.assertTrue(job["dependency"])
        self.assertEqual(job["rootId"], "root")
        ledger.record_artifact_result(job, {"result": {"x": 1}})
        ledger.finish(job, 0)
        self.assertEqual(ledger.snapshot()[0]["artifactResult"]["result"], {"x": 1})


class ArtifactCoalescing(unittest.TestCase):
    def test_disconnect_before_claim_reply_retires_owner_and_attached_consumer(self):
        registry = broker.Broker(1)
        request = {"kind": "inflight", "op": "claim", "artifact": surface_request(), "store_root": "/store"}
        gone = Connection()
        gone.disconnected.set()
        registry.handle(gone, request)
        self.assertEqual(registry.snapshot()["inflight"], 0)
        _, owner = registry.claim_artifact_entry(surface_request(), store_root="/store")
        with self.assertRaises(OSError):
            registry.handle(gone, request)
        self.assertEqual(owner["consumers"], 0)
        self.assertFalse(registry.abandon(owner))
        self.assertEqual(registry.snapshot()["inflight"], 0)

    def test_typed_coalescing_separates_store_and_every_input_and_retires_by_owner(self):
        registry = broker.Broker(1)
        owned, first = registry.claim_artifact_entry(surface_request(), store_root="/store/a")
        self.assertTrue(owned)
        owned, attached = registry.claim_artifact_entry(surface_request(cids=["c" * 16, "b" * 16]), store_root="/store/a")
        self.assertFalse(owned)
        self.assertIs(attached, first)
        for store, request in (("/store/b", surface_request()), ("/store/a", surface_request(force=True)),
                               ("/store/a", surface_request(expected_objects={})),
                               ("/store/a", surface_request(producer={**PRODUCER, "ocp": "other"}))):
            owns, entry = registry.claim_artifact_entry(request, store_root=store)
            self.assertTrue(owns)
            registry.finish_entry(entry, 0)
        self.assertTrue(registry.abandon(first), "an attached consumer preserves the producer")
        registry.detach(attached)
        self.assertTrue(registry.orphaned(first))
        owned, replacement = registry.claim_artifact_entry(surface_request(), store_root="/store/a")
        self.assertTrue(owned)
        registry.finish_entry(first, 1)
        self.assertFalse(registry.claim_artifact_entry(surface_request(), store_root="/store/a")[0])
        registry.finish_entry(replacement, 0)
        self.assertEqual(registry.snapshot()["inflight"], 0)

    def exercise_relay(self, *, fail=False):
        registry, ledger = broker.Broker(1), JobLedger()
        running = ResultWorker(fail=fail)
        pool = mock.Mock()
        pool.acquire.return_value = running
        request = {"tool": "artifact", "argv": [], "artifact": surface_request(), "store_root": "/store/a",
                   "root_id": "root", "dependency": True, "cwd": "/unrelated/source"}
        first, second = Connection(), Connection()
        with contextlib.ExitStack() as stack:
            for name, value in (("_BROKER", registry), ("_JOBS", ledger), ("_POOL", pool)):
                stack.enter_context(mock.patch.object(server, name, value))
            for name in ("_script_path", "_document_path"):
                stack.enter_context(mock.patch.object(server, name, side_effect=AssertionError("source/document lookup")))
            stack.enter_context(mock.patch("cadgen.daemon.jobs.declared_outputs", side_effect=AssertionError("source read")))
            stack.enter_context(mock.patch.object(server, "_log"))
            stack.enter_context(mock.patch.object(server, "_watch_client"))
            executor = stack.enter_context(concurrent.futures.ThreadPoolExecutor(2))
            owner = executor.submit(server._handle_request, first, request)
            self.assertTrue(running.ready.wait(3))
            follower = executor.submit(server._handle_request, second, request)
            deadline = time.monotonic() + 3
            while not any("artifactResult" in frame for frame in second.frames) and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(any("artifactResult" in frame for frame in second.frames))
            self.assertFalse(follower.done(), "result does not replace eventual completion")
            running.finish.set()
            owner.result(5)
            follower.result(5)
        pool.acquire.assert_called_once_with("", dependency=True)
        pool.release.assert_called_once_with(running, healthy=True)
        self.assertEqual(running.request["kind"], "artifact")
        self.assertEqual(running.request["argv"], [])
        self.assertEqual(first.frames[-1], {"exit": int(fail)})
        self.assertEqual(second.frames[-1], {"exit": int(fail)})
        results = ledger.snapshot()
        self.assertEqual(len(results), 2)
        for job in results:
            self.assertEqual(job["subject"], "")
            self.assertEqual(job["outputs"], [])
            self.assertFalse(job["editingProducer"])
            self.assertIn("artifactResult", job)
        self.assertEqual(registry.snapshot()["inflight"], 0)

    def test_late_attached_client_receives_result_and_then_completion(self):
        self.exercise_relay()

    def test_producer_failure_is_not_hidden_by_an_earlier_result(self):
        self.exercise_relay(fail=True)

    def test_admission_failure_finishes_coalescing_without_starting_work(self):
        registry, ledger, pool = broker.Broker(1), JobLedger(), mock.Mock()
        pool.acquire.side_effect = server.pool_mod.MemoryAdmissionError("memory admission refused")
        connection = Connection()
        with mock.patch.object(server, "_BROKER", registry), mock.patch.object(server, "_JOBS", ledger), \
             mock.patch.object(server, "_POOL", pool), mock.patch.object(server, "_log"):
            server._handle_request(connection, {"tool": "artifact", "argv": [], "artifact": {"kind": "producer"}, "store_root": "/store"})
        self.assertEqual(connection.frames[-1], {"exit": 1})
        self.assertEqual(registry.snapshot()["inflight"], 0)
        self.assertEqual(ledger.snapshot()[0]["state"], "failed")
        pool.release.assert_not_called()

    def test_invalid_typed_request_never_routes_or_admits(self):
        pool = mock.Mock()
        with mock.patch.object(server, "_POOL", pool), \
             mock.patch.object(server, "_script_path", side_effect=AssertionError("source parse")):
            for changes in ({"argv": ["model.py"]}, {"store_root": ""}, {"artifact": {"kind": "producer", "source": "x.py"}}):
                connection = Connection()
                request = {"tool": "artifact", "argv": [], "artifact": {"kind": "producer"}, "store_root": "/store", **changes}
                server._handle_request(connection, request)
                self.assertEqual(connection.frames[-1], {"exit": 1})
        pool.acquire.assert_not_called()


class ArtifactTransport(unittest.TestCase):
    def payload(self):
        return {"tool": "artifact", "argv": [], "artifact": {"kind": "producer"}, "store_root": "/store"}

    def test_protocol_loss_failure_and_missing_result_never_retry_cold(self):
        for frames, reason in (
            ([], "closed the connection"),
            ([{"exit": 0}], "completed without returning"),
            ([{"exit": 1}], "exit 1"),
            ([{"event": {"sourceResult": {"tree": "wrong"}}}], "build update instead"),
            ([{"unexpected": 1}], "invalid response"),
        ):
            raw = [json.dumps(frame).encode() for frame in frames] + [b""]
            conn = Connection(raw)
            with self.subTest(frames=frames), mock.patch.object(client, "_connect_or_spawn", return_value=conn) as connect, \
                 mock.patch("cadgen.daemon.artifacts._run_transient", side_effect=AssertionError("cold retry")):
                with self.assertRaisesRegex(artifacts.ArtifactJobError, reason):
                    client.run_artifact(self.payload())
                self.assertEqual(connect.call_count, 1)
                self.assertTrue(conn.closed)

    def test_rejected_key_fails_immediately_without_spawning_over_live_service(self):
        with mock.patch.object(transport, "read_authkey", return_value=b"test-key"), \
             mock.patch.object(transport.mpc, "Client", side_effect=transport.mpc.AuthenticationError("rejected")), \
             mock.patch.object(client, "_spawn_daemon") as spawn, \
             mock.patch.object(transport, "spawn_lock") as election:
            with self.assertRaisesRegex(artifacts.ArtifactJobError, "connection key"):
                client.run_artifact(self.payload())
            self.assertIsNone(client._run_with_retry({"tool": "run", "argv": []}),
                              "ordinary source requests keep their pre-submission fallback")
        spawn.assert_not_called()
        election.assert_not_called()

    def test_silent_geometry_service_reports_the_timeout(self):
        with mock.patch.object(client, "_connect_or_spawn", return_value=Connection()), \
             mock.patch.object(client, "_recv_json", return_value=client._TIMED_OUT), \
             mock.patch.object(client, "request_timeout", return_value=1), \
             mock.patch.object(client.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(artifacts.ArtifactJobError, "stopped responding for 1 seconds"):
                client.run_artifact(self.payload())

    def test_restart_is_allowed_only_before_observed_work(self):
        result = {"artifactResult": artifacts.result_frame({"kind": "producer"}, PRODUCER)}
        conn = Connection([json.dumps(result).encode(), b'{"restart":true}'])
        with mock.patch.object(client, "_connect_or_spawn", return_value=conn) as connect:
            with self.assertRaises(artifacts.ArtifactJobError):
                client.run_artifact(self.payload())
            self.assertEqual(connect.call_count, 1)

    def test_result_then_exit_returns_only_the_typed_value(self):
        result = {"artifactResult": artifacts.result_frame({"kind": "producer"}, PRODUCER)}
        conn = Connection([json.dumps(result).encode(), b'{"exit":0}'])
        with mock.patch.object(client, "_connect_or_spawn", return_value=conn):
            self.assertEqual(client.run_artifact(self.payload()), PRODUCER)


class ArtifactStartup(unittest.TestCase):
    def setUp(self):
        temp = generated_cad_directory(prefix="artifact-startup-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.enterContext(mock.patch.dict(os.environ, {
            "CADGEN_DAEMON": "1", "CADGEN_DAEMON_SPARES": "0",
            "CADGEN_DAEMON_STATE_DIR": str(self.root / "state"),
            "CADGEN_CACHE_DIR": str(self.root / "store"),
        }))

    @unittest.skipIf(os.name == "nt", "Windows named pipes do not have the Unix socket path limit")
    def test_actual_overlong_socket_startup_fails_future_once_without_cold_retry(self):
        address = str(self.root / ("long-" * 30) / "daemon.sock")
        processes = []
        spawn = client._spawn_daemon

        def recorded_spawn(selected):
            process = spawn(selected)
            if process is not None:
                processes.append(process)
            return process

        future = None
        try:
            with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SOCKET": address}), \
                 mock.patch.object(client, "_spawn_daemon", side_effect=recorded_spawn) as launched, \
                 mock.patch.object(artifacts, "_run_transient", side_effect=AssertionError("unaccounted cold retry")), \
                 mock.patch.object(artifacts, "execute", side_effect=AssertionError("native work in caller")):
                future = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root / "store")
                with self.assertRaisesRegex(artifacts.ArtifactJobError, "geometry service could not accept"):
                    future.result(timeout=10)
                self.assertTrue(future.done())
                self.assertEqual(launched.call_count, 1)
                self.assertEqual(len(processes), 1)
                # The server also uses exit 0 when it stands down before bind;
                # only a successful connection/result can satisfy the client.
                processes[0].wait(timeout=5)
                self.assertIsNotNone(processes[0].poll())
                self.assertIn("AF_UNIX path too long", client.log_path(address).read_text(encoding="utf-8"))
                self.assertFalse((self.root / "store" / "index").exists())
        finally:
            if future is not None:
                future.detach()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)

    def test_a_nonspawner_deadline_is_terminal_without_respawn_or_cold_retry(self):
        from cadgen.daemon import transport

        address = transport.private_address("artifact-startup-" + str(os.getpid()))
        election = transport.spawn_lock(address)
        self.assertTrue(election.acquire())
        self.addCleanup(election.release)
        with mock.patch.dict(os.environ, {"CADGEN_DAEMON_SOCKET": address}), \
             mock.patch.object(client, "SPAWN_WAIT_SECONDS", 0.1), \
             mock.patch.object(client, "_spawn_daemon", side_effect=AssertionError("second spawner")) as spawn, \
             mock.patch.object(artifacts, "_run_transient", side_effect=AssertionError("unaccounted cold retry")):
            future = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root / "store")
            try:
                with self.assertRaisesRegex(artifacts.ArtifactJobError, "geometry service could not accept"):
                    future.result(timeout=3)
                self.assertTrue(future.done())
                spawn.assert_not_called()
                self.assertFalse((self.root / "store" / "index").exists())
            finally:
                future.detach()


class ArtifactLeases(unittest.TestCase):
    def setUp(self):
        self.private = broker.PrivateBroker(1)
        self.addCleanup(self.private.close)
        temp = generated_cad_directory(prefix="artifact-jobs-")
        self.addCleanup(temp.cleanup)
        self.root = str(Path(temp.name).resolve())
        env = mock.patch.dict(os.environ, {**self.private.env(), "CADGEN_CACHE_DIR": self.root, "CADGEN_DAEMON": "0"})
        env.start()
        self.addCleanup(env.stop)
        self.fake = types.ModuleType("cadgen.store.surfaces")
        self.fake.producer_identity = mock.Mock(return_value=dict(PRODUCER))
        self.fake.derive = mock.Mock(return_value={"components": ["b" * 16]})
        import cadgen.store

        stack = self.enterContext(contextlib.ExitStack())
        stack.enter_context(mock.patch.dict(sys.modules, {"cadgen.store.surfaces": self.fake}))
        stack.enter_context(mock.patch.object(cadgen.store, "surfaces", self.fake, create=True))

    def settled(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            snapshot = self.private.broker.snapshot()
            if not snapshot["running"] and not snapshot["queued"] and not snapshot["inflight"]:
                return snapshot
            time.sleep(.005)
        self.fail(f"leaked accounting: {snapshot}")

    def test_matching_accounted_worker_executes_inline_under_the_same_one_slot(self):
        with broker.held("parent", required=True), artifacts.worker_context(self.root), \
             mock.patch.object(client, "run_artifact", side_effect=AssertionError("nested dispatch")):
            before = self.private.broker.snapshot()["granted"]
            self.assertEqual(artifacts.resolve_artifact({"kind": "producer"}, store_root=self.root), PRODUCER)
            self.assertEqual(artifacts.resolve_artifact(surface_request(), store_root=self.root), {"components": ["b" * 16]})
            self.assertEqual(self.private.broker.snapshot()["granted"], before)
            self.assertEqual(self.private.broker.snapshot()["running"], 1)
        self.assertEqual(self.settled()["peakRunning"], 1)
        self.fake.derive.assert_called_once_with("a" * 64, ["b" * 16, "c" * 16], producer=PRODUCER,
                                               expected_objects={"d" * 64: "e" * 64}, force=False)

    def test_worker_source_isolation_and_failure_release_real_lease(self):
        readable = Path(self.root) / "unrelated.py"
        readable.write_text("raise AssertionError('must not be read')\n", encoding="utf-8")
        frames = []
        original_open = open

        def guard(path, *args, **kwargs):
            if isinstance(path, (str, os.PathLike)) and str(path).endswith("unrelated.py"):
                raise AssertionError("unrelated source read")
            return original_open(path, *args, **kwargs)

        request = {"tool": "artifact", "argv": [], "artifact": surface_request(), "store_root": self.root,
                   "cwd": self.root, "env": {}}
        with mock.patch.object(worker, "_emit", side_effect=frames.append), mock.patch("builtins.open", side_effect=guard), \
             mock.patch.object(worker, "_evict_first_party_modules", side_effect=AssertionError("source hygiene scan")), \
             mock.patch("cadgen.metadata.parse_generator_metadata", side_effect=AssertionError("source metadata")):
            self.assertEqual(worker._run(request), 0)
            self.fake.derive.side_effect = RuntimeError("surface producer failed")
            self.assertEqual(worker._run(request), 1)
        self.assertEqual(sum("artifactResult" in frame for frame in frames), 1)
        self.assertEqual(self.settled()["granted"], 2)
        self.assertIsNone(getattr(artifacts._WORKER, "root", None))

    def test_nested_wait_yields_and_reacquires_one_slot(self):
        finished = artifacts.ArtifactFuture()
        entered = threading.Event()

        def child():
            with broker.held("child", required=True):
                entered.set()
                finished.set_result({"ok": True})

        with broker.held("parent", required=True):
            thread = threading.Thread(target=child)
            thread.start()
            self.assertEqual(finished.result(3), {"ok": True})
            self.assertTrue(entered.is_set())
            self.assertEqual(self.private.broker.snapshot()["running"], 1)
        thread.join(3)
        snapshot = self.settled()
        self.assertEqual(snapshot["peakRunning"], 1)
        self.assertEqual(snapshot["granted"], 3)

    def test_different_store_and_other_thread_never_borrow_the_parent_native_lease(self):
        endpoint = (self.private.address, self.private.key)
        calls = []

        def dispatch(request, root, env, selected_endpoint, **kwargs):
            calls.append(root)
            with broker.held("dispatched", required=True, endpoint=endpoint):
                return {"root": root}

        with mock.patch.object(artifacts, "_run_transient", side_effect=dispatch):
            with broker.held("parent", required=True), artifacts.worker_context(self.root):
                other_root = str(Path(self.root) / "other")
                self.assertEqual(artifacts.resolve_artifact({"kind": "producer"}, store_root=other_root), {"root": other_root})
                holder = []
                thread = threading.Thread(target=lambda: holder.append(artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)))
                thread.start(); thread.join(3)
                self.assertEqual(holder[0].result(3), {"root": self.root})
        self.assertEqual(calls, [other_root, self.root])
        self.assertEqual(self.settled()["peakRunning"], 1)

    def test_missing_or_malformed_required_broker_does_not_execute(self):
        request = {"tool": "artifact", "argv": [], "artifact": {"kind": "producer"}, "store_root": self.root}
        frames = []
        for connection in (None, Connection([b'{"error":"refused"}'])):
            with mock.patch.object(broker, "_open", return_value=connection), mock.patch.object(worker, "_emit", side_effect=frames.append):
                self.assertEqual(worker._run(request), 1)
        self.fake.producer_identity.assert_not_called()
        self.assertFalse(any("artifactResult" in frame for frame in frames))

    def test_transient_broker_claim_retains_typed_result_for_late_clients(self):
        endpoint = (self.private.address, self.private.key)
        request = surface_request()
        owner = broker.claim_artifact(request, store_root=self.root, endpoint=endpoint)
        payload = artifacts.result_frame(request, {"complete": True})
        broker.report_artifact_result(owner[1], payload)
        attached = broker.claim_artifact(request, store_root=self.root, endpoint=endpoint)
        self.assertEqual((owner[0], attached[0]), ("yours", "attached"))
        values, ready = [], threading.Event()
        exits = []

        def receive(value):
            values.append(value)
            ready.set()

        thread = threading.Thread(target=lambda: exits.append(broker.wait_attached(attached[1], on_artifact_result=receive)))
        thread.start()
        self.assertTrue(ready.wait(3))
        self.assertEqual(values, [payload])
        self.assertEqual(exits, [])
        broker.report_done(owner[1], 0)
        thread.join(3)
        self.assertEqual(exits, [0])
        self.settled()

    def test_future_result_does_not_expose_mutable_retained_value(self):
        result = artifacts.ArtifactFuture()
        result.set_result({"items": [1]})
        result.result()["items"].append(2)
        self.assertEqual(result.result(), {"items": [1]})

    def test_actual_transient_worker_uses_explicit_broker_env_and_coalesces(self):
        entered, release = Path(self.root) / "entered", Path(self.root) / "release"
        # Inject only the future store module in a real child. The actual typed
        # stdin entry, request environment, lease, native-import seam and result
        # protocol all run unchanged; no source model or fake document is used.
        script = f"""import json,os,sys,time,types
from pathlib import Path
from cadgen.daemon import artifacts,broker
module=types.ModuleType('cadgen.store.surfaces')
def identity():
    assert broker.current_lease() is not None
    assert artifacts._WORKER.root == artifacts.store_path()
    Path({str(entered)!r}).write_text('entered')
    deadline=time.monotonic()+5
    while not Path({str(release)!r}).exists():
        if time.monotonic()>deadline: raise RuntimeError('test barrier')
        time.sleep(.005)
    return {PRODUCER!r}
module.producer_identity=identity
sys.modules[module.__name__]=module
raise SystemExit(artifacts._main())
"""
        real_popen = subprocess.Popen
        spawned = []

        def start(argv, **kwargs):
            self.assertEqual(argv, [sys.executable, "-m", "cadgen.daemon.artifacts"])
            spawned.append(dict(kwargs["env"]))
            return real_popen([sys.executable, "-c", script], **kwargs)

        with mock.patch.object(artifacts.subprocess, "Popen", side_effect=start):
            first = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            deadline = time.monotonic() + 3
            while not entered.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(entered.exists())
            second = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            deadline = time.monotonic() + 3
            while self.private.broker.snapshot()["coalesced"] < 1 and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertEqual(self.private.broker.snapshot()["coalesced"], 1)
            release.write_text("go", encoding="utf-8")
            self.assertEqual(first.result(5), PRODUCER)
            self.assertEqual(second.result(5), PRODUCER)
        self.assertEqual(len(spawned), 1)
        self.assertEqual(spawned[0][broker.BROKER_ADDRESS_VAR], self.private.address)
        self.assertEqual(spawned[0]["CADGEN_CACHE_DIR"], self.root)
        self.assertEqual(self.settled()["peakRunning"], 1)

    def test_concurrent_transient_roots_share_owned_broker_without_global_env_mutation(self):
        entered, release = Path(self.root) / "entered-owned", Path(self.root) / "release-owned"
        script = f"""import os,sys,time,types
from pathlib import Path
from cadgen.daemon import artifacts,broker
module=types.ModuleType('cadgen.store.surfaces')
def identity():
    assert broker.current_lease() is not None
    Path({str(entered)!r}).write_text('entered')
    deadline=time.monotonic()+5
    while not Path({str(release)!r}).exists():
        if time.monotonic()>deadline: raise RuntimeError('test barrier')
        time.sleep(.005)
    return {{'store': artifacts.store_path()}}
module.producer_identity=identity
sys.modules[module.__name__]=module
raise SystemExit(artifacts._main())
"""
        real_popen = subprocess.Popen
        spawned, children = [], []

        def start(argv, **kwargs):
            spawned.append(dict(kwargs["env"]))
            process = real_popen([sys.executable, "-c", script], **kwargs)
            children.append(process)
            return process

        with mock.patch.dict(os.environ, {broker.BROKER_ADDRESS_VAR: "", broker.BROKER_KEY_VAR: "", "CADGEN_JOBS": "1"}), \
             mock.patch.object(artifacts.subprocess, "Popen", side_effect=start):
            first = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            second_root = str(Path(self.root) / "second")
            second = artifacts.submit_artifact({"kind": "producer"}, store_root=second_root)
            owned = artifacts._PRIVATE
            self.assertIsNotNone(owned)
            deadline = time.monotonic() + 3
            while (not entered.exists() or owned.broker.snapshot()["queued"] != 1) and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(entered.exists())
            self.assertEqual(owned.broker.snapshot()["queued"], 1)
            self.assertEqual(os.environ[broker.BROKER_ADDRESS_VAR], "")
            self.assertEqual(os.environ[broker.BROKER_KEY_VAR], "")
            release.write_text("go", encoding="utf-8")
            self.assertEqual(first.result(5), {"store": self.root})
            self.assertEqual(second.result(5), {"store": second_root})
            deadline = time.monotonic() + 3
            while artifacts._PRIVATE is not None and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertIsNone(artifacts._PRIVATE)
            self.assertEqual(artifacts._PRIVATE_USERS, 0)
            self.assertEqual(os.environ[broker.BROKER_ADDRESS_VAR], "")
        self.assertEqual({env["CADGEN_CACHE_DIR"] for env in spawned}, {self.root, second_root})
        self.assertEqual(len({env[broker.BROKER_ADDRESS_VAR] for env in spawned}), 1)
        self.assertTrue(all(child.poll() == 0 for child in children))
        self.assertEqual(owned.broker.snapshot()["peakRunning"], 1)

    def test_failed_transient_spawn_retires_claim_and_never_computes_locally(self):
        with mock.patch.object(artifacts.subprocess, "Popen", side_effect=OSError("cannot spawn")):
            future = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            with self.assertRaisesRegex(OSError, "cannot spawn"):
                future.result(3)
        self.fake.producer_identity.assert_not_called()
        self.settled()

    def exercise_transient_detach(self, *, detach_last):
        entered, release = Path(self.root) / "detach-entered", Path(self.root) / "detach-release"
        script = f"""import sys,time,types
from pathlib import Path
from cadgen.daemon import artifacts,broker
module=types.ModuleType('cadgen.store.surfaces')
def identity():
    assert broker.current_lease() is not None
    Path({str(entered)!r}).write_text('entered')
    deadline=time.monotonic()+5
    while not Path({str(release)!r}).exists():
        if time.monotonic()>deadline: raise RuntimeError('test barrier')
        time.sleep(.005)
    return {PRODUCER!r}
module.producer_identity=identity
sys.modules[module.__name__]=module
raise SystemExit(artifacts._main())
"""
        real_popen = subprocess.Popen
        processes = []

        def start(argv, **kwargs):
            process = real_popen([sys.executable, "-c", script], **kwargs)
            processes.append(process)
            return process

        with mock.patch.object(artifacts.subprocess, "Popen", side_effect=start):
            first = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            deadline = time.monotonic() + 3
            while not entered.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(entered.exists())
            second = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            deadline = time.monotonic() + 3
            while self.private.broker.snapshot()["coalesced"] != 1 and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertEqual(self.private.broker.snapshot()["coalesced"], 1)
            self.assertTrue(first.detach())
            self.assertFalse(first.detach())
            with self.assertRaises(artifacts.ArtifactDetached):
                first.result()
            deadline = time.monotonic() + 3
            entry = next(iter(self.private.broker._inflight.values()))
            while entry["ownerActive"] and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertFalse(entry["ownerActive"])
            self.assertEqual(entry["consumers"], 1)
            self.assertIsNone(processes[0].poll(), "detaching the producer subscriber killed useful work")
            if detach_last:
                self.assertTrue(second.detach())
                with self.assertRaises(artifacts.ArtifactDetached):
                    second.result()
            else:
                release.write_text("go", encoding="utf-8")
                self.assertEqual(second.result(5), PRODUCER)
            deadline = time.monotonic() + 4
            while any(process.poll() is None for process in processes) and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertTrue(all(process.poll() is not None for process in processes))
        self.assertEqual(len(processes), 1)
        if not detach_last:
            self.assertEqual(processes[0].returncode, 0)
        self.assertEqual(self.settled()["peakRunning"], 1)

    def test_transient_owner_detach_preserves_real_child_for_other_subscriber(self):
        self.exercise_transient_detach(detach_last=False)

    def test_transient_last_detach_terminates_only_orphaned_child_and_releases_slot(self):
        self.exercise_transient_detach(detach_last=True)

    def test_daemon_transport_detach_preserves_coalesced_work(self):
        from cadgen.daemon import transport

        address = transport.private_address(transport.identity_digest(self.root + "artifact-server"))
        listener = transport.Server(address, self.private.key, backlog=4)
        self.addCleanup(listener.close)
        self.addCleanup(transport.clear_address, address)

        class LeasedWorker(ResultWorker):
            def frames(inner, **kwargs):
                with broker.held("artifact producer", required=True):
                    yield from super().frames(**kwargs)

        running, ledger, pool = LeasedWorker(), JobLedger(), mock.Mock()
        pool.acquire.return_value = running
        handlers = []

        def serve_two():
            for _ in range(2):
                connection = listener.accept()
                if connection is None:
                    return
                def handle(conn=connection):
                    try:
                        request = server._read_request(conn)
                        server._handle_request(conn, request)
                    finally:
                        conn.close()
                thread = threading.Thread(target=handle, daemon=True)
                handlers.append(thread)
                thread.start()

        with mock.patch.object(server, "_BROKER", self.private.broker), mock.patch.object(server, "_JOBS", ledger), \
             mock.patch.object(server, "_POOL", pool), mock.patch.object(server, "_log"), \
             mock.patch.object(client, "_connect_or_spawn", side_effect=lambda _: transport.connect(address, self.private.key)), \
             mock.patch("cadgen.daemon.executors.use_daemon", return_value=True):
            acceptor = threading.Thread(target=serve_two, daemon=True)
            acceptor.start()
            first = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            self.assertTrue(running.ready.wait(3))
            second = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            deadline = time.monotonic() + 3
            while self.private.broker.snapshot()["coalesced"] != 1 and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertEqual(self.private.broker.snapshot()["coalesced"], 1)
            entry = next(iter(self.private.broker._inflight.values()))
            self.assertTrue(first.detach())
            with self.assertRaises(artifacts.ArtifactDetached):
                first.result()
            deadline = time.monotonic() + 3
            while entry["ownerActive"] and time.monotonic() < deadline:
                time.sleep(.005)
            self.assertFalse(entry["ownerActive"])
            self.assertFalse(running.killed)
            running.finish.set()
            self.assertEqual(second.result(5), {"producer": PRODUCER})
            acceptor.join(3)
            for handler in handlers:
                handler.join(3)
            self.assertTrue(all(not handler.is_alive() for handler in handlers))
        pool.acquire.assert_called_once_with("", dependency=False)
        self.assertFalse(running.killed)
        self.assertEqual(self.settled()["peakRunning"], 1)


if __name__ == "__main__":
    unittest.main()
