"""A kernel Windows refuses to load is named as Smart App Control, nowhere else.

The cadquery-ocp wheels ship ``OCP``'s native module unsigned, and Windows 11's
Smart App Control blocks it with a bare ``ImportError: DLL load failed while
importing OCP``. That message says nothing about who refused the load, and the
fix is a machine setting, not a reinstall -- so the CLI failure report and
``cadgen doctor`` say so. The hint must fire on exactly that shape: not on a
missing install, not on another module's loader failure, and never off Windows.
"""

from __future__ import annotations

import io
import sys
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.cli_errors import report_cli_error  # noqa: E402
from cadgen._internal.kernel_load_hint import kernel_load_hint  # noqa: E402

REFUSED = "DLL load failed while importing OCP: Access is denied."


def _import_error(message: str, name: str | None = "OCP") -> ImportError:
    return ImportError(message, name=name)


class KernelLoadHintTest(unittest.TestCase):
    def test_a_refused_ocp_load_on_windows_names_smart_app_control(self) -> None:
        hint = kernel_load_hint(_import_error(REFUSED), platform="win32")
        self.assertIsNotNone(hint)
        text = "\n".join(hint)
        self.assertIn("Smart App Control", text)
        self.assertIn("3077", text, "the Event Viewer id is what makes the cause verifiable")
        self.assertIn("WSL", text, "the workaround that keeps the protection on")

    def test_the_same_failure_off_windows_is_not_this(self) -> None:
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform):
                self.assertIsNone(kernel_load_hint(_import_error(REFUSED), platform=platform))

    def test_a_missing_install_is_not_a_refused_load(self) -> None:
        # ModuleNotFoundError is pip's problem and already has its own hint.
        missing = ModuleNotFoundError("No module named 'OCP'", name="OCP")
        self.assertIsNone(kernel_load_hint(missing, platform="win32"))

    def test_another_modules_loader_failure_is_not_this(self) -> None:
        other = _import_error("DLL load failed while importing _ssl: ...", name="_ssl")
        self.assertIsNone(kernel_load_hint(other, platform="win32"))

    def test_an_unrelated_import_error_is_not_this(self) -> None:
        self.assertIsNone(
            kernel_load_hint(_import_error("cannot import name 'x' from 'OCP'"), platform="win32")
        )

    def test_stderr_text_is_read_the_same_way(self) -> None:
        # ``cadgen doctor`` probes the kernel in a subprocess and only has its stderr.
        line = "ImportError: DLL load failed while importing OCP: Access is denied."
        self.assertIsNotNone(kernel_load_hint(line, platform="win32"))
        self.assertIsNone(kernel_load_hint(line, platform="linux"))
        self.assertIsNone(kernel_load_hint("ModuleNotFoundError: No module named 'OCP'", platform="win32"))

    def test_the_default_platform_is_the_running_one(self) -> None:
        with mock.patch.object(sys, "platform", "win32"):
            self.assertIsNotNone(kernel_load_hint(_import_error(REFUSED)))
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIsNone(kernel_load_hint(_import_error(REFUSED)))


class ReportCarriesTheHintTest(unittest.TestCase):
    """The CLI failure report is where an agent reads the ImportError."""

    def _report(self, exc: BaseException, platform: str) -> str:
        stream = io.StringIO()
        with mock.patch.object(sys, "platform", platform):
            code = report_cli_error(exc, tool="python model.py", stream=stream)
        self.assertEqual(1, code)
        return stream.getvalue()

    def test_a_refused_load_on_windows_is_explained_under_the_failure(self) -> None:
        text = self._report(_import_error(REFUSED), "win32")
        lines = text.splitlines()
        self.assertTrue(lines[0].endswith(f"FAILED: ImportError: {REFUSED}"), lines[0])
        self.assertIn("Smart App Control", text)
        self.assertLess(
            text.index("Smart App Control"), text.index("re-run with --verbose"),
            "the cause comes before the generic hint",
        )

    def test_other_failures_are_reported_as_before(self) -> None:
        text = self._report(_import_error(REFUSED), "linux")
        self.assertNotIn("Smart App Control", text)
        text = self._report(ValueError("bad radius"), "win32")
        self.assertNotIn("Smart App Control", text)


if __name__ == "__main__":
    unittest.main()
