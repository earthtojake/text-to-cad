"""A reader or mesh child that dies must not disable the shared engine daemon until restart: the
next read or mesh rebuilds the pool, as the STEP path already does. Covers serve.Server._readers
and serve.Mesher.processes self-healing a broken ProcessPoolExecutor, and where a STEP read goes
when reads come at once (``Server._reading``: the reader, else one of its helpers)."""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine import serve  # noqa: E402


class FakePool:
    """A stand-in ProcessPoolExecutor: no child processes, records shutdown, can be marked broken."""

    instances: list["FakePool"] = []

    def __init__(self, *args, **kwargs):
        self._broken = False
        self.shut = False
        FakePool.instances.append(self)

    def submit(self, *args, **kwargs):
        future: "object" = __import__("concurrent.futures", fromlist=["Future"]).Future()
        future.set_result(True)
        return future

    def shutdown(self, *args, **kwargs):
        self.shut = True


class PoolRecoveryTest(unittest.TestCase):
    def setUp(self):
        FakePool.instances = []
        self._real = serve.concurrent.futures.ProcessPoolExecutor
        serve.concurrent.futures.ProcessPoolExecutor = FakePool

    def tearDown(self):
        serve.concurrent.futures.ProcessPoolExecutor = self._real

    def test_a_broken_reader_pool_is_rebuilt_on_the_next_read(self):
        server = serve.Server.__new__(serve.Server)
        server.foreign_lock = threading.Lock()
        server.reader = None
        first = server._readers()
        self.assertIs(server.reader, first)
        again = server._readers()
        self.assertIs(again, first)  # a healthy pool is reused, not replaced
        first._broken = "a child died"
        rebuilt = server._readers()
        self.assertIsNot(rebuilt, first)  # the dead pool is replaced
        self.assertTrue(first.shut)  # and shut down
        self.assertFalse(getattr(rebuilt, "_broken"))

    def test_a_broken_mesh_pool_is_rebuilt_on_the_next_job(self):
        mesher = serve.Mesher(mode="processes", workers=1)
        first = mesher.processes()
        self.assertIs(mesher.processes(), first)  # reused while healthy
        first._broken = "a child died"
        rebuilt = mesher.processes()
        self.assertIsNot(rebuilt, first)
        self.assertTrue(first.shut)


class ReaderLanesTest(unittest.TestCase):
    """A board's part models come at once: small files are read beside the one reader, by helpers
    that go once no read is under way; a large file, or any under memory pressure, waits for it."""

    def setUp(self):
        FakePool.instances = []
        saved = {name: getattr(serve, name) for name in ("READERS", "HELPERS_LINGER")}
        self.addCleanup(lambda: [setattr(serve, name, value) for name, value in saved.items()])
        real = serve.concurrent.futures.ProcessPoolExecutor
        self.addCleanup(setattr, serve.concurrent.futures, "ProcessPoolExecutor", real)
        serve.concurrent.futures.ProcessPoolExecutor = FakePool
        serve.READERS, serve.HELPERS_LINGER = 4, 0.01
        server = self.server = serve.Server.__new__(serve.Server)
        server.foreign_lock = threading.Lock()
        server.reader = server.helpers = server.helpers_idle = None
        server.reading = {"reader": 0, "all": 0}
        server.pressure = serve.Pressure()
        server.pressure.simulate(False)
        server.stopping = threading.Event()

    def test_small_reads_at_once_go_beside_the_reader_and_its_helpers_go_once_none_is_under_way(self):
        server = self.server
        self.assertEqual(server._reading(40_000), "reader", "the reader, warm, takes a read when it is free")
        self.assertEqual([server._reading(40_000) for _ in range(3)], ["helpers"] * 3)
        self.assertEqual(server._reading(serve.HELPER_BYTES + 1), "reader", "a large file waits for the one reader")
        server.pressure.simulate(True)
        self.assertEqual(server._reading(40_000), "reader", "under memory pressure nothing is read beside it")
        helpers = server._helpers()
        for lane in ("reader", "helpers", "helpers", "helpers", "reader", "reader"):
            server._read_done(lane)
        self.assertEqual(server.reading, {"reader": 0, "all": 0})
        idle = server.helpers_idle  # None if its HELPERS_LINGER has run out already
        if idle is not None:
            idle.join()
        self.assertIsNone(server.helpers)
        self.assertTrue(helpers.shut, "the helpers went once no read was under way")

    def test_a_read_that_comes_before_the_helpers_go_keeps_them(self):
        serve.HELPERS_LINGER = 60.0  # the next read comes first, however slow the machine is to it
        server = self.server
        server.reading["reader"] = server.reading["all"] = 1
        self.assertEqual(server._reading(40_000), "helpers")
        helpers = server._helpers()
        server._read_done("helpers")
        server._read_done("reader")
        waiting = server.helpers_idle
        self.assertEqual(server._reading(40_000), "reader")
        waiting.join()  # cancelled by that read: at once
        self.assertIs(server.helpers, helpers)
        self.assertFalse(helpers.shut)


if __name__ == "__main__":
    unittest.main()
