"""The cleanup while the older version it would remove has work in flight: that version's server is left exactly as
it is -- its process, its port and its pages --, and the version goes at a later cleanup, once nothing is in flight
(``versions.clean``). Work in flight is a real build: a model whose body waits on a file this test writes, built by a
worker of this interpreter (``Daemon.caller``) on the old version's server.

Its own file: the worker's start is this suite's slowest step (``test_version_servers`` has the rest)."""

from __future__ import annotations

import os
import textwrap
import threading
import unittest

import time
from unittest import mock

from tests.python.packages.cad_server.test_version_servers import X, Y, Servers
from tests.python.packages.cad_server.test_versions import DAY

from cad.engine import client, contract, places
from cad_server._internal import versions

SCRIPT = """
import os
import time
from pathlib import Path

from cad import model


@model
def held():
    here = Path(__file__).parent
    (here / "started").write_text("", encoding="utf-8")
    while not (here / "release").exists():
        time.sleep(0.05)
    import build123d as bd

    return bd.Box(1, 1, 1)
"""


class Busy(Servers):
    def build(self, name: str) -> threading.Thread:
        """A build on version ``name``'s server, through its own door, in the background: held until ``release``."""
        project = self.root / "project"
        project.mkdir()
        (project / "model.py").write_text(textwrap.dedent(SCRIPT), encoding="utf-8")
        self.addCleanup(lambda: (project / "release").write_text("", encoding="utf-8"))
        order = {"op": "build", "script": str(project / "model.py"), "functions": ["held"], "cwd": str(project),
                 "env": {key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
                 "interpreter": contract.interpreter()}
        door = versions.endpoint(name).address

        def building() -> None:
            connection = client._connect(door)
            self.assertIsNotNone(connection)
            client._exchange(connection, order, address=door)

        thread = threading.Thread(target=building, daemon=True)
        thread.start()
        self.until(lambda: (project / "started").exists(), "the build is under way")
        return thread

    def test_with_work_in_flight_the_old_server_is_untouched_until_a_later_cleanup(self) -> None:
        for name in (X, Y):
            self.version(name)
        x = self.start(X)
        token = self.serve(X)["token"]
        building = self.build(X)
        self.assertTrue(versions.connected(X), "a build in flight keeps its version")
        now = time.time()
        self.aged(X, installed=now - 30 * DAY, used=now - 3 * DAY)

        with mock.patch.object(places, "versioned", return_value=Y):  # Y's server's cleanup
            self.assertEqual(versions.clean(now=now), {X: "connected"})
        self.assertEqual(versions.ask(X, {"op": "pid"})["pid"], x, "its server is left exactly as it is")
        self.assertEqual(versions.ask(X, {"op": "status"})["serving"]["port"], self.port, "its port and its pages")
        self.assertTrue(places.version_dir(X).exists())
        self.assertEqual(self.page(self.port, token), 200)

        (self.root / "project" / "release").write_text("", encoding="utf-8")
        building.join(60)
        self.assertFalse(versions.connected(X), "nothing in flight once the build is done")
        with mock.patch.object(places, "versioned", return_value=Y):
            self.assertEqual(versions.clean(now=now + versions.CLEAN_SECONDS), {X: "removed"})
        self.assertFalse(places.version_dir(X).exists() or versions.serves(X))


if __name__ == "__main__":
    unittest.main()
