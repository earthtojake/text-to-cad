"""A reader or mesh child that dies must not disable the shared engine daemon until restart: the
next read or mesh rebuilds the pool, as the STEP path already does. Covers serve.Server._readers
and serve.Mesher.processes self-healing a broken ProcessPoolExecutor."""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine import serve  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
