"""Tiny native integration for the source-free artifact transport boundary."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import subprocess
import threading
import time
import unittest
from unittest import mock

from cadgen.daemon import artifacts, broker, client, pool, server, transport
from cadgen.daemon.jobs import JobLedger
from tests.python.support.broker import PrivateBroker
from cadgen.daemon.memory import MemoryPolicy, MIB
from tests.python.support.tmp_root import generated_cad_directory


class NativeArtifactTransport(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="native-artifact-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = str(self.root / "store")
        self.private = PrivateBroker(1)
        self.addCleanup(self.private.close)
        self.enterContext(self.private.served())
        self.enterContext(mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": self.store, "CADGEN_DAEMON_STATE_DIR": str(self.root / "state"),
            "CADGEN_DAEMON": "0", "CADGEN_JOBS": "1",
            "CADGEN_DAEMON_SPARES": "1", "CADGEN_COMPONENT_WORKERS": "1",
        }))
        from build123d import Solid
        from cadgen.store import parts
        from cadgen.store.build import build_tree_from_compound
        from cadgen.store.trees import capture_tree

        box = Solid.make_box(2, 3, 4)
        box.cad_face_ordinal_colors = {1: (0.1, 0.3, 0.8, 1.0)}
        self.tree, self.descriptor, _ = build_tree_from_compound(box, root_name="colored box")
        self.geometry = capture_tree(self.tree)[1]
        self.producer = parts.producer_identity()
        self.request = {
            "kind": "display", "tree": self.tree,
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
        return self.private.broker.snapshot()

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
        from cadgen.store import meshes, parts
        from cadgen.store.trees import capture_tree

        self.assertEqual(set(result), set(self.request["cids"]))
        for cid, record in result.items():
            key = parts.part_key(self.descriptor["components"][cid], self.producer)
            self.assertEqual(parts.probe(key), record, "the job answers the part it stored")
            self.assertEqual(meshes.body_facts(parts.read(key, "glb"))["part"], key)
            self.assertEqual((record["glb"]["faceCount"], record["selectors"]["faceCount"]), (6, 6))
        self.assertEqual(capture_tree(self.tree)[1], self.geometry)
        self.assertFalse(self.audit_violation.exists())
        self.assertFalse((Path(self.store) / "index/model").exists())
        self.assertFalse((Path(self.store) / "index/document").exists())

    @contextlib.contextmanager
    def daemon(self, child_prelude):
        # The daemon is its workers' broker: they reach it at the address the pool names
        # for them (``CADGEN_DAEMON_SOCKET``) with the key it published.
        address = transport.private_address(transport.identity_digest(str(self.root) + "native-server"))
        transport.publish_authkey(address, self.private.key)
        listener = transport.Server(address, self.private.key, backlog=8)
        workers = pool.Pool(policy=MemoryPolicy(limit_bytes=1024 * MIB, seed_bytes=1024 * MIB))
        ledger, handlers = JobLedger(), []
        processes = []
        original_popen = subprocess.Popen

        def start(argv, **kwargs):
            if argv[-2:] == ["-m", "cadgen.daemon.worker"]:
                process = original_popen([*argv[:-2], "-c", child_prelude + "\nfrom cadgen.daemon import worker\nraise SystemExit(worker.serve())\n"], **kwargs)
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
            stack.enter_context(mock.patch.dict(os.environ, {"CADGEN_DAEMON_SOCKET": address}))
            stack.enter_context(mock.patch.object(server, "_BROKER", self.private.broker))
            stack.enter_context(mock.patch.object(server, "_JOBS", ledger))
            stack.enter_context(mock.patch.object(server, "_POOL", workers))
            stack.enter_context(mock.patch.object(server, "_log"))
            stack.enter_context(mock.patch.object(client, "_connect_or_spawn", side_effect=lambda _: transport.connect(address, self.private.key)))
            stack.enter_context(mock.patch("cadgen.daemon.executors.use_daemon", return_value=True))
            stack.enter_context(mock.patch.object(pool.subprocess, "Popen", side_effect=start))
            stack.enter_context(mock.patch.object(artifacts, "_run_here", side_effect=AssertionError("unaccounted fallback")))
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

    def test_real_daemon_native_display_pins_and_errors(self):
        with self.daemon(self.source_guard()) as (workers, ledger, processes):
            self.assertEqual(artifacts.submit_artifact({"kind": "producer"}, store_root=self.store).result(20), self.producer)
            result = artifacts.submit_artifact(self.request, store_root=self.store).result(20)
            self.assert_geometry_and_result(result)
            for changes, message in (
                ({"producer": {**self.producer, "ocp": "different-known-runtime"}}, "pinned producer"),
                ({"cids": ["0" * 16]}, "unpinned component"),
            ):
                with self.subTest(changes=changes), self.assertRaisesRegex(artifacts.ArtifactJobError, message):
                    artifacts.submit_artifact({**self.request, **changes}, store_root=self.store).result(20)
            self.assert_geometry_and_result(result)
            self.assertEqual(self.settled()["peakRunning"], 1)
            self.assertEqual(len(processes), 1)
            self.assertTrue(all(row["model"] == "" for row in workers.snapshot()["workers"]))
            jobs = ledger.snapshot()
            self.assertEqual(len(jobs), 4)
            self.assertTrue(all(row["subject"] == "" and row["outputs"] == [] for row in jobs))
            self.assertEqual(sum(row["state"] == "failed" for row in jobs), 2)
            self.assertEqual(self.private.broker.snapshot()["granted"], 4, "one slot a job")

    def test_with_no_daemon_a_display_job_derives_in_this_process_on_its_own_thread(self):
        from cadgen.store import parts

        derive, threads, leases = parts.derive, [], []

        def leased(*args, **kwargs):
            threads.append(threading.current_thread())
            leases.append(broker.current_lease())
            return derive(*args, **kwargs)

        with mock.patch.object(subprocess, "Popen", side_effect=AssertionError("a process per job")), \
             mock.patch.object(parts, "derive", side_effect=leased):
            result = artifacts.submit_artifact(self.request, store_root=self.store).result(60)
        self.assertNotEqual(threads, [threading.current_thread()])
        self.assertIsNone(leases[0], "with no daemon there is no broker to take a slot from")
        self.assert_geometry_and_result(result)
        self.settled()

    def test_real_daemon_detach_retains_native_worker_for_attached_subscriber(self):
        entered, release = self.root / "daemon-entered", self.root / "daemon-release"
        prelude = self.source_guard() + f"""
import time
from cadgen.store import parts
original=parts.derive
def derive(*args,**kwargs):
    Path({str(entered)!r}).write_text('entered')
    deadline=time.monotonic()+15
    while not Path({str(release)!r}).exists():
        if time.monotonic()>deadline: raise RuntimeError('test barrier')
        time.sleep(.005)
    return original(*args,**kwargs)
parts.derive=derive
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
            self.assertEqual(self.settled()["peakRunning"], 1)
            self.assertEqual(self.private.broker.snapshot()["granted"], 1)
            self.assertEqual(len(processes), 1)
            self.assertEqual(workers.snapshot()["imports"], 1)
            self.assertTrue(all(row["outputs"] == [] for row in ledger.snapshot()))


if __name__ == "__main__":
    unittest.main()
