"""One resolver derives a model's artifact path (library-first).

The retired gen/artifact CLIs each carried a private sibling-path helper and
the two disagreed on Windows separators. Library-first has exactly one:
``cadgen.metadata.resolve_model_output_path`` — sibling ``<stem>.<fmt>`` by
default, an explicit ``out=`` resolved relative to the script's own folder
(structure conventions live in the cad skill's project-layout reference as guidance, not code).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages", "cadgen", "src")

from cadgen.metadata import resolve_model_output_path  # noqa: E402


class ResolveModelOutputPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cadout-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        (self.root / "src").mkdir()
        self.script = self.root / "src" / "bracket.py"
        self.script.write_text("# model\n", encoding="utf-8")

    def test_the_default_is_the_sibling_stem(self) -> None:
        self.assertEqual(
            self.root / "src" / "bracket.step",
            resolve_model_output_path(self.script, fmt="step"),
        )
        self.assertEqual(
            self.root / "src" / "bracket.dxf",
            resolve_model_output_path(self.script, fmt="dxf"),
        )

    def test_out_resolves_relative_to_the_script_folder(self) -> None:
        # The cad skill's project-layout convention (src/ + capitalized format folders)
        # is expressed exactly this way in model code.
        self.assertEqual(
            self.root / "STEP" / "bracket.step",
            resolve_model_output_path(self.script, fmt="step", explicit_out="../STEP/bracket.step"),
        )

    def test_out_may_rename_the_artifact(self) -> None:
        # Industry exchange names (part numbers, revisions) belong on the
        # artifact via out=; the script stem stays a Python identifier.
        self.assertEqual(
            self.root / "src" / "PN-10432_revB.step",
            resolve_model_output_path(self.script, fmt="step", explicit_out="PN-10432_revB.step"),
        )

    def test_absolute_out_is_honored(self) -> None:
        target = self.root / "elsewhere" / "out.step"
        self.assertEqual(
            target,
            resolve_model_output_path(self.script, fmt="step", explicit_out=str(target)),
        )

    def test_resolution_is_independent_of_the_working_directory(self) -> None:
        import os

        cwd = Path.cwd()
        try:
            os.chdir(self.root / "src")
            from_inside = resolve_model_output_path(self.script, fmt="step", explicit_out="../STEP/bracket.step")
            os.chdir(self.root)
            from_root = resolve_model_output_path(self.script, fmt="step", explicit_out="../STEP/bracket.step")
        finally:
            os.chdir(cwd)
        self.assertEqual(from_inside, from_root)


if __name__ == "__main__":
    unittest.main()
