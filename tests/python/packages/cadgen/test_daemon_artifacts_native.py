"""Tiny native integration for the source-free artifact transport boundary."""
from __future__ import annotations

import contextlib
import copy
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

from cadgen.daemon import artifacts, broker, client, pool, server, transport
from cadgen.daemon.jobs import JobLedger
from cadgen.daemon.memory import MemoryPolicy, MIB
from tests.python.support.tmp_root import generated_cad_directory


class NativeArtifactTransport(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="native-artifact-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = str(self.root / "store")
        self.private = broker.PrivateBroker(1)
        self.addCleanup(self.private.close)
        self.enterContext(mock.patch.dict(os.environ, {
            **self.private.env(), "CADGEN_CACHE_DIR": self.store,
            "CADGEN_DAEMON": "0", "CADGEN_JOBS": "1",
            "CADGEN_DAEMON_SPARES": "1", "CADGEN_COMPONENT_WORKERS": "1",
        }))
        from build123d import Solid
        from cadgen.store import surfaces
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.trees import capture_tree

        box = Solid.make_box(2, 3, 4)
        box.cad_face_ordinal_colors = {1: (0.1, 0.3, 0.8, 1.0)}
        self.tree, self.descriptor, _ = build_tree_from_compound(box, root_name="colored box")
        self.geometry = capture_tree(self.tree)[1]
        self.producer = surfaces.producer_identity()
        self.request = {
            "kind": "surfaces", "tree": self.tree,
            "cids": sorted(self.descriptor["components"]), "producer": self.producer,
        }
        self.source = self.root / "unrelated.py"
        self.source.write_text("raise AssertionError('artifact jobs must not read this source')\n", encoding="utf-8")
        self.audit_violation = self.root / "source-read-attempt"

    def wait_for(self, predicate, message, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(predicate(), message() if callable(message) else message)

    @staticmethod
    def stop_process(process):
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    def settled(self):
        def idle():
            snapshot = self.private.broker.snapshot()
            return not any(snapshot[key] for key in ("running", "queued", "inflight"))
        self.wait_for(idle, str(self.private.broker.snapshot()))
        self.assertEqual(self.private.broker.snapshot()["peakRunning"], 1)

    def source_guard(self):
        # Record the attempt before raising, so a catch-all source scanner could
        # not make this isolation assertion pass by suppressing the audit error.
        return f"""import os,sys
from pathlib import Path
forbidden={str(self.source)!r}
violation={str(self.audit_violation)!r}
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)) and os.fsdecode(args[0])==forbidden:
        Path(violation).write_text('attempted')
        raise AssertionError('artifact source read')
sys.addaudithook(audit)
"""

    def assert_geometry_and_result(self, result):
        from cadgen.store import surfaces
        from cadgen.store.objects import read_verified_object
        from cadgen.store.trees import capture_tree

        self.assertEqual(set(result), set(self.request["cids"]))
        for cid, record in result.items():
            self.assertEqual(record["producer"], self.producer)
            self.assertEqual(record["surfaceInput"], surfaces.surface_input(self.descriptor["components"][cid], self.producer))
            self.assertEqual(record["component"], self.descriptor["components"][cid]["contentHash"])
            self.assertEqual(record["brep"], self.descriptor["components"][cid]["brep"])
            index = surfaces.validate_surface_bytes(read_verified_object(record["object"]))
            self.assertEqual(index["counts"]["faces"], 6)
        self.assertEqual(capture_tree(self.tree)[1], self.geometry)
        self.assertFalse(self.audit_violation.exists())
        self.assertFalse((Path(self.store) / "index/model").exists())
        self.assertFalse((Path(self.store) / "index/document").exists())

    @contextlib.contextmanager
    def daemon(self, child_prelude):
        address = transport.private_address(transport.identity_digest(str(self.root) + "native-server"))
        listener = transport.Server(address, self.private.key, backlog=8)
        workers = pool.Pool(policy=MemoryPolicy(limit_bytes=1024 * MIB, seed_bytes=1024 * MIB))
        ledger, handlers = JobLedger(), []
        processes = []
        original_popen = subprocess.Popen

        def start(argv, **kwargs):
            if argv == [sys.executable, "-m", "cadgen.daemon.worker"]:
                process = original_popen([sys.executable, "-c", child_prelude + "\nfrom cadgen.daemon import worker\nraise SystemExit(worker.serve())\n"], **kwargs)
                processes.append(process)
                return process
            return original_popen(argv, **kwargs)

        def accept():
            while True:
                connection = listener.accept()
                if connection is None:
                    return
                def handle(conn=connection):
                    try:
                        server._handle_request(conn, server._read_request(conn))
                    finally:
                        conn.close()
                handler = threading.Thread(target=handle, daemon=True)
                handlers.append(handler)
                handler.start()

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(server, "_BROKER", self.private.broker))
            stack.enter_context(mock.patch.object(server, "_JOBS", ledger))
            stack.enter_context(mock.patch.object(server, "_POOL", workers))
            stack.enter_context(mock.patch.object(server, "_log"))
            stack.enter_context(mock.patch.object(client, "_connect_or_spawn", side_effect=lambda _: transport.connect(address, self.private.key)))
            stack.enter_context(mock.patch("cadgen.daemon.executors.use_daemon", return_value=True))
            stack.enter_context(mock.patch.object(pool.subprocess, "Popen", side_effect=start))
            stack.enter_context(mock.patch.object(artifacts, "_run_transient", side_effect=AssertionError("unaccounted fallback")))
            for name in ("_script_path", "_document_path"):
                stack.enter_context(mock.patch.object(server, name, side_effect=AssertionError("source/document routing")))
            stack.enter_context(mock.patch("cadgen.daemon.jobs.declared_outputs", side_effect=AssertionError("source scan")))
            acceptor = threading.Thread(target=accept, daemon=True)
            acceptor.start()
            try:
                yield workers, ledger, processes
            finally:
                listener.close()
                acceptor.join(5)
                workers.shutdown()
                for handler in handlers:
                    handler.join(5)
                transport.clear_address(address)
                self.assertFalse(acceptor.is_alive())
                self.assertFalse(any(handler.is_alive() for handler in handlers))
                self.assertTrue(all(process.poll() is not None for process in processes))

    def test_real_daemon_native_surface_pins_errors_and_nested_one_slot(self):
        nested = self.root / "nested-native"
        prelude = self.source_guard() + f"""
from cadgen.daemon import artifacts,broker
from cadgen.store import surfaces
original_derive=surfaces.derive
def derive(*args,**kwargs):
    lease=broker.current_lease()
    assert lease is not None
    nested=artifacts.resolve_artifact({{'kind':'producer'}},store_root=artifacts.store_path())
    assert nested==surfaces.producer_identity() and broker.current_lease() is lease
    Path({str(nested)!r}).write_text('completed under same lease')
    return original_derive(*args,**kwargs)
surfaces.derive=derive
"""
        with self.daemon(prelude) as (workers, ledger, processes):
            self.assertEqual(artifacts.submit_artifact({"kind": "producer"}, store_root=self.store).result(20), self.producer)
            result = artifacts.submit_artifact(self.request, store_root=self.store).result(20)
            self.assert_geometry_and_result(result)
            expected = {row["surfaceInput"]: row["object"] for row in result.values()}
            self.assertEqual(artifacts.submit_artifact({**self.request, "expected_objects": expected, "force": True}, store_root=self.store).result(20), result)
            self.assertTrue(nested.exists())
            for changes, message in (
                ({"producer": {**self.producer, "ocp": "different-known-runtime"}}, "pinned surface producer"),
                ({"cids": ["0" * 16]}, "unpinned component"),
                ({"expected_objects": {key: "0" * 64 for key in expected}, "force": True}, "producer conflict"),
            ):
                with self.subTest(changes=changes), self.assertRaisesRegex(artifacts.ArtifactJobError, message):
                    artifacts.submit_artifact({**self.request, **changes}, store_root=self.store).result(20)
            self.assert_geometry_and_result(result)
            self.settled()
            self.assertEqual(len(processes), 1)
            self.assertTrue(all(row["model"] == "" for row in workers.snapshot()["workers"]))
            jobs = ledger.snapshot()
            self.assertEqual(len(jobs), 6)
            self.assertTrue(all(row["subject"] == "" and row["outputs"] == [] and not row["editingProducer"] for row in jobs))
            self.assertEqual(sum(row["state"] == "failed" for row in jobs), 3)
            self.assertEqual(self.private.broker.snapshot()["granted"], 6, "inline nested native identity acquired an extra slot")

    def test_real_transient_surface_keeps_coalesced_native_work_after_owner_detach(self):
        entered = self.root / "native-entered"
        release = self.root / "native-release"
        derived = self.root / "native-derived"
        script = self.source_guard() + f"""
import time
import build123d
from cadgen._internal import component_package,surface_extract
from cadgen.daemon import artifacts,broker
from cadgen.store import surfaces
original=surfaces.derive
def derive(*args,**kwargs):
    assert broker.current_lease() is not None
    Path({str(entered)!r}).write_text('entered')
    deadline=time.monotonic()+15
    while not Path({str(release)!r}).exists():
        if time.monotonic()>deadline: raise RuntimeError('test barrier')
        time.sleep(.005)
    result=original(*args,**kwargs)
    Path({str(derived)!r}).write_text('derived')
    return result
surfaces.derive=derive
raise SystemExit(artifacts._main())
"""
        original_popen, processes = subprocess.Popen, []

        def start(argv, **kwargs):
            self.assertEqual(argv, [sys.executable, "-m", "cadgen.daemon.artifacts"])
            process = original_popen([sys.executable, "-c", script], **kwargs)
            processes.append(process)
            self.addCleanup(self.stop_process, process)
            return process

        with mock.patch.object(artifacts.subprocess, "Popen", side_effect=start):
            first = artifacts.submit_artifact(self.request, store_root=self.store)
            self.addCleanup(first.detach)
            self.wait_for(
                lambda: entered.exists() or first.done(),
                lambda: "native worker did not acquire its lease after cold native startup: "
                f"child={processes[0].poll() if processes else 'not started'}, "
                f"broker={self.private.broker.snapshot()}, future_done={first.done()}",
                timeout=60,
            )
            if not entered.exists():
                first.result()
                self.fail("native worker completed without entering the guarded derivation")
            second = artifacts.submit_artifact(copy.deepcopy(self.request), store_root=self.store)
            self.addCleanup(second.detach)
            self.wait_for(lambda: self.private.broker.snapshot()["coalesced"] == 1, "second subscriber did not attach")
            self.assertTrue(first.detach())
            with self.assertRaises(artifacts.ArtifactDetached):
                first.result()
            self.assertIsNone(processes[0].poll())
            release.write_text("continue", encoding="utf-8")

            # The entered marker is deliberately emitted after the child's lazy native
            # imports. This test owns the detach/result handoff, not a cold OCP
            # startup benchmark. Separate real surface derivation from broker
            # delivery so a failure names the stalled phase and its live state.
            self.wait_for(
                lambda: derived.exists() or second.done(),
                lambda: "native surface derivation did not finish after owner detach: "
                f"child={processes[0].poll()}, broker={self.private.broker.snapshot()}, "
                f"future_done={second.done()}",
                timeout=60,
            )
            if not derived.exists():
                second.result()
                self.fail("native artifact completed without the guarded derivation marker")
            self.wait_for(
                second.done,
                lambda: "derived native surface was not delivered to its attached subscriber: "
                f"child={processes[0].poll()}, broker={self.private.broker.snapshot()}",
            )
            result = second.result()
            self.assert_geometry_and_result(result)
            self.wait_for(lambda: all(process.poll() is not None for process in processes), "native child remained alive")
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes[0].returncode, 0)
        self.settled()

    def test_real_daemon_detach_retains_native_worker_for_attached_subscriber(self):
        entered, release = self.root / "daemon-entered", self.root / "daemon-release"
        prelude = self.source_guard() + f"""
import time
from cadgen.store import surfaces
original=surfaces.derive
def derive(*args,**kwargs):
    Path({str(entered)!r}).write_text('entered')
    deadline=time.monotonic()+15
    while not Path({str(release)!r}).exists():
        if time.monotonic()>deadline: raise RuntimeError('test barrier')
        time.sleep(.005)
    return original(*args,**kwargs)
surfaces.derive=derive
"""
        with self.daemon(prelude) as (workers, ledger, processes):
            first = artifacts.submit_artifact(self.request, store_root=self.store)
            self.addCleanup(first.detach)
            # This first job includes cold native imports. Ownership assertions
            # begin at the operation barrier, independently of startup speed.
            self.wait_for(
                lambda: entered.exists() or first.done(),
                lambda: f"daemon native operation did not begin: broker={self.private.broker.snapshot()}",
                timeout=60,
            )
            if not entered.exists():
                first.result()
                self.fail("native artifact finished without entering its operation")
            second = artifacts.submit_artifact(self.request, store_root=self.store)
            self.addCleanup(second.detach)
            self.wait_for(lambda: self.private.broker.snapshot()["coalesced"] == 1, "daemon subscriber did not attach")
            self.assertTrue(first.detach())
            with self.assertRaises(artifacts.ArtifactDetached):
                first.result()
            self.assertIsNone(processes[0].poll())
            release.write_text("continue", encoding="utf-8")
            self.assert_geometry_and_result(second.result(20))
            self.settled()
            self.assertEqual(self.private.broker.snapshot()["granted"], 1)
            self.assertEqual(len(processes), 1)
            self.assertEqual(workers.snapshot()["imports"], 1)
            self.assertTrue(all(row["outputs"] == [] and not row["editingProducer"] for row in ledger.snapshot()))


if __name__ == "__main__":
    unittest.main()
