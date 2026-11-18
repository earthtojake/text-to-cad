"""``cad mcp`` run from uv's cache (an app's server line, ``uvx ... cad@<release> mcp``) on a computer with no global
cad installs cad once with uv, then uses the installed cad's server; with a global cad, or run from anywhere else, it
installs nothing. Where the install fails, no server is started from the cache and every request is answered with one
line. Nothing is installed for real: uv's answers and the install are stand-ins, but for ``uv cache dir``, asked of the
real uv in a cache folder of the test's own."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import client
from cad_mcp import shim
from cad_mcp.protocol import RequestContext, RpcError
from cad_server._internal import launch, tool_install

TOOL = Path("/tools/cad")


class Started(unittest.TestCase):
    """Which way ``start_server`` goes, every outside step a stand-in."""

    def setUp(self) -> None:
        self.not_running = client.NOT_RUNNING
        for name, value in (("AT_LEAST", None), ("RELEASE", None), ("NOT_RUNNING", client.NOT_RUNNING)):
            patch = mock.patch.object(client, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.start = self.patch(client, "start", return_value="started this release's server")
        self.installed = self.patch(shim, "installed", return_value="the installed cad's server")

    def patch(self, target, name, **kwargs):
        patch = mock.patch.object(target, name, **kwargs)
        found = patch.start()
        self.addCleanup(patch.stop)
        return found

    def test_from_uv_s_cache_with_no_global_cad_it_installs_once_and_uses_the_installed_cad_s_server(self) -> None:
        found = self.patch(shim, "installed_tool", side_effect=[None, TOOL])
        self.patch(shim, "from_uv_cache", return_value=True)
        install = self.patch(tool_install, "install", return_value=["Installed 1 executable: cad"])
        with self.assertLogs("cad_mcp", "INFO") as logged:
            self.assertEqual(shim.start_server(), "the installed cad's server")
        install.assert_called_once_with(timeout=shim.INSTALL_SECONDS)
        self.assertEqual(found.call_count, 2, "asked again once installed")
        self.installed.assert_called_once_with(TOOL)
        self.start.assert_not_called()
        self.assertIn("INFO:cad_mcp:uv: Installed 1 executable: cad", logged.output)

    def test_with_a_global_cad_nothing_is_installed(self) -> None:
        self.patch(shim, "installed_tool", return_value=TOOL)
        asked = self.patch(shim, "from_uv_cache", side_effect=AssertionError("not asked"))
        self.patch(tool_install, "install", side_effect=AssertionError("nothing is installed"))
        self.assertEqual(shim.start_server(), "the installed cad's server")
        asked.assert_not_called()
        self.installed.assert_called_once_with(TOOL)

    def test_from_anywhere_but_uv_s_cache_nothing_is_installed_and_this_release_s_server_is_started(self) -> None:
        self.patch(shim, "installed_tool", return_value=None)
        self.patch(shim, "from_uv_cache", return_value=False)
        self.patch(tool_install, "install", side_effect=AssertionError("nothing is installed"))
        self.assertEqual(shim.start_server(), "started this release's server")
        self.start.assert_called_once_with()
        self.installed.assert_not_called()

    def test_an_install_that_fails_starts_no_server_and_every_request_gets_one_line(self) -> None:
        for failed in (tool_install.Failed("error: Executable already exists: cad (use `--force` to overwrite)"),
                       None):  # uv said it installed, yet no cad is found
            with self.subTest(failed=failed):
                client.NOT_RUNNING = self.not_running
                self.patch(shim, "installed_tool", return_value=None)
                self.patch(shim, "from_uv_cache", return_value=True)
                self.patch(tool_install, "install", **({"side_effect": failed} if failed else {"return_value": []}))
                with self.assertLogs("cad_mcp", "INFO") as logged, self.assertRaises(client.NotRunning) as said:
                    shim.start_server()
                self.assertEqual(str(said.exception), shim.NOT_INSTALLED)
                self.start.assert_not_called()
                self.installed.assert_not_called()
                if failed:
                    self.assertIn(f"INFO:cad_mcp:could not install cad with uv: {failed}", logged.output)
                # Every request that then finds no server is answered with the line, as one is with NotRunning's.
                holder = types.SimpleNamespace(started=threading.Event(), ident="held", want=lambda: None)
                holder.started.set()
                proxy = shim.Proxy(holder=holder)
                with mock.patch.object(client, "_connect", return_value=None):
                    self.assertEqual(proxy.handle("tools/call", {"name": "cad_show"}, RequestContext(1, {})),
                                     {"content": [{"type": "text", "text": shim.NOT_INSTALLED}], "isError": True})
                    with self.assertRaises(RpcError) as refused:
                        proxy.handle("resources/read", {"uri": "ui://cad/app"}, RequestContext(2, {}))
                self.assertEqual(refused.exception.message, shim.NOT_INSTALLED)

    def test_the_line_is_plain(self) -> None:
        self.assertEqual(shim.NOT_INSTALLED, "cad is not installed: run `uv tool install cad`")


class Install(unittest.TestCase):
    """The install itself: uv's own command, never forced, its refusal said in one line, and bounded in time. uv's bin
    folder is one of the test's own (``_bin``)."""

    def setUp(self) -> None:
        self.bin = Path(tempfile.mkdtemp(prefix="uvbin-")).resolve()
        self.addCleanup(shutil.rmtree, self.bin, True)
        self.tools = self.bin / "tools"  # uv's tool folder, as ``uv tool dir`` names it: no cad tool in it yet
        self.real_tools = tool_install._tools
        for patch in (mock.patch.object(tool_install, "_bin", return_value=self.bin),
                      mock.patch.object(tool_install, "_tools", return_value=self.tools)):
            patch.start()
            self.addCleanup(patch.stop)
        self.cad = self.bin / ("cad.exe" if os.name == "nt" else "cad")

    def test_the_command_is_uv_tool_install_of_the_newest_cad_of_this_major_with_cad_s_own_python_flags(self) -> None:
        """The newest release of the major of the cad doing the installing, never of a higher one: a copy pinned to
        this release may run long after a higher major is out. Worked out from the release, never a fixed number."""
        import cad_server

        for version, wanted in (("0.11.12", "cad<1"), ("0.12.0-dev.20261118", "cad<1"), ("1.4.2", "cad<2"),
                                ("10.0.0", "cad<11"), ("not a release", "cad")):
            with self.subTest(version=version):
                self.assertEqual(tool_install.command("uv", version),
                                 ["uv", "tool", "install", "--managed-python", "--python", launch.PYTHON, wanted])
        with mock.patch.object(cad_server, "__version__", "2.3.4"):
            self.assertEqual(tool_install.command("uv")[-1], "cad<3", "this cad's release by default")
        self.assertNotIn("--force", tool_install.command("uv"))

    def run_as_uv(self, code: str, timeout: float = 60.0) -> list[str]:
        with mock.patch.object(tool_install, "command", return_value=[sys.executable, "-c", code]):
            return tool_install.install("uv", timeout=timeout)

    def test_what_uv_said_is_returned_and_a_refusal_is_its_error_line(self) -> None:
        said = self.run_as_uv("import sys; sys.stderr.write('Resolved 9 packages\\nInstalled 1 executable: cad\\n')")
        self.assertEqual(said, ["Resolved 9 packages", "Installed 1 executable: cad"])
        with self.assertRaises(tool_install.Failed) as refused:
            self.run_as_uv("import sys; sys.stderr.write(' + cad==1.0.0\\nerror: Executable already exists: cad (use "
                           "`--force` to overwrite)\\n'); sys.exit(2)")
        self.assertEqual(str(refused.exception), "error: Executable already exists: cad (use `--force` to overwrite)")

    def test_a_uv_that_hangs_is_stopped_at_its_bound(self) -> None:
        began = time.monotonic()
        with self.assertRaises(tool_install.Failed) as stopped:
            self.run_as_uv("import time; time.sleep(60)", timeout=0.5)
        self.assertLess(time.monotonic() - began, 30)
        self.assertEqual(str(stopped.exception), "uv did not finish within 0.5 s, and was stopped")

    def test_no_uv_is_a_failure_never_a_crash(self) -> None:
        with mock.patch.object(tool_install, "find", return_value=None):
            with self.assertRaises(tool_install.Failed):
                tool_install.install(timeout=1)
            self.assertFalse(tool_install.from_uv_cache(sys.prefix))

    def holding(self, release: str | None) -> None:
        """uv's tool ``cad`` with ``release`` in its environment's site-packages and no launcher (None: half made)."""
        site = self.tools / "cad" / "lib" / "python3.14" / "site-packages"
        site.mkdir(parents=True, exist_ok=True)
        if release is not None:
            (site / f"cad-{release}.dist-info").mkdir()

    def test_a_tool_of_a_higher_major_is_never_moved_down_and_uv_is_never_run(self) -> None:
        """``cad<1`` would move a cad 2.0.1 whose launcher is missing down to 0.x, with exit status 0: refused."""
        import cad_server

        self.holding("2.0.1")
        with mock.patch.object(cad_server, "__version__", "0.11.12"), \
                mock.patch.object(tool_install, "_run", side_effect=AssertionError("uv is never run")), \
                self.assertRaises(tool_install.Failed) as refused:
            tool_install.install("uv", timeout=1)
        self.assertEqual(str(refused.exception), "uv's cad tool holds cad 2.0.1, of a newer major version than this "
                                                 "cad installs, so cad was left as it is")

    def test_a_tool_of_this_major_or_one_half_made_is_installed_over(self) -> None:
        import cad_server

        for release in ("0.11.13", "0.9.0", None):
            with self.subTest(release=release), mock.patch.object(cad_server, "__version__", "0.11.12"):
                shutil.rmtree(self.tools, ignore_errors=True)
                self.holding(release)
                self.assertEqual(self.run_as_uv("print('Installed 1 executable: cad')"),
                                 ["Installed 1 executable: cad"])

    def test_where_uv_cannot_say_where_its_tools_are_nothing_is_run(self) -> None:
        def run(command, timeout):
            if command[1:3] == ["tool", "dir"]:
                return subprocess.CompletedProcess(command, 2, "", "error: no home folder")
            raise AssertionError("uv's install is never run")

        for answer in ({"side_effect": run}, {"side_effect": OSError("no uv")},
                       {"side_effect": subprocess.TimeoutExpired("uv", 15)}):
            with self.subTest(answer=answer), mock.patch.object(tool_install, "_tools", self.real_tools), \
                    mock.patch.object(tool_install, "_run", **answer), self.assertRaises(tool_install.Failed) as refused:
                tool_install.install("uv", timeout=1)
            self.assertEqual(str(refused.exception), "uv could not say where its tools are, so cad was left as it is")

    # BRIDGE-ONLY: the cad command of 0.10.0 to 0.11.11 in uv's bin folder, which uv would refuse to replace.
    OLD = "#!/bin/sh\n# cad proxy: 3\nexec python -m cad_server._internal.proxy \"$@\"\n"

    def uv_that(self, code: int, writes: bool) -> str:
        """A stand-in uv: it notes whether a ``cad`` was in its way, writes uv's own where ``writes``, and exits
        ``code``."""
        return (f"import os, sys\nprint('in the way' if os.path.lexists({str(self.cad)!r}) else 'room')\n"
                + (f"open({str(self.cad)!r}, 'w').write('uv')\n" if writes else "")
                + ("sys.stderr.write('error: Executable already exists: cad\\n')\n" if code else "")
                + f"sys.exit({code})\n")

    def test_the_old_cad_command_is_set_aside_and_deleted_once_uv_installed_cad(self) -> None:
        self.cad.write_text(self.OLD, encoding="utf-8")
        self.assertTrue(tool_install.old_launcher(self.cad))
        self.assertEqual(self.run_as_uv(self.uv_that(0, writes=True)), ["room"], "out of uv's way while it ran")
        self.assertEqual(self.cad.read_text(encoding="utf-8"), "uv")
        self.assertEqual(sorted(os.listdir(self.bin)), [self.cad.name], "nothing left beside it")

    def test_the_old_cad_command_is_put_back_where_uv_failed(self) -> None:
        self.cad.write_text(self.OLD, encoding="utf-8")
        with self.assertRaises(tool_install.Failed):
            self.run_as_uv(self.uv_that(2, writes=False))
        self.assertEqual(self.cad.read_text(encoding="utf-8"), self.OLD, "put back: it still runs cad")
        self.assertEqual(sorted(os.listdir(self.bin)), [self.cad.name])
        with self.assertRaises(tool_install.Failed):
            self.run_as_uv("import time; time.sleep(60)", timeout=0.5)
        self.assertEqual(self.cad.read_text(encoding="utf-8"), self.OLD, "put back after uv was stopped too")

    def test_another_program_s_cad_is_never_moved(self) -> None:
        other = "#!/bin/sh\necho another cad\n"
        self.cad.write_text(other, encoding="utf-8")
        self.assertFalse(tool_install.old_launcher(self.cad))
        with self.assertRaises(tool_install.Failed) as refused:
            self.run_as_uv(self.uv_that(2, writes=False))
        self.assertEqual(str(refused.exception), "error: Executable already exists: cad")
        self.assertEqual(self.cad.read_text(encoding="utf-8"), other)
        self.assertEqual(sorted(os.listdir(self.bin)), [self.cad.name])


class FromUvCache(unittest.TestCase):
    """Whether this process runs from uv's cache: its environment in the folder ``uv cache dir`` names, asked of the
    real uv with a cache folder of the test's own (``UV_CACHE_DIR``)."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="uvcache-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.uv = tool_install.find()
        if self.uv is None:
            raise AssertionError("uv is not found: cad depends on it")

    def test_an_environment_in_uv_s_cache_is_and_one_outside_it_is_not(self) -> None:
        cache = self.root / "cache"
        made = cache / "archive-v0" / "abc"  # where uvx makes the environment it runs
        made.mkdir(parents=True)
        with mock.patch.dict(os.environ, {"UV_CACHE_DIR": str(cache)}):
            self.assertTrue(tool_install.from_uv_cache(str(made), self.uv))
            self.assertFalse(tool_install.from_uv_cache(str(self.root / "project" / ".venv"), self.uv))
            self.assertFalse(tool_install.from_uv_cache(sys.prefix, self.uv), "the tests' own Python")

    def test_either_answer_counts_where_uv_s_settings_name_another_cache(self) -> None:
        answers = {True: str(self.root / "plain"), False: str(self.root / "settings")}

        def run(command, timeout):
            return subprocess.CompletedProcess(command, 0, answers["--no-config" in command] + "\n", "")

        with mock.patch.object(tool_install, "_run", side_effect=run):
            for folder in answers.values():
                self.assertTrue(tool_install.from_uv_cache(str(Path(folder) / "archive-v0" / "x"), "uv"))
            self.assertFalse(tool_install.from_uv_cache(str(self.root / "elsewhere"), "uv"))
        with mock.patch.object(tool_install, "_run", side_effect=OSError("no uv")):
            self.assertFalse(tool_install.from_uv_cache(str(self.root), "uv"))


if __name__ == "__main__":
    unittest.main()
