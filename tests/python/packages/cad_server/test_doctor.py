"""``cad doctor``: one read-only report -- the release, the data and cache folders and what ``cad cache prune`` would
free, the CAD kernel environment (never made here) and whether its kernel loads, the integrations', and whether the
server runs and its release (asked, never started). It writes, registers, starts and deletes nothing; ``--check`` is
the same report, ``--json`` it as one document. Exit 0, or 1 when the kernel is installed and does not load -- naming
Smart App Control on Windows, where a refused ``OCP`` load is otherwise a bare ImportError.

The kernel probe is a fresh-interpreter ``import OCP``; it is stubbed here so the contract tests cost no kernel load,
and exercised once for real.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine.previous import version  # noqa: E402
from cad_server.cli import doctor  # noqa: E402


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = doctor.main(argv)
    return code, out.getvalue(), err.getvalue()


REFUSED = "ImportError: DLL load failed while importing OCP: Access is denied."


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_OK, "/site/OCP.pyd"))
        patcher.start()
        self.addCleanup(patcher.stop)
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name).resolve()
        environment = mock.patch.dict("os.environ", {"CAD_STATE_DIR": str(self.root / "state"),
                                                     "CAD_CACHE_DIR": str(self.root / "cache"),
                                                     "CAD_ENGINE_DIR": str(self.root / "engine")})
        environment.start()
        self.addCleanup(environment.stop)

    def tree(self) -> list[str]:
        return sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*"))

    def test_the_report_writes_nothing_and_starts_nothing_and_check_is_the_same_report(self) -> None:
        from cad.engine import client

        with mock.patch.object(client, "request", wraps=client.request) as asked:
            code, out, err = _run([])
            again = _run(["--check"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(again, (code, out, err))
        self.assertEqual(self.tree(), [], "no folder, record, setting or server made")
        self.assertTrue(asked.call_args_list and all(call.kwargs.get("start") is False for call in asked.call_args_list))
        self.assertEqual(out.splitlines()[0], f"cad {version()}")
        self.assertEqual([line.split()[0] for line in out.splitlines()[1:5]], ["python", "install", "data", "cache"])
        self.assertIn(f"  data     {self.root / 'state'}\n", out)
        self.assertIn(f"  cache    {self.root / 'cache'}: nothing for `cad cache prune` to remove\n", out)
        self.assertRegex(out, r"  server   not running \(.+\): run `cad server start`\n"
                              r"  update   this cad is not a global install, so it never updates "
                              r"itself; plugin update auto off\n  newest   the version feed has not been read on this "
                              r"computer yet\n  uv       .+\n  attempt  none\n"
                              r"  plugin   no record of the install command being up to date on this computer\n$")

    def test_the_cache_line_says_what_cad_cache_prune_would_free(self) -> None:
        from cad_server._internal import base

        env = base.folder() / "theirs00"
        base.interpreter(env).parent.mkdir(parents=True)
        base.interpreter(env).write_bytes(b"p" * 3 * 1024 * 1024)
        (env / base.MARKER).write_text(json.dumps({"schema": base.SCHEMA, "key": env.name,
                                                   "inputs": {"release": "0.11.9"}}), encoding="utf-8")
        before = self.tree()
        _code, out, _err = _run([])
        self.assertIn(f"  cache    {self.root / 'cache'}: `cad cache prune` would remove 1 folder of other releases and "
                      "free 3.0 MB\n", out)
        self.assertEqual(self.tree(), before, "said, never removed")

    def test_the_server_is_said_with_its_release_and_never_started(self) -> None:
        from cad.engine import client

        answer = {"pid": 4242, "workers": [{"script": "a.py"}], "standby": {"pid": 4343}, "cap": 10, "version": version()}
        with mock.patch.object(client, "request", return_value=answer) as asked:
            self.assertRegex(_run([])[1], rf"  server   running, pid 4242, cad {version()}, workers 2/10 with the standby "
                                          r"\(.+\)\n")
        self.assertEqual(asked.call_args.kwargs, {"start": False, "timeout": doctor.STATUS_SECONDS})
        with mock.patch.object(client, "request", return_value={**answer, "version": "0.11.9"}):
            code, said, _err = _run(["--json"])
        server = next(check for check in json.loads(said)["checks"] if check["name"] == "server")
        self.assertEqual((code, server["status"]), (0, "warning"))
        self.assertIn(", cad 0.11.9, workers 2/10", server["detail"])
        self.assertTrue(server["detail"].endswith(f": not this release; `cad server start` runs {version()}'s"))
        with mock.patch.object(client, "request", side_effect=client.Unanswered("the cad server did not answer within 10 s")):
            self.assertIn("  server   unknown (Unanswered: the cad server did not answer within 10 s)\n", _run([])[1])

    def test_a_kernel_environment_not_made_is_reported_never_made_and_is_not_a_failure(self) -> None:
        # The release workflow installs the wheel --no-deps and runs doctor: no kernel environment there (no uv, no
        # network) is a correct install, and the first need makes it.
        from cad_server._internal import base

        made = base.Environment("/cache/base/k/bin/python", "/cache/base/k", False, ("/cache/base/k/site",))
        with mock.patch.object(base, "ensure", return_value=made) as asked:
            code, out, _err = _run([])
        self.assertEqual((code, [call.kwargs["make"] for call in asked.call_args_list]), (0, [False]))
        self.assertIn("  kernel   OK — OCP at /site/OCP.pyd (the CAD kernel environment, /cache/base/k)\n", out)
        doctor._probe_kernel.assert_called_with("/cache/base/k/bin/python")
        with mock.patch.object(base, "ensure", return_value=None):
            code, out, _err = _run([])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"  kernel   not made — \S+, made on first need: the first build or view that needs it\n")
        with mock.patch.object(base, "ensure", side_effect=base.Refused("it needs the network once: dns error")):
            self.assertEqual(_run([])[0], 0)

    def test_where_the_builds_ran_in_an_environment_cad_run_made_its_kernel_is_said_not_the_base_s_absence(self) -> None:
        """A build's worker runs in the environment ``cad run`` made for its program where that is not the base (a
        setting of uv's from the caller, more than the kernel): doctor says that one's kernel, and the base not made,
        never "not made" alone after a build that worked."""
        from cad_server._internal import base

        here = base.Installation.here()

        def made(name: str, inputs: dict, integrations: list[str]) -> Path:
            env = base.folder() / name
            base.interpreter(env).parent.mkdir(parents=True)
            base.interpreter(env).write_text("", encoding="utf-8")
            (env / base.MARKER).write_text(json.dumps({"schema": base.SCHEMA, "key": name, "inputs": inputs,
                                                       "integrations": integrations}), encoding="utf-8")
            return env

        made("kicad0000", base._inputs(here), ["kicad"])  # an integration's: no kernel
        made("older000", {**base._inputs(here), "release": "0.0.1"}, ["build123d"])  # another release's
        ran = made("ran00000", base._inputs(here), ["build123d"])
        with mock.patch.object(base, "ensure", return_value=None):
            code, out, _err = _run([])
        self.assertEqual(code, 0)
        self.assertIn(f"  kernel   OK — OCP at /site/OCP.pyd (the environment `cad run` made for a program, {ran}; the "
                      f"CAD kernel environment, {base.where()}, made on first need)\n", out)
        doctor._probe_kernel.assert_called_with(str(base.interpreter(ran)))

    def test_a_kernel_that_will_not_load_exits_1_and_the_whole_report_is_on_stdout(self) -> None:
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_FAILED, REFUSED)), \
                mock.patch.object(sys, "platform", "linux"):
            code, out, err = _run([])
        self.assertEqual((code, err), (1, ""))
        self.assertIn(f"  kernel   FAILED — {REFUSED}\n", out, "the exception line is the evidence")
        self.assertNotIn("Smart App Control", out, "off Windows the cause is not known")
        self.assertIn("  server   ", out, "the rest of the report still prints")

    def test_a_refused_load_on_windows_names_smart_app_control(self) -> None:
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_FAILED, REFUSED)), \
                mock.patch.object(sys, "platform", "win32"):
            code, out, _err = _run([])
            _code, said, _err = _run(["--json"])
        self.assertEqual(code, 1)
        self.assertIn("Smart App Control", out)
        kernel = next(check for check in json.loads(said)["checks"] if check["name"] == "kernel")
        self.assertEqual((kernel["status"], kernel["detail"]), ("failed", f"FAILED — {REFUSED}"))
        self.assertTrue(any("Smart App Control" in line for line in kernel["more"]))

    def test_the_report_as_json_is_one_document_of_every_check(self) -> None:
        code, out, _ = _run([])
        code_json, said, err = _run(["--json"])
        found = json.loads(said)
        self.assertEqual((code, code_json, found["ok"], found["version"], err), (0, 0, True, version(), ""))
        self.assertEqual(said.count("\n"), 1, "one line")
        names = [check["name"] for check in found["checks"]]
        self.assertEqual(names[:5], ["python", "install", "data", "cache", "kernel"])
        self.assertLessEqual({"trimesh", "kicad", "server"}, set(names))
        self.assertTrue(all(check["status"] in ("ok", "info", "warning", "failed") for check in found["checks"]))
        self.assertEqual([f"  {check['name']:<8} {check['detail']}" for check in found["checks"]], out.splitlines()[1:])


class PrivateFolderTests(unittest.TestCase):
    """On Windows a packaged app keeps a folder made from inside it under AppData in a private copy only it sees. uv's
    folder there holds a copy of cad that works in that app alone and wins over the real one there, or a failed try's
    leftovers, where every new Python uv installs from inside that app fails. `cad server start` and `cad doctor` name
    each such folder with its reason and say to delete it in File Explorer (a delete from inside that app does not
    reach it); cad never deletes it. Off Windows they say nothing. A stand-in %LOCALAPPDATA% here, so it runs on every
    system."""

    def setUp(self) -> None:
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name).resolve()
        self.local = self.root / "Local"
        self.copy = self.local / "Packages/App_1/LocalCache/Roaming/uv"
        (self.copy / "tools/cad/Scripts").mkdir(parents=True)
        self.leftover = self.local / "Packages/App_2/LocalCache/Roaming/uv"
        (self.leftover / "python").mkdir(parents=True)
        # Not uv's folder in an app's private Roaming: never named.
        (self.local / "Packages/App_3/LocalCache/Local/uv/tools/cad").mkdir(parents=True)
        (self.local / "Packages/App_4/LocalCache/Roaming/other").mkdir(parents=True)
        for patcher in (mock.patch.dict("os.environ", {"CAD_STATE_DIR": str(self.root / "state"),
                                                       "CAD_CACHE_DIR": str(self.root / "cache"),
                                                       "CAD_ENGINE_DIR": str(self.root / "engine"),
                                                       "CAD_UPDATE_CHECK": "0", "LOCALAPPDATA": str(self.local)}),
                        mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_OK, "/site/OCP.pyd")),
                        mock.patch.object(doctor, "WINDOWS", True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def lines(self) -> list[str]:
        return [doctor.COPY_LINE.format(path=self.copy), doctor.LEFTOVER_LINE.format(path=self.leftover)]

    def start(self) -> tuple[int, str, str]:
        from cad.engine import client
        from cad_server.cli import server

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(client, "start", return_value="the cad server is running") as started, \
                redirect_stdout(out), redirect_stderr(err):
            code = server.main(["start"])
        started.assert_called_once()
        return code, out.getvalue(), err.getvalue()

    def test_each_folder_is_named_with_its_reason_by_both_commands_and_never_deleted(self) -> None:
        copy, leftover = self.lines()
        self.assertEqual(copy, f"another copy of cad is in an app's private folder: {self.copy}. That app keeps using "
                               "it instead of this one. Delete that folder in File Explorer so every app uses this "
                               "cad; deleting it from inside that app does not work.")
        self.assertEqual(leftover, f"uv left files in an app's private folder: {self.leftover}. Inside that app a new "
                                   "Python lands there and fails to install. Delete that folder in File Explorer; "
                                   "deleting it from inside that app does not work.")
        code, out, err = self.start()
        self.assertEqual((code, out), (0, "the cad server is running\n"))
        self.assertEqual(sorted(err.splitlines()), [f"cad: {copy}", f"cad: {leftover}"])
        code, out, _err = _run([])
        self.assertEqual(code, 0, "worth a look, never a failure")
        self.assertIn(f"  private  {copy}\n", out)
        self.assertIn(f"  private  {leftover}\n", out)
        private = [check for check in json.loads(_run(["--json"])[1])["checks"] if check["name"] == "private"]
        self.assertEqual(sorted(check["detail"] for check in private), [copy, leftover])
        self.assertEqual({check["status"] for check in private}, {"warning"})
        self.assertTrue(self.copy.is_dir() and self.leftover.is_dir(), "named, never deleted")

    def test_the_folder_this_cad_runs_from_is_not_named(self) -> None:
        # Inside the app this cad runs from that very folder, by another name: compared as folders, not as words.
        # Deleting it would remove this cad.
        with mock.patch.object(sys, "prefix", str(self.copy / "tools/cad/Scripts/..")):
            self.assertEqual(doctor.private_folders(), self.lines()[1:])
        self.assertEqual(sorted(doctor.private_folders()), sorted(self.lines()))

    def test_nothing_is_said_off_windows_or_where_there_is_no_folder(self) -> None:
        with mock.patch.object(doctor, "WINDOWS", False):
            self.assertEqual(self.start(), (0, "the cad server is running\n", ""))
            self.assertNotIn("\n  private  ", _run([])[1])
        shutil.rmtree(self.copy)
        shutil.rmtree(self.leftover)
        self.assertEqual(self.start(), (0, "the cad server is running\n", ""))
        self.assertNotIn("\n  private  ", _run([])[1])

    def test_a_broken_localappdata_never_fails_a_start(self) -> None:
        file = self.root / "a-file"
        file.write_text("", encoding="utf-8")
        for value in ("", str(file), str(self.root / "gone"), "\\\\?\\nowhere"):
            with mock.patch.dict("os.environ", {"LOCALAPPDATA": value}):
                self.assertEqual(self.start(), (0, "the cad server is running\n", ""), value)
        with mock.patch.dict("os.environ"):
            del os.environ["LOCALAPPDATA"]
            self.assertEqual(self.start(), (0, "the cad server is running\n", ""))
        with mock.patch.object(Path, "glob", side_effect=OSError("refused")):
            self.assertEqual(self.start(), (0, "the cad server is running\n", ""))


class KernelProbeTest(unittest.TestCase):
    """The real probe, once: this interpreter's kernel imports in a child."""

    def test_the_probe_imports_the_installed_kernel_whatever_folder_it_runs_from(self) -> None:
        with TemporaryDirectory() as folder:
            Path(folder, "OCP.py").write_text("raise SystemExit('the working folder was searched')\n", encoding="utf-8")
            here = os.getcwd()
            os.chdir(folder)
            try:
                state, detail = doctor._probe_kernel()
            finally:
                os.chdir(here)
        self.assertEqual(state, doctor.KERNEL_OK, detail)
        self.assertIn("OCP", detail)
        self.assertNotIn(os.path.realpath(folder), os.path.realpath(detail))

    def test_the_probe_tells_a_missing_kernel_from_a_refused_one(self) -> None:
        # The child interpreter's last stderr line is all the probe has. A ModuleNotFoundError is "not installed" (a
        # --no-deps wheel install); anything else is the kernel refusing to load.
        import subprocess

        def child(stderr: str) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)

        with mock.patch("subprocess.run", return_value=child("Traceback...\nModuleNotFoundError: No module named 'OCP'\n")):
            self.assertEqual(doctor._probe_kernel(), (doctor.KERNEL_MISSING, "ModuleNotFoundError: No module named 'OCP'"))
        with mock.patch("subprocess.run", return_value=child(REFUSED + "\n")) as ran:
            self.assertEqual(doctor._probe_kernel(), (doctor.KERNEL_FAILED, REFUSED))
        self.assertIn("-B", ran.call_args.args[0], "its import writes no bytecode")


if __name__ == "__main__":
    unittest.main()
