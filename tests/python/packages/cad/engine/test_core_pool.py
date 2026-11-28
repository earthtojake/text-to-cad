"""The engine's pool jobs on the view core (``core_pool.CorePool``): each job the core answers asked of its job
server in its frames and answered as the engine's own job answers, a job it refuses the asker's error, a job it
does not answer a kernel process's. The server here is a stand-in that speaks its frames (the real one is the view
core's host, which its own tools hold to the engine's code part by part), so what the pool asks and makes of the
answers is checked wherever the suite runs."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
import unittest
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

SRC = add_sources()

from cad.engine import core_pool, serve  # noqa: E402
from cad.engine.core_pool import CorePool  # noqa: E402

# A job server that answers each job with what it was asked, so a test reads the request in the answer.
SERVER = textwrap.dedent("""
    import json, os, struct, sys
    sizes = struct.Struct(">QI")
    asked, out = sys.stdin.buffer, sys.stdout.buffer

    def send(header, payloads=()):
        head = json.dumps({**header, "payloads": [len(p) for p in payloads]}).encode()
        out.write(sizes.pack(4 + len(head) + sum(map(len, payloads)), len(head)) + head + b"".join(payloads))
        out.flush()

    while True:
        first = asked.read(sizes.size)
        if len(first) < sizes.size:
            break
        length, head_length = sizes.unpack(first)
        body = asked.read(length - 4)
        header = json.loads(body[:head_length])
        payloads, at = [], head_length
        for size in header["payloads"]:
            payloads.append(body[at:at + size]); at += size
        job, said = header["job"], {"id": header["id"], "ok": True}
        echo = json.dumps({key: value for key, value in header.items() if key not in ("id", "payloads")},
                          separators=(",", ":"), sort_keys=True).encode()
        if payloads and payloads[0] == b"no shape":
            send({"id": header["id"], "ok": False, "job": job, "error": "vc_open_shape: no shape in these bytes"})
        elif payloads and payloads[0] == b"die":
            os._exit(7)
        elif payloads and payloads[0] == b"hang":
            import time
            time.sleep(3600)
        elif payloads and payloads[0] == b"garbage":
            out.write(sizes.pack(12, 8) + b"not json"); out.flush()
        elif payloads and payloads[0] == b"trap":
            send({"id": header["id"], "ok": False, "job": job, "error": "RuntimeError: memory access out of bounds"})
        elif job == "about":
            send({**said, "abi": 1, "pid": os.getpid()})
        elif job == "mesh":
            send({**said, "unmeshed": {"3": "no triangles"}, "seconds": 0.25}, [b"XBM2" + payloads[0]])
        elif job == "table":
            send(said, [echo, *([b'{"volume":2.5}'] if header["measure"] else [])])
        elif job == "measured":
            send(said, [json.dumps({"key": key, "bytes": len(p)}).encode() for key, p in zip(header["keys"], payloads)])
        elif job == "fact":
            send(said, [echo])
        elif job == "read_xbf":
            structure = {"name": "pair", "units": "mm", "tessellation": {"linear": 0.1}, "closure": "abc",
                         "prototypes": [{"index": 0, "key": "k1", "name": "base", "color": [0.5, 0.5, 0.5, 1.0],
                                         "faceColors": {"2": [1.0, 0.0, 0.0, 1.0]}}],
                         "instances": [{"prototype": 0, "path": "base", "matrix": [1.0] * 16, "color": None}],
                         "tree": {"name": "pair"}}
            send({**said, "path": header["path"], "version": ["1700000000000000001", 42],
                  "parts": [{"key": "k1", "name": "base"}]}, [json.dumps(structure).encode(), b"shape of k1"])
        else:
            send({"id": header["id"], "ok": False, "job": job, "error": "no job " + job})
""")


def _pid() -> int:
    return os.getpid()


def _alive(pid: int) -> bool:
    import time

    for _ in range(200):  # killed and waited for: gone at once, or within moments where the system is slow to say so
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        time.sleep(0.01)
    return True


class _Kernel:
    """The kernel pool a job the core does not answer goes to: what it was asked, kept."""

    def __init__(self) -> None:
        self.asked: list[tuple] = []
        self.ended: list[str] = []

    def submit(self, fn, *args):
        import concurrent.futures

        self.asked.append((fn, args))
        future: concurrent.futures.Future = concurrent.futures.Future()
        future.set_result("the kernel's answer")
        return future

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        self.ended.append("shutdown")

    def terminate_workers(self) -> None:
        self.ended.append("terminated")


class CorePoolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="core-pool-")).resolve()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        (self.folder / "server.py").write_text(SERVER, encoding="utf-8")
        program = self.folder / ("viewcore.cmd" if os.name == "nt" else "viewcore")
        program.write_text(f'@"{sys.executable}" "{self.folder / "server.py"}"\r\n' if os.name == "nt" else
                           f'#!/bin/sh\nexec "{sys.executable}" "{self.folder / "server.py"}"\n', encoding="utf-8")
        program.chmod(0o755)
        self.program = str(program)
        self.kernels: list[_Kernel] = []

    def pool(self, workers: int = 2) -> CorePool:
        def kernel() -> _Kernel:
            self.kernels.append(_Kernel())
            return self.kernels[-1]

        found = CorePool(workers, self.program, kernel)
        self.addCleanup(found.terminate_workers)
        return found

    def test_each_job_the_core_answers_is_asked_in_its_frames_and_answered_as_the_engine_s_own(self) -> None:
        pool = self.pool()
        self.assertEqual(pool.submit(serve._timed, b"shape", True).result(60), (b"XBM2shape", {3: "no triangles"}, 0.25))
        table, measure = pool.submit(serve._table, "k1", b"shape", (4, 2), True).result(60)
        self.assertEqual((json.loads(table), measure),
                         ({"job": "table", "key": "k1", "measure": True, "unmeshed": [4, 2]}, {"volume": 2.5}))
        self.assertEqual(pool.submit(serve._table, "k1", b"shape").result(60)[1], None)
        self.assertEqual(pool.submit(serve._measured, [("k1", b"a"), ("k2", b"bcd")]).result(60),
                         [("k1", {"key": "k1", "bytes": 1}), ("k2", {"key": "k2", "bytes": 3})])
        self.assertEqual(pool.submit(serve._topology_fact, "k1", b"shape", "face", (7,)).result(60),
                         {"job": "fact", "key": "k1", "method": "face", "args": [7]})
        self.assertEqual(pool.submit(serve._topology_fact, "k1", b"shape", "elements", ((4, 2),)).result(60)["args"],
                         [[4, 2]])
        # A pool's warm-up loads no kernel here: the process is ready as it starts.
        self.assertEqual((pool.submit(serve._ready).result(60), pool.submit(int).result(60)), (True, 0))
        self.assertEqual(self.kernels, [], "no kernel process was asked for any of these")

    def test_an_xbf_read_is_the_engine_s_read_document(self) -> None:
        path = self.folder / "XBF" / "pair.xbf"
        structure, version, shapes, names = self.pool().submit(serve._read_document, str(path)).result(60)
        self.assertEqual((version, shapes, names), ((1700000000000000001, 42), {"k1": b"shape of k1"}, {"k1": "base"}))
        self.assertEqual(list(structure)[:4], ["name", "path", "version", "units"])
        self.assertEqual((structure["path"], structure["version"]), (str(path), "1700000000000000001-42"))
        self.assertNotIn("tessellation", structure)
        self.assertNotIn("closure", structure)
        # Colours as the engine's own structure holds them: tuples.
        self.assertEqual((structure["prototypes"][0]["color"], structure["prototypes"][0]["faceColors"]["2"],
                          structure["instances"][0]["color"]), ((0.5, 0.5, 0.5, 1.0), (1.0, 0.0, 0.0, 1.0), None))

    def test_what_the_core_refuses_is_the_job_s_error_and_its_process_goes_on(self) -> None:
        pool = self.pool(1)
        before = pool.submit(serve._ready).result(60)
        with self.assertRaisesRegex(ValueError, "^vc_open_shape: no shape in these bytes$"):
            pool.submit(serve._timed, b"no shape", True).result(60)
        self.assertEqual(pool.submit(serve._timed, b"shape", True).result(60)[0], b"XBM2shape")
        self.assertTrue(before)
        # One that dies fails its job alone, and the next job starts another.
        with self.assertRaises(BrokenProcessPool):
            pool.submit(serve._timed, b"die", True).result(60)
        self.assertEqual(pool.submit(serve._timed, b"shape", True).result(60)[0], b"XBM2shape")

    def test_a_host_late_garbled_or_trapped_is_killed_its_job_refused_and_the_next_job_has_another(self) -> None:
        """A job past its deadline, an answer that is no frame, and a trapped module's refusal: the host killed (by its
        process) and waited for, the job refused in one line, the next job answered by a fresh host."""
        pool = self.pool(1)
        for given, said in ((b"hang", "^the view core took longer than 1 s for its mesh job, and was stopped"),
                            (b"garbage", "^the view core's job server answered its mesh job with what is no answer"),
                            (b"trap", "^the view core failed its mesh .*memory access out of bounds.*started afresh")):
            with self.subTest(host=given.decode()):
                pool.submit(serve._ready).result(60)
                [before] = [child.pid for child in pool._children.values()]
                with mock.patch.dict(core_pool.SECONDS, {"mesh": 1.0}), self.assertRaisesRegex(ValueError, said):
                    pool.submit(serve._timed, given, True).result(60)
                self.assertFalse(_alive(before), "the host is gone")
                self.assertEqual(pool.submit(serve._timed, b"shape", True).result(60)[0], b"XBM2shape")
                self.assertNotEqual([child.pid for child in pool._children.values()], [before], "a fresh host")

    def test_a_job_the_core_does_not_answer_is_a_kernel_process_s_started_for_the_first_of_them(self) -> None:
        pool = self.pool()
        self.assertIsNone(core_pool.request(serve._pose_structure, ({}, None)))
        self.assertIsNone(core_pool.request(serve._read_foreign, ("part.step", "digest")))
        self.assertIsNone(core_pool.request(serve._read_document, ("part.step",)))
        self.assertIsNone(core_pool.request(serve._timed, (object(), True)), "a live shape is no bytes for the core")
        self.assertIsNone(core_pool.request(_pid, ()))
        self.assertEqual(self.kernels, [])
        self.assertEqual(pool.submit(serve._pose_structure, {"name": "arm"}, None).result(60), "the kernel's answer")
        self.assertEqual(pool.submit(_pid).result(60), "the kernel's answer")
        (kernel,) = self.kernels
        self.assertEqual([fn.__name__ for fn, _args in kernel.asked], ["_pose_structure", "_pid"])
        serve._end(pool)
        self.assertEqual(kernel.ended[-1], "terminated", "ended with its pool")
        with self.assertRaises(RuntimeError):
            pool.submit(serve._pose_structure, {}, None)

    def test_the_engine_s_pool_is_this_one_where_its_kernel_folder_carries_the_core(self) -> None:
        found = {"python": sys.executable, "prefix": sys.prefix, "path": None, "own": False, "wasm": True}
        with mock.patch("cad.engine.places.kernel", return_value={**found, "core": self.program}):
            pool = serve._process_pool(8, initializer=serve.exit_with_parent)
        self.addCleanup(pool.terminate_workers)
        self.assertIsInstance(pool, CorePool)
        self.assertEqual(pool.workers, core_pool.PROCESSES)
        self.assertIs(pool.submit(serve._ready).result(60), True)
        with mock.patch("cad.engine.places.kernel", return_value=found):
            without = serve._process_pool(2)
        self.addCleanup(without.terminate_workers)
        self.assertNotIsInstance(without, CorePool)


if __name__ == "__main__":
    unittest.main()
