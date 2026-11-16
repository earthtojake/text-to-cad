"""Real servers of versions made present side by side in one temporary device (``test_versions.Device``: uv stood in
for, each version a virtual environment of this Python that imports this checkout and this interpreter's packages),
each server started from its own version's Python under its own name: ``test_setup``'s fixture. Their flat door and
their cleanup went with one cad (the server starts by ``cad server start`` alone, and cleans nothing), and their
tests with them. ``CAD_ENGINE_DEFAULT_PORT`` stands in for 3245, so no test binds the machine's.
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

from cad.engine import client, places
from cad_server._internal import base, versions

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


if __name__ == "__main__":
    unittest.main()
