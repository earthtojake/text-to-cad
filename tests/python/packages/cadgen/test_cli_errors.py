"""A CAD CLI failure has to lead with the failure, and name the caller's own code.

Before this, an uncaught generator exception reached the interpreter: a `gen_step()` that
raised printed a 62-line traceback whose only useful line was last, and one missing its
return printed 43 lines to say "must return one value". Both are ordinary authoring
mistakes, so both are what an agent hits most.
"""

from __future__ import annotations

import io
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.cli_errors import report_cli_error  # noqa: E402


def _raise_from_model(model: Path) -> BaseException:
    """Run a throwaway generator from ``model`` so the traceback carries its frames."""
    namespace: dict[str, object] = {}
    code = compile(model.read_text(), str(model), "exec")
    try:
        exec(code, namespace)  # noqa: S102 - the fixture IS a model source
        namespace["gen_step"]()
    except Exception as exc:  # noqa: BLE001
        return exc
    raise AssertionError("fixture did not raise")


class ReportCliErrorTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.root, True)
        self.model = self.root / "widget.step.py"
        self.model.write_text(
            "def _inner():\n"
            "    raise ValueError('bad radius')\n"
            "\n"
            "\n"
            "def gen_step():\n"
            "    return _inner()\n"
        )

    def _report(self, exc, **kwargs) -> str:
        stream = io.StringIO()
        code = report_cli_error(exc, tool="scripts/gen", stream=stream, **kwargs)
        self.assertEqual(1, code, "a reported failure is still a failure")
        return stream.getvalue()

    def test_it_leads_with_the_failure(self):
        text = self._report(_raise_from_model(self.model))
        self.assertTrue(
            text.splitlines()[0].endswith("FAILED: ValueError: bad radius"),
            f"the failure must be the FIRST line, got: {text.splitlines()[0]!r}",
        )

    def test_it_names_the_models_own_frames(self):
        text = self._report(_raise_from_model(self.model))
        self.assertIn("widget.step.py:6 in gen_step", text)
        self.assertIn("widget.step.py:2 in _inner", text)

    def test_it_drops_the_runtime_frames(self):
        # A model that fails INSIDE cadgen: the traceback carries a cadgen frame, and the
        # report must not. Those frames are identical in every failure and say nothing
        # about which model broke -- they are the ~50 lines this reporter exists to remove.
        self.model.write_text(
            "from cadgen.metadata import normalize_mesh_numeric\n"
            "\n"
            "\n"
            "def gen_step():\n"
            "    return normalize_mesh_numeric(-1, field_name='mesh_tolerance')\n"
        )
        text = self._report(_raise_from_model(self.model))
        self.assertIn("widget.step.py:5 in gen_step", text, "the model's frame is kept")
        self.assertNotIn("metadata.py", text, "a cadgen frame is runtime, not the model")
        self.assertLess(len(text.splitlines()), 10, "a compact report stays compact")

    def test_verbose_restores_the_full_traceback(self):
        text = self._report(_raise_from_model(self.model), verbose=True)
        self.assertIn("Traceback (most recent call last)", text)
        self.assertIn("test_cli_errors.py", text, "internal frames are the point of --verbose")

    def test_a_failure_with_no_model_frames_still_names_where_it_came_from(self):
        # A validation error raised before the generator ever ran, so every frame is
        # runtime. The message already names the model; the report points at the raiser so
        # a cadgen-side fault is still diagnosable without --verbose.
        import cadgen._internal.cli_errors as cli_errors

        original = cli_errors.__dict__.get("_model_frames")
        self.addCleanup(lambda: cli_errors.__dict__.__setitem__("_model_frames", original))
        cli_errors._model_frames = lambda exc: []
        try:
            raise ValueError("widget.step.py gen_step() must return one value")
        except ValueError as exc:
            text = self._report(exc)
        self.assertIn("must return one value", text)
        self.assertIn("raised in", text)
        self.assertLess(len(text.splitlines()), 5)

    def test_an_exception_that_was_never_raised_still_reports(self):
        # Defensive: a caller may report a constructed exception with no traceback at all.
        text = self._report(ValueError("no traceback here"))
        self.assertIn("FAILED: ValueError: no traceback here", text)


if __name__ == "__main__":
    unittest.main()
