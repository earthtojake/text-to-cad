"""One server per installed version, side by side, each reached through its own door and on its own port; the flat
door every client of 0.11.10 and earlier finds, held by the server of the version ``installations/current`` names;
and the cleanup the newest version's server runs (``cad_server._internal.versions``, ``cad_server.engine.daemon``).

Real servers: two versions made present in one temporary device (``test_versions.Device``: uv stood in for, each
version a virtual environment of this Python that imports this checkout and this interpreter's packages), each server
started from its own version's Python under its own name. ``CAD_ENGINE_DEFAULT_PORT`` stands in for 3245, so no test
binds the machine's. A client of 0.11.10 and earlier is this library's client as a process with no version: its flat
path (the flat engine folder, ``installations/current`` and the record it names) is that release's unchanged (``git
diff v0.11.10 -- packages/cad/src/cad/engine/client.py``: the channel field and the engine folder's making alone).
An older version is made unused by its files' times (``Device.aged``): nothing waits two days.
"""

from __future__ import annotations

import http.client
import os
import socket
import subprocess
import sysconfig
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.packages.cad_server.test_versions import DAY, Device, Uv, site_packages

from cad.engine import client, contract, places
from cad_server._internal import base, installations, versions

X, Y, Z = "0.12.0", "0.12.1", "0.12.2"
# How long a server is given to come up, or to go.
WAIT = 60.0


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class ServingUv(Uv):
    """``Uv``, its server environments importing this interpreter's packages too, so a version's own Python runs
    its server for real."""

    def __call__(self, step, folder, settings=None):
        done = super().__call__(step, folder, settings)
        if step[1] != "venv" and self.installs_server(step) and done.returncode == 0:
            env = Path(step[step.index("--python") + 1]).parent.parent
            (site_packages(env) / "zz_inherit.pth").write_text(
                f"import site; site.addsitedir({sysconfig.get_paths()['purelib']!r})\n", encoding="utf-8")
        return done


class Servers(Device):
    REAL_SERVERS = True

    def setUp(self) -> None:
        super().setUp()
        self.port = free_port()
        environment = {"CAD_ENGINE_DEFAULT_PORT": str(self.port), "CAD_ENGINE_STANDBY": "0", "CAD_ENGINE_PORT": "",
                       "CAD_UPDATE_CHECK": "0", "CAD_API_URL": "http://127.0.0.1:9", "PYTHONPATH": ""}
        for patch in (mock.patch.dict(os.environ, environment), mock.patch.object(base, "_uv", ServingUv())):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.stop_all)
        self.flat = self.engines / ("engine.port" if places.WINDOWS else "engine.door")

    # --- the device ------------------------------------------------------------------------------------

    def version(self, name: str) -> None:
        """Version ``name`` present; its data is copied in by its server's first start."""
        self.present(name)

    def start(self, name: str, *, tend: float | None = None) -> int:
        """Version ``name``'s server started from its own Python, detached, its name told, as a client of that version
        starts it (``client._start``) -- with ``tend``, tending itself every ``tend`` seconds rather than
        ``TEND_SECONDS`` --: its pid once it answers at its own door."""
        record = places.version_record(name)
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        env[places.INSTALLATION_ENV] = name
        folder = places.make_engine_dir(places.engine_dir(name))
        code = ("import sys\nfrom cad_server.engine import daemon\n"
                + (f"daemon.TEND_SECONDS = {tend!r}\n" if tend is not None else "") + "sys.exit(daemon.main())\n")
        process = subprocess.Popen([record["python"], "-P", "-c", code], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=str(folder),
                                   **places.detached())
        threading.Thread(target=process.wait, daemon=True).start()
        self.until(lambda: versions.ask(name, {"op": "pid"}, seconds=2.0) is not None, f"{name}'s server answers")
        return versions.ask(name, {"op": "pid"})["pid"]

    def stop_all(self) -> None:
        for name in (X, Y, Z):
            if versions.ask(name, {"op": "stop"}, seconds=5.0) is not None:
                client.wait_gone(timeout=WAIT, endpoint=versions.endpoint(name))

    def until(self, condition, said: str, within: float = WAIT) -> None:
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.1)
        self.fail(f"not within {within} s: {said}")

    def serve(self, name: str) -> dict:
        """Version ``name``'s server serving pages: its endpoint (``url``, ``port``, ``token``)."""
        answer = versions.ask(name, {"op": "http"}, seconds=WAIT)
        self.assertTrue(answer and answer.get("url"), answer)
        return answer

    # --- a client of 0.11.10 and earlier -----------------------------------------------------------------

    def old(self, message: dict, *, start: bool = True) -> dict | None:
        """``message`` asked as a client of 0.11.10 and earlier asks it: through the flat door, starting the
        server ``installations/current`` names where none answers there."""
        self.assertIsNone(places.versioned(), "this test's process has no version: the flat door is its door")
        return client.request(message, start=start)

    def page(self, port: int, token: str) -> int:
        """A page's request on ``port`` with ``token``: its status."""
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        try:
            connection.request("GET", "/api/v1/local/link", headers={"Authorization": f"Bearer {token}"})
            return connection.getresponse().status
        finally:
            connection.close()

    def within(self, prefix: str, name: str) -> bool:
        inside = os.path.realpath(places.code_dir(name)) + os.sep
        return os.path.realpath(prefix).startswith(inside)


class FlatDoor(Servers):
    def test_a_client_of_0_11_10_starts_the_version_current_names_and_finds_it_at_the_flat_door(self) -> None:
        self.version(X)
        self.assertTrue(installations.mirror(X))  # what the hand-over from a shipped release writes
        self.assertFalse(versions.serves(X))
        status = self.old({"op": "status"})  # nothing runs: it starts what installations/current names
        self.assertTrue(self.within(status["prefix"], X) and status["bridge"], status.get("prefix"))
        self.assertTrue(versions.serves(X), "the version's own server, under its own lock")
        # A second start of the version while it runs fronts it: the client that started it finds the flat door.
        self.start(X)
        self.assertTrue(versions.ask(X, {"op": "status"})["bridge"])

    def test_versions_run_side_by_side_and_the_flat_door_follows_current(self) -> None:
        for name in (X, Y):
            self.version(name)
        self.assertTrue(installations.mirror(X))
        self.start(X, tend=0.5)
        self.start(Y, tend=0.5)
        self.assertEqual(self.serve(X)["port"], self.port, "the default port")
        self.assertNotEqual(self.serve(Y)["port"], self.port, "the second takes the next free port")
        self.until(lambda: versions.ask(X, {"op": "status"})["bridge"], f"{X}'s server holds the flat door")
        self.assertFalse(versions.ask(Y, {"op": "status"})["bridge"])
        self.assertTrue(self.within(self.old({"op": "status"}, start=False)["prefix"], X))
        installations.mirror(Y)
        self.until(lambda: versions.ask(Y, {"op": "status"})["bridge"] and not versions.ask(X, {"op": "status"})["bridge"],
                   "the flat door moves to the version current names, at their tending")
        self.assertTrue(self.within(self.old({"op": "status"}, start=False)["prefix"], Y))


class ShippedSwitchAtTheFlatDoor(Servers):
    def test_a_shipped_updater_s_drain_lets_the_flat_door_go_and_never_the_version_s_server(self) -> None:
        """0.11.10's switch asks whatever holds the flat door to drain before it points ``installations/current``
        (``{"op": "stop", "drain": true}``, unmarked): a version's server lets that door go, and only that, so the
        switch goes on and the version's own sessions are not stopped; a process of the version takes it back."""
        self.version(X)
        self.assertTrue(installations.mirror(X))
        x = self.start(X)
        self.until(lambda: versions.ask(X, {"op": "status"})["bridge"], "its server holds the flat door")
        self.assertEqual(self.old({"op": "stop", "drain": True}, start=False), {"ok": True, "draining": True})
        self.until(lambda: not versions.ask(X, {"op": "status"})["bridge"], "the flat door let go")
        self.assertIsNone(self.old({"op": "pid"}, start=False), "nothing answers at the flat door")
        self.assertEqual(versions.ask(X, {"op": "pid"})["pid"], x, "the version's server runs on at its own door")
        self.assertEqual(versions.ask(X, {"op": "bridge"}), {"ok": True, "flat": True}, "taken back when asked")
        self.assertEqual(self.old({"op": "pid"}, start=False)["pid"], x)


class PortHandedToARunningServer(Servers):
    def test_the_flat_door_asked_for_the_old_port_on_a_server_serving_another_takes_it_too_and_never_fails(self) -> None:
        """0.11.10's switch helper asks the server ``installations/current`` names, through the flat door, to serve on the port 0.11.10
        served (``{"op": "http", "port": P}``) and stops it should the answer say ``failed``. A server that started
        while 0.11.10 still held P serves on another, Q: it takes P too, the port pages were on, which is its own
        from then on, and keeps Q; where P cannot be taken, it answers with where it serves."""
        self.version(X)
        self.assertTrue(installations.mirror(X))
        x = self.start(X)
        self.until(lambda: versions.ask(X, {"op": "status"})["bridge"], "its server holds the flat door")
        other = free_port()
        served = versions.ask(X, {"op": "http", "port": other}, seconds=WAIT)  # it serves Q: 0.11.10 held P
        self.assertEqual(served["port"], other, served)
        answer = self.old({"op": "http", "port": self.port}, start=False)
        self.assertNotIn("failed", answer)
        self.assertEqual((answer["port"], answer["token"]), (self.port, served["token"]), "P, with the same token")
        self.assertTrue(answer["url"].endswith(f":{self.port}"), answer)
        status = versions.ask(X, {"op": "status"})
        self.assertEqual((status["pid"], status["serving"]["port"], status["serving"]["also"]), (x, self.port, [other]),
                         "the same server: P its own now, as status says it and a later update hands it on")
        for port in (self.port, other):
            self.assertEqual(self.page(port, served["token"]), 200, f"a page open on {port} works")
        # A port another program holds: answered with where it serves, never `failed` (0.11.10 would stop it).
        taken = socket.socket()
        self.addCleanup(taken.close)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        held = self.old({"op": "http", "port": taken.getsockname()[1]}, start=False)
        self.assertEqual((held.get("failed"), held["port"]), (None, self.port), held)
        self.assertEqual(versions.ask(X, {"op": "pid"})["pid"], x, "still running")


class PortsHeldAtTheHandover(Servers):
    def test_a_server_serving_nothing_asked_for_a_port_still_held_serves_another_and_never_fails(self) -> None:
        """E4: a new server that holds the flat door but serves no pages yet, asked (by 0.11.10's helper, or a
        bridge) for the old pages' port while the old server still holds it, binds as if no port were asked and
        answers with that address: ``failed`` would have 0.11.10's helper stop it."""
        self.version(X)
        self.assertTrue(installations.mirror(X))
        x = self.start(X)
        self.until(lambda: versions.ask(X, {"op": "status"})["bridge"], "its server holds the flat door")
        taken = socket.socket()
        self.addCleanup(taken.close)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        held = taken.getsockname()[1]
        answer = self.old({"op": "http", "port": held}, start=False)
        self.assertNotIn("failed", answer or {})
        self.assertNotEqual(answer["port"], held)
        self.assertEqual(versions.ask(X, {"op": "pid"})["pid"], x, "still running")



class Cleanup(Servers):
    def test_the_newest_version_s_server_stops_and_removes_an_older_one_unused_for_two_days(self) -> None:
        for name in (X, Y):
            self.version(name)
        x = self.start(X)
        self.serve(X)
        self.aged(X, installed=time.time() - 30 * DAY, used=time.time() - 3 * DAY)
        self.start(Y, tend=0.5)  # as it starts, it cleans
        self.until(lambda: not places.version_dir(X).exists(), f"{Y}'s server removes {X}")
        self.assertIsNone(versions.ask(X, {"op": "pid"}, seconds=2.0), f"{X}'s server ({x}) stopped first")
        self.assertTrue(versions.serves(Y) and places.version_dir(Y).exists(), "never its own")


class NoVersion(Servers):
    def test_a_process_with_no_version_reaches_the_flat_door_s_server_and_another_contract_is_refused(self) -> None:
        self.version(X)
        self.assertTrue(installations.mirror(X))
        self.start(X)
        self.until(lambda: versions.ask(X, {"op": "status"})["bridge"], "its server holds the flat door")
        status = self.old({"op": "status"}, start=False)
        self.assertTrue(self.within(status["prefix"], X), "reached the flat door's server, never a version's "
                                                          "data by a release number")
        forged = {**contract.interpreter(), "release": "0.0.1", "contract": {**contract.CONTRACT, "protocol": 0}}
        answer = self.old({"op": "build", "script": str(self.root / "model.py"), "cwd": str(self.root),
                           "env": {}, "interpreter": forged}, start=False)
        self.assertIn("update the cad package in this environment to", answer["failed"])
        self.assertTrue(answer["failed"].endswith("or run it with `cad run`"), answer["failed"])


if __name__ == "__main__":
    unittest.main()
