from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from build123d import Box, Compound, Location  # noqa: E402

from cadgen.step_export import build_build123d_step_scene  # noqa: E402
from cadgen._internal.step_scene_loader import _normalize_label_name  # noqa: E402


class UnnamedLabelSceneTests(unittest.TestCase):
    """A shape whose XCAF labels are not all named must still build a scene.

    This is a SEGFAULT regression, not a wrong-answer one, so there is nothing to assert
    against on failure -- the process dies with SIGSEGV and no traceback, and the test run
    reports a crashed worker. TDF_Label.FindAttribute does not return false for an absent
    attribute in this OCP build; it dereferences null. _label_name now asks IsAttribute first.

    A plain ``Compound(children=[...])`` is the shape that produces unnamed labels: XCAF makes
    a child label per solid, and nothing names them unless the model was authored through
    AssemblyHelper. Both spellings are covered here because only the unnamed one ever crashed,
    and a fix that quietly stopped reading real names would pass the unnamed case alone.
    """

    def _build(self, shape):
        with tempfile.TemporaryDirectory() as directory:
            return build_build123d_step_scene(shape, Path(directory) / "scene.step")

    def _grid(self, count: int):
        return [Location((index * 30.0, 0.0, 0.0)) * Box(20, 20, 10) for index in range(count)]

    def test_compound_of_unnamed_solids_builds(self) -> None:
        scene = self._build(Compound(children=self._grid(3)))
        self.assertIsNotNone(scene)

    def test_named_labels_still_resolve(self) -> None:
        children = self._grid(2)
        for index, child in enumerate(children):
            child.label = f"block_{index}"
        scene = self._build(Compound(children=children))
        self.assertIsNotNone(scene)

    def test_single_unnamed_solid_builds(self) -> None:
        scene = self._build(Box(20, 20, 10))
        self.assertIsNotNone(scene)

    def test_vendor_unicode_label_spellings_normalize_to_authored_text(self) -> None:
        escaped = r"\X2\51F853F0\X0\-\X2\62C94F38\X0\4_1_2_3_4"
        mojibake = "å\x9c\x86è§\x922_1_2"
        self.assertEqual(_normalize_label_name(escaped), "凸台-拉伸4_1_2_3_4")
        self.assertEqual(_normalize_label_name(mojibake), "圆角2_1_2")
        self.assertEqual(_normalize_label_name(r"\X4\0001F680\X0\ mount"), "🚀 mount")
        self.assertEqual(_normalize_label_name("café Ã©"), "café Ã©")
        self.assertEqual(_normalize_label_name("bracket"), "bracket")


if __name__ == "__main__":
    unittest.main()
