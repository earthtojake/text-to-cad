"""A generated CLI's failure has to lead with the failure, and name where it was raised.

An uncaught exception would reach the interpreter as a long traceback whose only useful line
is last. The report is the failure, the frame that raised it, and the hint to re-run with
``--verbose`` where the command takes it.
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
    code = compile(model.read_text(encoding="utf-8"), str(model), "exec")
    try:
        exec(code, namespace)  # noqa: S102 - the fixture IS a model source
        namespace["model"]()
    except Exception as exc:  # noqa: BLE001
        return exc
    raise AssertionError("fixture did not raise")


class ReportCliErrorTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.root, True)
        self.model = self.root / "widget.py"
        self.model.write_text(
            "def _inner():\n"
            "    raise ValueError('bad radius')\n"
            "\n"
            "\n"
            "def model():\n"
            "    return _inner()\n", encoding="utf-8"
        )

    def _report(self, exc, **kwargs) -> str:
        stream = io.StringIO()
        code = report_cli_error(exc, tool="cadgen urdf validate", stream=stream, **kwargs)
        self.assertEqual(1, code, "a reported failure is still a failure")
        return stream.getvalue()

    def test_it_leads_with_the_failure(self):
        text = self._report(_raise_from_model(self.model))
        self.assertTrue(
            text.splitlines()[0].endswith("FAILED: ValueError: bad radius"),
            f"the failure must be the FIRST line, got: {text.splitlines()[0]!r}",
        )

    def test_it_names_where_it_was_raised_and_stays_compact(self):
        text = self._report(_raise_from_model(self.model))
        self.assertIn("raised in", text)
        self.assertIn("widget.py:2", text, "the innermost frame: the one that raised")
        self.assertLess(len(text.splitlines()), 5, "a compact report stays compact")

    def test_verbose_restores_the_full_traceback(self):
        text = self._report(_raise_from_model(self.model), verbose=True)
        self.assertIn("Traceback (most recent call last)", text)
        self.assertIn("test_cli_errors.py", text, "internal frames are the point of --verbose")

    def test_an_exception_that_was_never_raised_still_reports(self):
        # Defensive: a caller may report a constructed exception with no traceback at all.
        text = self._report(ValueError("no traceback here"))
        self.assertIn("FAILED: ValueError: no traceback here", text)

    def test_a_failure_with_no_message_is_named_by_its_type_and_where_it_was_raised(self):
        """A bare ``assert`` in the kernel says nothing: the one-line text a ``--json``
        envelope carries names the type and the raiser instead of an empty string."""
        from cadgen._internal.cli_errors import failure_text

        self.model.write_text("def model():\n    assert False\n", encoding="utf-8")
        text = failure_text(_raise_from_model(self.model))
        self.assertRegex(text, r"^AssertionError \(raised in .*widget\.py:2\)$")
        self.assertEqual(failure_text(ValueError("bad radius")), "bad radius")
        self.assertEqual(failure_text(AssertionError()), "AssertionError")

    def test_the_hint_is_offered_when_the_command_takes_the_flag(self):
        self.assertIn("re-run with --verbose", self._report(_raise_from_model(self.model)))

    def test_the_hint_is_dropped_when_the_command_has_no_such_flag(self):
        # `--verbose` exists only where the verb declares a `verbose` parameter (the
        # snapshot doors do not). Telling an agent to re-run with a flag that command
        # refuses costs it a failed invocation.
        text = self._report(_raise_from_model(self.model), verbose_hint=False)
        self.assertNotIn("--verbose", text)
        self.assertIn("FAILED: ValueError: bad radius", text)


class VerboseHintFollowsTheParserTest(unittest.TestCase):
    """The generated CLI decides the hint from the verb's own signature."""

    def _run(self, func) -> str:
        import contextlib

        from cadgen._internal.cli_from_function import run_cli

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = run_cli(func, [], prog="cadgen fake door", stdout=io.StringIO())
        self.assertEqual(1, code)
        return stderr.getvalue()

    def test_a_verb_without_verbose_gets_no_verbose_hint(self):
        def snapshot() -> object:
            """A door with no verbose parameter, so its CLI has no --verbose."""
            raise ValueError("boom")

        text = self._run(snapshot)
        self.assertIn("FAILED: ValueError: boom", text)
        self.assertNotIn("--verbose", text)

    def test_a_verb_with_verbose_keeps_the_hint(self):
        def build(*, verbose: bool = False) -> object:
            """A door that does take --verbose."""
            raise ValueError("boom")

        self.assertIn("re-run with --verbose", self._run(build))


if __name__ == "__main__":
    unittest.main()
