"""``cadgen doctor`` — the one user-facing pin/version check the skills teach.

The per-verb shims that used to enforce the pin on every invocation are gone;
doctor re-homes that value as an explicit command, so its contract is pinned here:
report the install, resolve a requirements.txt from a file/dir/cwd, exit 0 on
match-or-nothing-to-check, exit 3 (the historical shim code) on a mismatch, and
exit 4 when the CAD kernel is installed but cannot be loaded -- naming Smart App
Control on Windows, where a refused ``OCP`` load is otherwise a bare
ImportError. A kernel that is simply absent is reported and exits 0: the release
workflow installs the wheel --no-deps and runs doctor as its smoke test.

The kernel probe is a fresh-interpreter ``import OCP``; it is stubbed here so
the contract tests cost no kernel load, and exercised once for real.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

import cadgen  # noqa: E402
from cadgen.cli import doctor  # noqa: E402


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

    def test_the_report_names_the_kernel_it_loaded(self) -> None:
        with TemporaryDirectory() as tmp:
            code, out, _ = _run([tmp])
        self.assertEqual(code, 0)
        self.assertIn("kernel   OK", out)
        self.assertIn("/site/OCP.pyd", out)

    def test_a_missing_kernel_is_reported_and_is_not_a_failure(self) -> None:
        # The release workflow installs the wheel --no-deps and runs doctor: no OCP
        # there is a correct install, and the pin is what brings the kernel.
        missing = "ModuleNotFoundError: No module named 'OCP'"
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_MISSING, missing)), \
                TemporaryDirectory() as tmp:
            code, out, err = _run([tmp])
        self.assertEqual(code, 0)
        self.assertIn("kernel   not installed", out)
        self.assertIn("pip install -r requirements.txt", out)
        self.assertNotIn("FAILED", err)

    def test_a_kernel_that_will_not_load_exits_4(self) -> None:
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_FAILED, REFUSED)), \
                mock.patch.object(sys, "platform", "linux"), TemporaryDirectory() as tmp:
            code, out, err = _run([tmp])
        self.assertEqual(code, 4)
        self.assertIn("kernel   FAILED", err)
        self.assertIn(REFUSED, err, "the exception line is the evidence")
        self.assertNotIn("Smart App Control", err, "off Windows the cause is not known")
        self.assertIn("pin      none found", out, "the rest of the report still prints")

    def test_a_refused_load_on_windows_names_smart_app_control(self) -> None:
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_FAILED, REFUSED)), \
                mock.patch.object(sys, "platform", "win32"), TemporaryDirectory() as tmp:
            code, _, err = _run([tmp])
        self.assertEqual(code, 4)
        self.assertIn("Smart App Control", err)
        self.assertIn("3077", err)

    def test_a_pin_mismatch_outranks_the_kernel(self) -> None:
        # The install is wrong before the kernel is: fixing the pin may fix both.
        with mock.patch.object(doctor, "_probe_kernel", return_value=(doctor.KERNEL_FAILED, REFUSED)), \
                TemporaryDirectory() as tmp:
            (Path(tmp) / "requirements.txt").write_text("cadgen==0.0.0.dev0\n", encoding="utf-8")
            code, _, err = _run([tmp])
        self.assertEqual(code, 3)
        self.assertIn("kernel   FAILED", err)
        self.assertIn("MISMATCH", err)

    def test_matching_pin_passes_and_names_the_file(self) -> None:
        with TemporaryDirectory() as tmp:
            req = Path(tmp) / "requirements.txt"
            req.write_text(f"cadgen=={cadgen.__version__}\n", encoding="utf-8")
            code, out, _ = _run([str(req)])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)
        self.assertIn(str(req), out)

    def test_mismatch_exits_3_with_the_install_instruction(self) -> None:
        with TemporaryDirectory() as tmp:
            (Path(tmp) / "requirements.txt").write_text("cadgen==0.0.0.dev0\n", encoding="utf-8")
            code, _, err = _run([tmp])
        self.assertEqual(code, 3)
        self.assertIn("MISMATCH", err)
        self.assertIn("pip install -r requirements.txt", err)


class KernelProbeTest(unittest.TestCase):
    """The real probe, once: this interpreter's kernel imports in a child."""

    def test_the_probe_imports_ocp_in_a_fresh_interpreter(self) -> None:
        state, detail = doctor._probe_kernel()
        self.assertEqual(state, doctor.KERNEL_OK, detail)
        self.assertIn("OCP", detail)

    def test_the_probe_tells_a_missing_kernel_from_a_refused_one(self) -> None:
        # The child interpreter's last stderr line is all the probe has. A
        # ModuleNotFoundError is "not installed" (a --no-deps wheel install, a
        # cadgen-free skill); anything else is the kernel refusing to load.
        import subprocess

        def child(stderr: str) -> subprocess.CompletedProcess:
            return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)

        missing = child("Traceback...\nModuleNotFoundError: No module named 'OCP'\n")
        with mock.patch("subprocess.run", return_value=missing):
            self.assertEqual(
                doctor._probe_kernel(),
                (doctor.KERNEL_MISSING, "ModuleNotFoundError: No module named 'OCP'"),
            )
        refused = child("ImportError: DLL load failed while importing OCP: Access is denied.\n")
        with mock.patch("subprocess.run", return_value=refused):
            state, detail = doctor._probe_kernel()
        self.assertEqual(doctor.KERNEL_FAILED, state)
        self.assertIn("DLL load failed", detail)


if __name__ == "__main__":
    unittest.main()
