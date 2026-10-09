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

from cadgen.daemon import artifacts, broker, client, executors, pool, server, transport, worker
from cadgen.daemon.jobs import JobLedger
from tests.python.support.tmp_root import generated_cad_directory


PRODUCER = {"scheme": 20, "surfFormat": 3, "build123d": "0.10", "ocp": "7.9.3.1", "cadqueryOcp": "7.9.3.1.1"}


def surface_request(**changes):
    request = {"kind": "surfaces", "tree": "a" * 64, "cids": ["b" * 16, "c" * 16],
               "producer": dict(PRODUCER), "expected_objects": {"d" * 64: "e" * 64}, "force": False}
    request.update(changes)
    return request


def done(value):
    future = concurrent.futures.Future()
    future.set_result(value)
    return future


def noticing_log():
    """A stand-in for the supervisor's ``_log``, and the event it sets once the supervisor
    notices a client leave -- whatever it then does: let the job finish, keep it for
    coalesced consumers, or kill the worker."""
    noticed = threading.Event()

    def log(message):
        if "client left" in message or "disconnected" in message:
            noticed.set()

    return log, noticed


class Connection:
    def __init__(self, frames=()):
        self.frames = []
        self.incoming = iter(frames)
        self.closed = False
        self.disconnected = threading.Event()
        self.sent = threading.Condition()

    def send(self, raw):
        if self.disconnected.is_set():
            raise OSError("client left")
        with self.sent:
            self.frames.append(json.loads(raw))
            self.sent.notify_all()

    def first_frame(self):
        """The first frame sent to this client, once one has been."""
        with self.sent:
            self.sent.wait_for(lambda: self.frames)
            return self.frames[0]

    def frame_with(self, key):
        """The first frame sent to this client that carries ``key``, once one has been."""
        with self.sent:
            self.sent.wait_for(lambda: any(key in frame for frame in self.frames))
            return next(frame for frame in self.frames if key in frame)

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


class AskingWorker:
    """A job that asks before each of its derivations (worker._wanted), each after a step."""
    pid = 998
    extra = False

    def __init__(self, *steps):
        self.steps, self.answers, self.killed = steps, [], False

    def send(self, request):
        if request.get("kind") == "artifactNext":
            self.answers.append(request["goOn"])
        else:
            self.request = request

    def alive(self):
        return not self.killed

    def kill(self):
        self.killed = True

    def frames(self, **kwargs):
        for step in self.steps:
            step()
            yield {"artifactNext": True}
        yield {"artifactResult": artifacts.result_frame(self.request["artifact"], {})}
        yield {"exit": 0}


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
                       {"expected_objects": {"d" * 64: "f" * 64}}, {"expected_objects": {"f" * 64: "e" * 64}},
                       {"tessellations": [{"chordTolerance": 5e-4, "angleTolerance": 0.35}]}):
            with self.subTest(change=change):
                self.assertNotEqual(key, artifacts.request_key(surface_request(**change)))

    def test_unknown_fields_bad_pins_versions_and_nonboolean_force_fail_before_dispatch(self):
        invalid = [{"kind": "producer", "path": "source.py"}, {"kind": "compile"},
                   surface_request(script="model.py"), surface_request(tree="part.step"),
                   surface_request(cids=["B" * 16]), surface_request(cids=["b" * 16] * 2),
                   surface_request(force=1), surface_request(expected_objects={"short": "e" * 64}),
                   surface_request(producer={**PRODUCER, "ocp": "unknown"}),
                   surface_request(producer={**PRODUCER, "scheme": True}),
                   surface_request(tessellations=[{"chordTolerance": 5e-4}]),
                   surface_request(tessellations=[{"chordTolerance": 1e-9, "angleTolerance": 0.35}])]
        with mock.patch.object(client, "run_artifact") as dispatch:
            for request in invalid:
                with self.subTest(request=request), self.assertRaises(ValueError):
                    artifacts.submit_artifact(request)
            dispatch.assert_not_called()

    def test_a_meshes_request_names_this_cadgens_mesh_keys_once_each_in_one_order(self):
        from cadgen.store.meshes import TESSELLATOR_VERSION, tessellation_key

        keys = [tessellation_key(digit * 64) for digit in "21"]
        self.assertEqual(artifacts.normalize_request({"kind": "meshes", "keys": keys}),
                         {"kind": "meshes", "keys": sorted(keys)})
        self.assertEqual(artifacts.request_key({"kind": "meshes", "keys": keys}),
                         artifacts.request_key({"kind": "meshes", "keys": keys[::-1]}), "an order splits no request")
        older = keys[0].replace(f"-t{TESSELLATOR_VERSION}-", f"-t{TESSELLATOR_VERSION - 1}-")
        crowd = [tessellation_key(f"{n:064x}") for n in range(artifacts.MESH_KEYS_MAX + 1)]
        # Finer than any request may ask to have meshed: refused where it enters, as a
        # surfaces request's tessellations are.
        too_fine = [tessellation_key("3" * 64, 1e-6, 0.35), tessellation_key("3" * 64, 1.5e-3, 1e-3)]
        for request in ({"kind": "meshes"}, {"kind": "meshes", "keys": []}, {"kind": "meshes", "keys": keys * 2},
                        {"kind": "meshes", "keys": keys, "tree": "a" * 64}, {"kind": "meshes", "keys": [older]},
                        {"kind": "meshes", "keys": ["../escape"]}, {"kind": "meshes", "keys": crowd},
                        *({"kind": "meshes", "keys": [*keys, key]} for key in too_fine)):
            with self.subTest(request=request), self.assertRaises(ValueError):
                artifacts.normalize_request(request)

    def test_a_sections_request_names_each_component_cut_once_in_one_canonical_order(self):
        component = {"kind": "native", "codec": "bintools-v4", "brep": "b" * 64, "contentHash": "c" * 64,
                     "faceColors": {}}
        items = [{"component": component, "normal": [0, 0, 2], "offset": 4},
                 {"component": component, "normal": [1, 0, 0], "offset": -1.5}]
        normalized = artifacts.normalize_request({"kind": "sections", "items": items})
        # The plane is the unit normal and the offset along it, as every key and cut uses it.
        self.assertIn({"component": component, "normal": [0.0, 0.0, 1.0], "offset": 2.0}, normalized["items"])
        self.assertEqual(artifacts.request_key({"kind": "sections", "items": items}),
                         artifacts.request_key({"kind": "sections", "items": items[::-1]}), "an order splits no request")
        crowd = [{"component": component, "normal": [0, 0, 1], "offset": n}
                 for n in range(artifacts.SECTION_ITEMS_MAX + 1)]
        for request in ({"kind": "sections"}, {"kind": "sections", "items": []},
                        {"kind": "sections", "items": items * 2}, {"kind": "sections", "items": crowd},
                        {"kind": "sections", "items": items, "tree": "a" * 64},
                        {"kind": "sections", "items": [{**items[0], "normal": [0, 0, 0]}]},
                        {"kind": "sections", "items": [{**items[0], "component": {**component, "script": "x.py"}}]},
                        {"kind": "sections", "items": [{**items[0], "component": {**component, "brep": "../x"}}]}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                artifacts.normalize_request(request)

    def test_work_is_dealt_one_job_per_cpu_slot_and_every_job_ends_before_a_failure_is_raised(self):
        def jobs(count, *, warm, per_started_worker=32, cpus=4):
            with mock.patch.object(executors, "use_daemon", return_value=warm is not None), \
                    mock.patch.object(pool, "spare_count", return_value=warm or 0), \
                    mock.patch.object(broker, "job_limit", return_value=cpus):
                dealt = artifacts.deal(range(count), per_started_worker=per_started_worker)
            self.assertEqual(sorted(item for job in dealt for item in job), list(range(count)), "each item once")
            return [len(job) for job in dealt]

        self.assertEqual(jobs(3, warm=2), [3], "a small model's work stays one job")
        self.assertEqual(jobs(38, warm=2), [19, 19], "the warm workers share it")
        self.assertEqual(jobs(100, warm=2), [34, 33, 33], "a job that starts a worker has 32 items to repay it")
        self.assertEqual(jobs(256, warm=2), [64, 64, 64, 64], "no more jobs than CPU slots")
        self.assertEqual(jobs(38, warm=None), [38], "without a daemon every job starts a worker")
        self.assertEqual(jobs(200, warm=None, per_started_worker=96), [100, 100])
        self.assertEqual(artifacts.deal([], per_started_worker=1), [])

        release = threading.Event()
        started, finished = [], []

        def submit(request, *, store_root=None):
            future = concurrent.futures.Future()
            started.append(request["n"])

            def run():
                if request["n"] == 0:
                    future.set_exception(artifacts.ArtifactJobError("the first job failed"))
                    release.set()
                    return
                release.wait(3)
                finished.append(request["n"])
                future.set_result(request["n"])

            threading.Thread(target=run).start()
            return future

        with mock.patch.object(artifacts, "submit_artifact", side_effect=submit), \
                self.assertRaisesRegex(artifacts.ArtifactJobError, "the first job failed"):
            artifacts.resolve_artifacts([{"n": n} for n in range(3)])
        self.assertEqual(started, [0, 1, 2], "every job is started before any is awaited")
        self.assertEqual(sorted(finished), [1, 2], "the failure waits for the others to finish")
        with mock.patch.object(artifacts, "submit_artifact", side_effect=lambda request, **_: done(request["n"])):
            self.assertEqual(artifacts.resolve_artifacts([{"n": n} for n in range(3)]), [0, 1, 2])

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
            self.assertIn("artifactResult", second.frame_with("artifactResult"))
            self.assertFalse(follower.done(), "result does not replace eventual completion")
            running.finish.set()
            owner.result(5)
            follower.result(5)
        pool.acquire.assert_called_once_with("", dependency=True, on_start=mock.ANY)
        pool.release.assert_called_once_with(running, healthy=True, cancelled=False)
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

    def test_a_cancelled_artifact_request_finishes_on_its_warm_worker(self):
        # The CAD Viewer cancels surface requests as a matter of course. The derivation writes
        # its result into the store, so the worker finishes it rather than being killed (a
        # replacement imports the kernel again), and an identical request meanwhile attaches.
        registry, ledger, pool = broker.Broker(1), JobLedger(), mock.Mock()
        running = ResultWorker()
        pool.acquire.return_value = running
        request = {"tool": "artifact", "argv": [], "artifact": surface_request(), "store_root": "/store/a"}
        cancelled, late = Connection(), Connection()
        log, noticed = noticing_log()
        with mock.patch.object(server, "_BROKER", registry), mock.patch.object(server, "_JOBS", ledger), \
             mock.patch.object(server, "_POOL", pool), mock.patch.object(server, "_log", side_effect=log), \
             mock.patch.object(server, "CLIENT_LIVENESS_INTERVAL_SECONDS", .01), \
             concurrent.futures.ThreadPoolExecutor(2) as executor:
            owner = executor.submit(server._handle_request, cancelled, request)
            self.assertTrue(running.ready.wait(3))
            cancelled.disconnected.set()
            noticed.wait()
            self.assertFalse(running.killed, "a cancelled artifact request killed its warm worker")
            follower = executor.submit(server._handle_request, late, request)
            # An attached consumer's first frame is the job's retained result.
            self.assertIn("artifactResult", late.first_frame(),
                          "an identical request did not attach to the job still running")
            running.finish.set()
            owner.result(5)
            follower.result(5)
        self.assertFalse(running.killed)
        pool.acquire.assert_called_once_with("", dependency=False, on_start=mock.ANY)
        pool.release.assert_called_once_with(running, healthy=True, cancelled=False)
        self.assertEqual(late.frames[-1], {"exit": 0})
        self.assertEqual(sorted(job["state"] for job in ledger.snapshot()), ["done", "done"])
        self.assertEqual(registry.snapshot()["inflight"], 0)

    def test_a_cancelled_artifact_job_stops_before_its_next_derivation(self):
        # Asked before each derivation, the supervisor says go on while the caller listens or
        # an identical request has attached, and stop once neither does: a request the browser
        # left no longer holds its worker for the rest of its components. Nothing is killed.
        registry, ledger, pool = broker.Broker(1), JobLedger(), mock.Mock()
        request = {"tool": "artifact", "argv": [], "artifact": surface_request(), "store_root": "/store/a"}
        owner, other = Connection(), Connection()
        attached, detached = threading.Event(), threading.Event()
        claim, detach = registry.claim_artifact_entry, registry.detach

        def claiming(*args, **kwargs):
            owned, entry = claim(*args, **kwargs)
            if not owned:
                attached.set()
            return owned, entry

        def detaching(entry):
            orphaned = detach(entry)
            detached.set()
            return orphaned

        with mock.patch.object(server, "_BROKER", registry), mock.patch.object(server, "_JOBS", ledger), \
             mock.patch.object(server, "_POOL", pool), mock.patch.object(server, "_log"), \
             mock.patch.object(server, "_watch_client"), \
             mock.patch.object(registry, "claim_artifact_entry", side_effect=claiming), \
             mock.patch.object(registry, "detach", side_effect=detaching), \
             concurrent.futures.ThreadPoolExecutor(1) as executor:
            follower = []

            def owner_leaves_as_another_attaches():
                owner.disconnected.set()
                follower.append(executor.submit(server._handle_request, other, request))
                attached.wait()

            def the_other_leaves():
                other.disconnected.set()
                detached.wait()

            running = AskingWorker(lambda: None, owner_leaves_as_another_attaches, the_other_leaves)
            pool.acquire.return_value = running
            server._handle_request(owner, request)
            follower[0].result()
        self.assertEqual(running.answers, [True, True, False])
        self.assertFalse(running.killed)
        pool.release.assert_called_once_with(running, healthy=True, cancelled=False)
        self.assertEqual(registry.snapshot()["inflight"], 0)

    def test_a_model_build_whose_client_left_is_still_stopped(self):
        class BuildWorker(ResultWorker):
            def frames(inner, **kwargs):
                inner.ready.set()
                if not inner.finish.wait(5):
                    raise AssertionError("test did not release worker")
                yield {"exit": 0}

        ledger, pool, running = JobLedger(), mock.Mock(), BuildWorker()
        pool.acquire.return_value = running
        gone = Connection()
        with mock.patch.object(server, "_JOBS", ledger), mock.patch.object(server, "_POOL", pool), \
             mock.patch.object(server, "_log"), mock.patch.object(server, "CLIENT_LIVENESS_INTERVAL_SECONDS", .01), \
             mock.patch("cadgen.daemon.jobs.declared_outputs", return_value=[]), \
             concurrent.futures.ThreadPoolExecutor(1) as executor:
            build = executor.submit(server._handle_request, gone, {"tool": "run", "argv": ["/project/model.py"]})
            self.assertTrue(running.ready.wait(3))
            gone.disconnected.set()
            build.result(5)
        self.assertTrue(running.killed, "a stopped build kept running")
        pool.release.assert_called_once_with(running, healthy=False, cancelled=True)

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
                                               expected_objects={"d" * 64: "e" * 64}, force=False,
                                               keep_going=None)

    def test_a_build_does_the_first_share_itself_and_deals_only_what_repays_a_started_worker(self):
        dispatched = []

        def dispatch(request, root):
            dispatched.append((request, root))
            return done({"components": []})

        requests = [surface_request(), surface_request(cids=["f" * 16])]
        with mock.patch.object(executors, "use_daemon", return_value=True), \
                mock.patch.object(pool, "spare_count", return_value=2), \
                mock.patch.object(broker, "job_limit", return_value=4), \
                mock.patch.object(artifacts, "_dispatch", side_effect=dispatch), \
                broker.held("build", required=True), artifacts.worker_context(self.root):
            self.assertEqual([len(share) for share in artifacts.deal(range(40), per_started_worker=32)], [40],
                             "work that repays no started worker stays in the build, though spares are warm")
            self.assertEqual([len(share) for share in artifacts.deal(range(100), per_started_worker=32)],
                             [34, 33, 33])
            results = artifacts.resolve_artifacts(requests, store_root=self.root)
        self.assertEqual(results, [{"components": ["b" * 16]}, {"components": []}])
        self.fake.derive.assert_called_once()
        self.assertEqual(self.fake.derive.call_args.args, ("a" * 64, ["b" * 16, "c" * 16]), "the first share, here")
        self.assertEqual(dispatched, [(artifacts.normalize_request(requests[1]), self.root)], "the rest, to the pool")
        self.assertEqual(self.settled()["peakRunning"], 1)

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
            self.assertEqual(argv, [sys.executable, "-P", "-m", "cadgen.daemon.artifacts"])
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

        log, noticed = noticing_log()
        # The second request joining the first's entry, awaited rather than polled for.
        coalesced, claim = threading.Event(), self.private.broker.claim_artifact_entry

        def claiming(request, **kwargs):
            owned, entry = claim(request, **kwargs)
            if not owned:
                coalesced.set()
            return owned, entry

        with mock.patch.object(server, "_BROKER", self.private.broker), mock.patch.object(server, "_JOBS", ledger), \
             mock.patch.object(server, "_POOL", pool), mock.patch.object(server, "_log", side_effect=log), \
             mock.patch.object(self.private.broker, "claim_artifact_entry", side_effect=claiming), \
             mock.patch.object(client, "_connect_or_spawn", side_effect=lambda _: transport.connect(address, self.private.key)), \
             mock.patch("cadgen.daemon.executors.use_daemon", return_value=True):
            acceptor = threading.Thread(target=serve_two, daemon=True)
            acceptor.start()
            first = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            self.assertTrue(running.ready.wait(3))
            second = artifacts.submit_artifact({"kind": "producer"}, store_root=self.root)
            coalesced.wait()
            self.assertEqual(self.private.broker.snapshot()["coalesced"], 1)
            entry = next(iter(self.private.broker._inflight.values()))
            self.assertTrue(first.detach())
            with self.assertRaises(artifacts.ArtifactDetached):
                first.result()
            # The supervisor notices its client leave, and the worker keeps the job: an
            # artifact job is never killed for its caller, and goes on while another waits.
            noticed.wait()
            self.assertTrue(entry["ownerActive"], "the producing request was abandoned")
            self.assertFalse(running.killed)
            running.finish.set()
            self.assertEqual(second.result(5), {"producer": PRODUCER})
            acceptor.join(3)
            for handler in handlers:
                handler.join(3)
            self.assertTrue(all(not handler.is_alive() for handler in handlers))
        pool.acquire.assert_called_once_with("", dependency=False, on_start=mock.ANY)
        self.assertFalse(running.killed)
        self.assertEqual(self.settled()["peakRunning"], 1)


class SupervisedDerivation(unittest.TestCase):
    def test_a_daemon_job_asks_before_each_derivation_and_ends_at_the_first_no(self):
        # The worker's half of the question the supervisor answers above, on real derivations:
        # told yes then no, the job derives one component and ends with it, exit 0.
        private = broker.PrivateBroker(1)
        self.addCleanup(private.close)
        temp = generated_cad_directory(prefix="artifact-asks-")
        self.addCleanup(temp.cleanup)
        root = str(Path(temp.name).resolve())
        self.enterContext(mock.patch.dict(os.environ, {**private.env(), "CADGEN_CACHE_DIR": root, "CADGEN_DAEMON": "0"}))
        from build123d import Box, Compound, Pos
        from cadgen.store import surfaces
        from cadgen.store.build import build_tree_from_compound

        parts = Compound(children=[Pos(20 * index, 0, 0) * Box(1 + index, 2, 3) for index in range(3)])
        tree, descriptor, _ = build_tree_from_compound(parts, root_name="parts")
        producer, cids = surfaces.producer_identity(), sorted(descriptor["components"])
        request = {"tool": "artifact", "argv": [], "store_root": root,
                   "artifact": {"kind": "surfaces", "tree": tree, "cids": cids, "producer": producer}}
        answers = io.StringIO('{"kind": "artifactNext", "goOn": true}\n{"kind": "artifactNext", "goOn": false}\n')
        frames = []
        with mock.patch.object(worker, "_emit", side_effect=frames.append), mock.patch.object(sys, "stdin", answers):
            self.assertEqual(worker._run(request, supervised=True), 0)
        self.assertEqual(frames[:2], [{"artifactNext": True}] * 2)
        self.assertEqual(list(frames[2]["artifactResult"]["result"]), cids[:1])
        self.assertEqual([surfaces.lookup(descriptor["components"][cid], producer) is not None for cid in cids],
                         [True, False, False])


if __name__ == "__main__":
    unittest.main()
