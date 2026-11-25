"""``cad mcp`` run from anywhere but the installed uv tool ``cad`` (Codex's plugin line runs it from uvx's cache, at the
plugin's release) starts no server of its own: it runs the installed cad's own ``cad server start`` and joins the
server that leaves running, whatever the two releases are, and a newer server already running is joined, never
replaced. With a REAL uv tool: this tree as a release older than itself (``machine.wheel``), installed with uv into a
tool folder of the test's own (``UV_TOOL_DIR``, ``UV_TOOL_BIN_DIR``), on state, engine and cache folders of its own.
Where no tool is installed, this release's server is started as ``cad server start`` starts it (``test_shim_start``)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import api, client
from cad.engine.previous import version
from cad_mcp import shim
from cad_server._internal import auto_update
from tests.python.support import engine_daemon, machine

# A release older than this tree's, which no index holds.
OLDER = f"0.10.{9000 + os.getpid() % 800}"


def _uv() -> str:
    found = shutil.which("uv")
    if found:
        return found
    from uv import find_uv_bin

    return find_uv_bin()


class InstalledToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="tool-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        wheels = cls.root / "wheels"
        wheels.mkdir()
        machine.wheel("cad", OLDER, wheels)
        cls.uv = _uv()
        cls.tools = {"UV_TOOL_DIR": str(cls.root / "tools"), "UV_TOOL_BIN_DIR": str(cls.root / "bin"),
                     "UV_NO_MODIFY_PATH": "1"}
        print(f"\nuv tool folders of this test: {cls.tools}", file=sys.stderr)
        done = subprocess.run([cls.uv, "tool", "install", "--python", sys.executable, "--find-links", str(wheels),
                               f"cad=={OLDER}"], env={**os.environ, **cls.tools}, capture_output=True, text=True,
                              timeout=600)
        if done.returncode:
            raise AssertionError(f"uv tool install cad=={OLDER}: {done.stdout}{done.stderr}")
        cache = subprocess.run([cls.uv, "cache", "dir"], capture_output=True, text=True, timeout=60).stdout.strip()
        if cache:
            cls.addClassCleanup(machine.forget, Path(cache), (OLDER,))
        cls.tool = Path(cls.tools["UV_TOOL_DIR"]) / "cad"
        assert auto_update.uv_tool(str(cls.tool)) is not None, "uv's receipt names cad"

    def setUp(self) -> None:
        engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        self.addCleanup(shutil.rmtree, engine, True)
        folder = Path(tempfile.mkdtemp(dir=self.root))
        self.env = {**self.tools, "CAD_ENGINE_DIR": engine, "CAD_STATE_DIR": str(folder / "state"),
                    "CAD_CACHE_DIR": str(folder / "cache"), "CAD_UPDATE_CHECK": "0",
                    "PATH": os.pathsep.join([str(Path(self.uv).parent), os.environ.get("PATH", "")])}
        patched = mock.patch.dict(os.environ, self.env)
        patched.start()
        self.addCleanup(patched.stop)
        self.addCleanup(api.stop)  # whichever server runs there, the tool's or this tree's: before the folder goes
        for name, value in (("AT_LEAST", None), ("RELEASE", None)):
            patch = mock.patch.object(client, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def status(self) -> dict:
        return client.request({"op": "status", "internal": True}, start=False)

    def test_the_tool_is_found_as_uv_says_and_this_process_is_not_it(self) -> None:
        self.assertEqual(auto_update.installed_tool(), self.tool)
        with mock.patch.dict(os.environ, {"UV_TOOL_DIR": str(self.root / "no-tools")}):
            self.assertIsNone(auto_update.installed_tool(), "no cad tool there")

    def test_no_server_running_the_installed_older_cad_starts_its_own_and_it_is_joined(self) -> None:
        with mock.patch.object(client, "_spawn", side_effect=AssertionError("cad mcp started a server of its own")):
            said = shim.start_server()
        self.assertTrue(said.startswith(f"started the cad server (cad {OLDER})"), said)
        status = self.status()
        self.assertEqual(status["version"], OLDER)
        self.assertEqual(os.path.realpath(status["prefix"]), os.path.realpath(self.tool), "the tool's environment")
        self.assertEqual(client.AT_LEAST, OLDER, "the older server it left running is reached")
        held = client.hold(start=False)
        self.assertIsNotNone(held)
        held.close()

    def test_a_newer_server_already_running_is_joined_never_replaced(self) -> None:
        engine_daemon.start({**os.environ})  # this tree's server, newer than the installed cad
        before = self.status()
        self.assertEqual(before["version"], version())
        said = shim.start_server()
        self.assertTrue(said.startswith(f"the cad server (cad {version()}, newer than this cad {OLDER}) is already "
                                        "running"), said)
        self.assertEqual(self.status()["pid"], before["pid"], "the same server")
        self.assertEqual(client.AT_LEAST, version())

    def test_where_the_installed_cad_cannot_start_its_server_cad_mcp_starts_none_of_its_own(self) -> None:
        broken = self.root / "broken"  # a tool whose own cad command is gone
        with mock.patch.object(shim, "installed_tool", return_value=broken), \
                mock.patch.object(client, "_spawn", side_effect=AssertionError("cad mcp started a server of its own")):
            with self.assertRaises(ConnectionError) as said:
                shim.start_server()
        self.assertIn("could not start its server", str(said.exception))
        self.assertIsNone(client.request({"op": "pid"}, start=False), "no server runs")


if __name__ == "__main__":
    unittest.main()
