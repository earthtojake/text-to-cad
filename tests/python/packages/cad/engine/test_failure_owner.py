"""Whose a failed build's error is to fix (``owner``, ``build._owner``): the model's own code, a
library the model called, the kernel refusing a call, the library refusing what it was given, or a
defect of the library's own -- the one a page offers to report."""

from __future__ import annotations

import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import build as engine_build

SCRIPT = """
import build123d as bd
from cad import dxf, model


@model
def asserted():
    part = bd.Box(1, 1, 1) + bd.Box(1, 1, 1).moved(bd.Location((5, 0, 0)))
    assert len(part.solids()) == 1, ("disconnected", len(part.solids()))
    return part


@model
def zero():
    return bd.Box(0, 60, 5)


@model
def rounded():
    return bd.fillet(bd.Box(10, 10, 10).edges(), 20)


@dxf("plate.dxf")
def solid_drawing():
    return bd.Box(10, 10, 10)


@model
def plate():
    return bd.Box(10, 10, 2)
"""


def _raised_in_library(error: type[BaseException]) -> BaseException:
    """``error`` raised by a line of the library's own (a file in its folder, as its code is)."""
    where = str(engine_build._LIBRARY / "engine" / "owner_probe.py")
    try:
        exec(compile(f"raise {error.__name__}('probe')", where, "exec"), {})
    except BaseException as raised:  # noqa: BLE001 - the probe's own
        return raised
    raise AssertionError("the probe raised nothing")


class FailureOwnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-owner-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.script = self.folder / "parts.py"
        self.script.write_text(textwrap.dedent(SCRIPT), encoding="utf-8")

    def failed(self, name: str) -> dict:
        report = engine_build.build(self.script, [name], cwd=self.folder)[0]
        self.assertFalse(report["ok"], report)
        return report

    def test_the_model_s_own_assertion_is_the_model_s(self) -> None:
        report = self.failed("asserted")
        self.assertIn("disconnected", report["error"])
        self.assertEqual(report["owner"], "model")

    def test_a_call_the_kernel_refused_is_the_kernel_s(self) -> None:
        report = self.failed("zero")
        self.assertEqual((report["owner"], report["failedAt"]), ("kernel", "Solid.make_box(0, 60, 5)"))

    def test_build123d_s_error_reached_through_the_memo_is_its_caller_s_the_model_s(self) -> None:
        self.assertEqual(self.failed("rounded")["owner"], "model")

    def test_a_file_the_library_refuses_to_write_is_refused(self) -> None:
        report = self.failed("solid_drawing")
        self.assertIn("3D", report["error"])
        self.assertEqual(report["owner"], "refused")

    def test_a_file_that_fails_in_the_library_s_own_code_is_internal(self) -> None:
        with mock.patch.object(engine_build, "_finish", side_effect=KeyError("lost")):
            report = self.failed("plate")
        self.assertEqual(report["owner"], "internal")

    def test_a_script_that_does_not_parse_is_the_model_s(self) -> None:
        self.script.write_text("def broken(:\n", encoding="utf-8")
        report = engine_build.build(self.script, cwd=self.folder)[0]
        self.assertEqual((report["ok"], report["owner"]), (False, "model"))

    def test_the_library_s_own_raise_is_refused_for_bad_input_and_internal_otherwise(self) -> None:
        self.assertEqual(engine_build._owner(_raised_in_library(ValueError)), "refused")
        self.assertEqual(engine_build._owner(_raised_in_library(TypeError)), "refused")
        self.assertEqual(engine_build._owner(_raised_in_library(KeyError)), "internal")
        self.assertEqual(engine_build._owner(_raised_in_library(AttributeError)), "internal")


if __name__ == "__main__":
    unittest.main()
