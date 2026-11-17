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
                              r"  update   auto-update off, installer off; .+\n  uv       .+\n  attempt  none\n$")

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
