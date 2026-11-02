"""Whether a failed build is cadgen's to fix, for its page to offer Report Issue (``daemon._reportable``):
telemetry's rule for a build's crash (``analytics.told_signature``) read from the report's error -- by its
class first (``cad.engine.errors``: ``owner``), else by its whole traceback kept as facts (``build._raised``).
Real builds, in this process."""

from __future__ import annotations

import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import build as engine_build
from cad.engine.errors import InternalError
from cad_server import analytics
from cad_server.engine import daemon

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


@model
def mistyped():
    return bd.Box(10, 10, 10).fillet(1, "edges")


@model
def refused_by_the_person():
    from cad.engine.errors import UserError

    raise UserError("the person's own refusal, raised where cadgen's code would be")


@dxf("plate.dxf")
def solid_drawing():
    return bd.Box(10, 10, 10)


@model
def plate():
    return bd.Box(10, 10, 2)
"""


class FailureReportableTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="engine-reportable-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.script = self.folder / "parts.py"
        self.script.write_text(textwrap.dedent(SCRIPT), encoding="utf-8")

    def failed(self, name: str | None) -> dict:
        report = engine_build.build(self.script, [name] if name else None, cwd=self.folder)[0]
        self.assertFalse(report["ok"], report)
        return report

    def test_the_model_s_own_errors_are_not_reportable(self) -> None:
        asserted = self.failed("asserted")  # the shape of #742: the model's own assert
        self.assertIn("disconnected", asserted["error"])
        self.assertEqual(asserted["raised"]["type"], "AssertionError")
        self.assertFalse(daemon._reportable(asserted))
        zero = self.failed("zero")  # the kernel refused a call
        self.assertEqual(zero["failedAt"], "Solid.make_box(0, 60, 5)")
        self.assertFalse(daemon._reportable(zero))
        self.assertFalse(daemon._reportable(self.failed("rounded")))  # build123d's ValueError, through the memo
        mistyped = self.failed("mistyped")  # what build123d raised for what the model gave it
        self.assertFalse(daemon._reportable(mistyped), mistyped["raised"])
        refused = self.failed("solid_drawing")  # cadgen refusing what it was given (``ExportRefused``)
        self.assertIn("3D", refused["error"])
        self.assertEqual(refused["raised"]["owner"], "user")  # by its class: a ``UserError``
        self.assertFalse(daemon._reportable(refused))
        self.assertEqual(self.failed("refused_by_the_person")["raised"]["owner"], "user")
        self.assertFalse(daemon._reportable(self.failed("refused_by_the_person")))
        self.script.write_text("def broken(:\n", encoding="utf-8")
        self.assertFalse(daemon._reportable(self.failed(None)))  # a script that does not parse

    def test_a_mistake_in_cadgen_s_own_code_is_reportable(self) -> None:
        with mock.patch.object(engine_build, "_finish", side_effect=KeyError("lost")):
            report = self.failed("plate")
        self.assertEqual(report["raised"]["type"], "KeyError")
        self.assertNotIn("owner", report["raised"])  # no ``CadError``: the frame rule decides
        self.assertTrue(daemon._reportable(report))

    def test_an_internal_error_is_reportable_whatever_its_frames_and_named_in_telemetry(self) -> None:
        # Raised from the mock's own frame, the standard library's: the frame rule alone would not tell.
        with mock.patch.object(engine_build, "_finish", side_effect=InternalError("an impossible state")):
            report = self.failed("plate")
        self.assertEqual(report["raised"]["owner"], "ours")
        self.assertTrue(daemon._reportable(report))
        from cad.engine.api import told_error

        crash = analytics.told_signature(told_error(report), "build")
        self.assertEqual(crash["type"], "cad.engine.errors.InternalError")

    def test_the_page_s_record_carries_it_and_a_worker_that_died_is_reportable(self) -> None:
        server = mock.Mock()
        engine = mock.Mock(server=server)
        engine.models.paths.side_effect = lambda _worker, model: [f"id:{model}"] if model else []
        asserted = {**self.failed("asserted"), "model": "parts.py::asserted"}
        daemon.Daemon._built(engine, mock.Mock(progress={"job": "parts.py::plate"}), {"done": {"reports": [asserted]}})
        self.assertIs(server.built.call_args.args[0]["id:parts.py::asserted"]["reportable"], False)
        daemon.Daemon._built(engine, mock.Mock(progress={"job": "parts.py::plate"}), {"failed": "the worker exited (-11)"})
        self.assertIs(server.built.call_args.args[0]["id:parts.py::plate"]["reportable"], True)


if __name__ == "__main__":
    unittest.main()
