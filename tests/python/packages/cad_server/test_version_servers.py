"""One server per installed version, each reached through its own door; the flat door every client of 0.11.10 and
earlier finds, held by the default channel's version's server alone; and what an update of the default channel does
to the servers, their port and their pages (``cad_server._internal.versions``, ``cad_server.engine.daemon``).

Real servers: two (or three) versions made present in one temporary device (``test_versions.Device``: uv stood in
for, each version a virtual environment of this Python that imports this checkout and this interpreter's packages),
each server started from its own version's Python under its own name. ``CAD_ENGINE_DEFAULT_PORT`` stands in for
3245, so no test binds the machine's. A client of 0.11.10 and earlier is this library's client as a process with no
version: its flat path (the flat engine folder, ``installations/current`` and the record it names) is that release's
unchanged (``git diff v0.11.10 -- packages/cad/src/cad/engine/client.py``: the channel field and the engine folder's
making alone).
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

from tests.python.packages.cad_server.test_versions import Device, Uv, site_packages

from cad.engine import client, contract, places
from cad_server._internal import base, pointers, versions

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
        if step[1] != "venv" and any("cad-server" in word for word in step) and done.returncode == 0:
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
        """Version ``name`` present; its data is imported by its first start (the move, else its server's)."""
        self.present(name)

    def start(self, name: str, *, tend: float | None = None) -> int:
        """Version ``name``'s server started from its own Python (``versions.start_server``), or, with ``tend``, the
        same daemon tending itself every ``tend`` seconds rather than ``TEND_SECONDS``: its pid."""
        if tend is None:
            self.assertTrue(versions.start_server(name), f"{name}'s server started")
        else:
            record = places.version_record(name)
            env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
            env[places.INSTALLATION_ENV] = name
            folder = places.make_engine_dir(places.engine_dir(name))
            code = ("import sys\nfrom cad_server.engine import daemon\n"
                    f"daemon.TEND_SECONDS = {tend!r}\nsys.exit(daemon.main())\n")
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


class DefaultMove(Servers):
    def test_nothing_in_flight_the_new_version_serves_on_the_old_port_with_the_old_token(self) -> None:
        for name in (X, Y):
            self.version(name)
        self.assertEqual(versions.move(None, X).kind, "moved")
        self.start(X)
        endpoint = self.serve(X)
        self.assertEqual(endpoint["port"], self.port, "the default port")
        status = versions.ask(X, {"op": "status"})
        self.assertTrue(status["bridge"], "the default's server holds the flat door")
        old = self.old({"op": "status"}, start=False)
        self.assertTrue(self.within(old["prefix"], X), "a client of 0.11.10 reaches the default's server")
        self.assertEqual(self.page(self.port, endpoint["token"]), 200)

        moved = versions.move(None, Y)
        self.assertEqual((moved.kind, moved.removed), ("moved", {X: "removed"}), moved.said)
        self.assertIn(f"text-to-cad {Y} serves pages on port {self.port}, as {X} did", moved.said)
        self.assertFalse(versions.serves(X) or places.version_dir(X).exists(), "the version left is gone")
        after = self.serve(Y)
        self.assertEqual((after["port"], after["token"]), (self.port, endpoint["token"]),
                         "the same port, with the token it imported")
        self.assertEqual(self.page(self.port, endpoint["token"]), 200, "a page open before reloads into it")
        self.assertTrue(versions.ask(Y, {"op": "status"})["bridge"], "the flat door moved with the default")
        old = self.old({"op": "status"}, start=False)
        self.assertTrue(self.within(old["prefix"], Y), "and a client of 0.11.10 reaches the new default's server")

    def test_a_client_of_0_11_10_starts_the_default_from_the_mirror_and_finds_it_at_the_flat_door(self) -> None:
        self.version(X)
        self.assertEqual(versions.move(None, X).kind, "moved")
        self.assertFalse(versions.serves(X))
        status = self.old({"op": "status"})  # nothing runs: it starts what installations/current names
        self.assertTrue(self.within(status["prefix"], X) and status["bridge"], status.get("prefix"))
        self.assertTrue(versions.serves(X), "the version's own server, under its own lock")
        # A second start of the version while it runs fronts it: the client that started it finds the flat door.
        self.start(X)
        self.assertTrue(versions.ask(X, {"op": "status"})["bridge"])


class Kept(Servers):
    def test_another_pointer_keeps_the_old_version_and_a_named_channel_never_holds_the_flat_door(self) -> None:
        for name in (X, Y, Z):
            self.version(name)
        self.assertEqual(versions.move(None, X).kind, "moved")
        self.assertEqual(versions.move("store", X).kind, "moved")
        self.assertEqual(versions.move("other", Z).kind, "moved")
        x = self.start(X)
        self.assertEqual(self.serve(X)["port"], self.port)
        self.start(Z)
        self.assertFalse(versions.ask(Z, {"op": "status"})["bridge"], "a named channel's server: never the flat door")
        self.assertTrue(self.within(self.old({"op": "status"}, start=False)["prefix"], X))

        moved = versions.move(None, Y)
        self.assertEqual((moved.kind, moved.removed), ("moved", {}), "the store still names it: never stopped")
        self.assertEqual(versions.ask(X, {"op": "pid"})["pid"], x, "the old version's server is left as it is")
        self.assertEqual(versions.ask(X, {"op": "status"})["serving"]["port"], self.port, "with its port and pages")
        self.start(Y)
        self.until(lambda: versions.ask(Y, {"op": "status"})["bridge"], "the flat door moves to the new default")
        self.assertFalse(versions.ask(X, {"op": "status"})["bridge"])
        self.assertFalse(versions.ask(Z, {"op": "status"})["bridge"])
        self.assertNotEqual(self.serve(Y)["port"], self.port, "the new version takes the next free port")
        self.assertTrue(self.within(self.old({"op": "status"}, start=False)["prefix"], Y))


class Retiring(Servers):
    def test_an_unnamed_idle_server_stops_itself_and_another_server_s_sweep_removes_its_folder(self) -> None:
        for name in (X, Y):
            self.version(name)
        pointers.write(None, Y)
        (places.version_dir(X) / versions.SUCCESSOR).write_text(f"{Y}\n", encoding="utf-8")  # the default left it
        self.start(X, tend=1.0)  # no pointer names it, nor the default: once idle, it goes
        self.until(lambda: not versions.serves(X), f"{X}'s server stops itself")
        self.assertTrue(places.version_dir(X).exists(), "a server never removes the folder it runs from")
        self.start(Y, tend=1.0)
        self.until(lambda: not places.version_dir(X).exists(), f"{Y}'s server's sweep removes {X}'s folder")
        self.assertTrue(versions.serves(Y) and places.version_dir(Y).exists(), "never its own")


class NoVersion(Servers):
    def test_a_process_with_no_version_reaches_the_default_and_another_contract_is_refused(self) -> None:
        self.version(X)
        self.assertEqual(versions.move(None, X).kind, "moved")
        self.start(X)
        status = self.old({"op": "status"}, start=False)
        self.assertTrue(self.within(status["prefix"], X), "reached the default's server, never a version's data "
                                                          "by a release number")
        forged = {**contract.interpreter(), "release": "0.0.1", "contract": {**contract.CONTRACT, "protocol": 0}}
        answer = self.old({"op": "build", "script": str(self.root / "model.py"), "cwd": str(self.root),
                           "env": {}, "interpreter": forged}, start=False)
        self.assertIn("update the cad package in this environment to", answer["failed"])
        self.assertTrue(answer["failed"].endswith("or run it with `cad run`"), answer["failed"])


if __name__ == "__main__":
    unittest.main()
