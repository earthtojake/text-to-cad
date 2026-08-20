"""``--output`` and ``SOURCE=OUTPUT`` take a path on the USER'S disk, in their own notation.

`_resolve_cli_output_path` rejected any value containing a backslash, absolutely. On POSIX
that is a useful guard: a backslash is a legal filename character there, so a Windows-shaped
path typed on a Linux box would otherwise create a file literally named ``C:\\out.step``
instead of failing. On Windows it is the opposite of useful -- backslash IS the separator, and
``str(Path(...))`` produces one -- so every native path a Windows user could give the CLI was
refused. Found by the Windows CI job on its first run, in
``test_package_portability.setUpClass``.

The identically worded rule in :mod:`cadgen.metadata` is absolute ON PURPOSE and is asserted
here too, so a later change cannot "consistently" relax both. That one validates a path
written into a checked-in ``gen_step()`` envelope, which is read on every platform; POSIX
separators are the portable form for a file in the repository. These are two different rules
that happen to share a sentence.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.generation_spec import (  # noqa: E402
    _parse_cli_target_specs,
    _resolve_cli_output_path,
)

WINDOWS = os.name == "nt"


class CliOutputPathSeparatorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _resolve(self, raw):
        return _resolve_cli_output_path(
            raw, expected_suffixes=(".step",), tool_name="cad gen"
        )

    def test_a_native_path_is_accepted(self):
        """Whatever this platform's separator is, a path written with it must work."""
        native = str(self.root / "out.step")
        self.assertEqual((self.root / "out.step").resolve(), self._resolve(native))

    @unittest.skipUnless(WINDOWS, "backslash is only a separator on Windows")
    def test_windows_accepts_a_backslash_path(self):
        # The exact shape that failed: a drive letter and backslashes, as every Windows tool
        # produces and every Windows user types.
        resolved = self._resolve(r"C:\models\out.step")
        self.assertEqual("out.step", resolved.name)

    @unittest.skipIf(WINDOWS, "backslash is a separator here, not a suspicious filename")
    def test_posix_still_rejects_a_windows_shaped_path(self):
        with self.assertRaisesRegex(ValueError, "POSIX"):
            self._resolve(r"C:\models\out.step")

    def test_a_source_output_pair_survives_a_native_output_path(self):
        """The pair splits on the FIRST '=', so a drive letter's colon is not a hazard --
        but the output half still goes through the separator rule, which is where it died."""
        source = self.root / "widget.step.py"
        output = self.root / "exported.step"
        specs = _parse_cli_target_specs(
            [f"{source}={output}"], expected_suffixes=(".step",), tool_name="cad gen"
        )
        self.assertEqual(1, len(specs))
        self.assertEqual(str(source), specs[0].target)
        self.assertEqual(output.resolve(), specs[0].output_path)


class EnvelopePathRuleStaysAbsoluteTest(unittest.TestCase):
    """The repository-facing rule is NOT platform-conditional, on any platform."""

    def test_an_envelope_path_with_a_backslash_is_rejected_everywhere(self):
        import ast

        from cadgen.metadata import _parse_path_field

        script = Path("widget.step.py")
        envelope = {"step": ast.Constant(value=r"models\widget.step")}
        with self.assertRaisesRegex(ValueError, "POSIX"):
            _parse_path_field(
                script_path=script,
                function_name="gen_step",
                envelope=envelope,
                field_name="step",
            )


if __name__ == "__main__":
    unittest.main()
