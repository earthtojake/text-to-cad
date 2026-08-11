"""One snapshot implementation, six front doors — so the DOOR is what has to be right.

Sharing the CLI makes every skill mechanically capable of rendering every format. The
kind gate is the only thing left keeping the CAD skill from quietly rendering a robot, so
these tests cover the gate rather than the rendering: what each skill enables, that an
input it does not enable is refused BY NAME with somewhere to go, and that the refusal
happens before anything is built.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_cli import (  # noqa: E402
    KIND_RESOLVERS,
    SnapshotError,
    enabled_kinds,
    help_text,
    input_kind,
    resolve_render_job_packet,
)

# What each skill declares. Kept here as data so a skill that quietly widens its inputs
# fails this test rather than shipping.
SKILL_KINDS = {
    "cad": ("step", "stp", "3mf", "glb", "stl"),
    "implicit-cad": ("implicit",),
    "dxf": ("dxf",),
    "urdf": ("urdf",),
    "srdf": ("srdf",),
    "sdf": ("sdf",),
}


class InputKindTests(unittest.TestCase):
    def test_compound_suffixes_are_not_read_as_their_last_one(self):
        # Path.suffix sees only `.js` and `.py`; both of these would be misread by it.
        self.assertEqual("implicit", input_kind(Path("orb.implicit.js")))
        self.assertEqual("dxf", input_kind(Path("panel.dxf.py")))
        # A plain `.py` IS a STEP generator, which is why the two need telling apart.
        self.assertEqual("python", input_kind(Path("bracket.step.py")))

    def test_every_kind_it_names_has_a_resolver_or_is_a_generator(self):
        for sample in ("a.step", "a.stp", "a.glb", "a.stl", "a.3mf", "a.implicit.js",
                       "a.urdf", "a.srdf", "a.sdf", "a.dxf"):
            kind = input_kind(Path(sample))
            self.assertTrue(kind, f"{sample} resolved to no kind")
            self.assertIn(kind, set(KIND_RESOLVERS) | {"python", "dxf"}, sample)


class EnabledKindsTests(unittest.TestCase):
    def test_enabling_step_enables_its_generator(self):
        # `.step.py` resolves as `python` before it collapses to `step`, so a skill that
        # named only "step" would reject its own generators.
        self.assertIn("python", enabled_kinds(("step",)))

    def test_a_skill_gets_only_what_it_declares(self):
        self.assertEqual({"implicit"}, set(enabled_kinds(SKILL_KINDS["implicit-cad"])))
        self.assertEqual({"urdf"}, set(enabled_kinds(SKILL_KINDS["urdf"])))

    def test_an_unknown_kind_is_a_programming_error(self):
        with self.assertRaises(SnapshotError):
            enabled_kinds(("gcode",))


class KindGateTests(unittest.TestCase):
    def _reject(self, skill: str, filename: str, body: str = "x"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "models").mkdir()
            (root / "models" / filename).write_text(body, encoding="utf-8")
            with self.assertRaises(SnapshotError) as ctx:
                resolve_render_job_packet(
                    {"input": f"models/{filename}", "outputs": [{"path": "tmp/o.png"}]},
                    cwd=root,
                    kinds=enabled_kinds(SKILL_KINDS[skill]),
                )
            return str(ctx.exception)

    def test_each_skill_refuses_the_others_formats(self):
        cases = [
            ("cad", "orb.implicit.js"),
            ("cad", "arm.urdf"),
            ("cad", "panel.dxf"),
            ("implicit-cad", "part.step"),
            ("dxf", "part.step"),
            ("urdf", "orb.implicit.js"),
        ]
        for skill, filename in cases:
            with self.subTest(skill=skill, filename=filename):
                message = self._reject(skill, filename)
                self.assertIn("does not render", message)

    def test_a_refusal_never_points_at_another_skill(self):
        # Skills install independently, so naming one assumes something we cannot know.
        for skill, filename in (("cad", "arm.urdf"), ("dxf", "orb.implicit.js")):
            with self.subTest(skill=skill):
                message = self._reject(skill, filename)
                for other in ("cad skill", "dxf skill", "implicit-cad skill", "urdf skill"):
                    self.assertNotIn(other, message, message)

    def test_the_refusal_lists_what_this_skill_does_take(self):
        # A bare "no" makes the reader go read the source; the accepted set is the answer.
        message = self._reject("cad", "orb.implicit.js")
        self.assertIn(".step", message)
        self.assertIn(".stl", message)

    def test_a_step_generator_is_gated_as_step_not_as_python(self):
        # `.step.py` is rewritten to its logical `.step` path. Gating after that rewrite
        # would report a path the caller never named.
        message = self._reject("implicit-cad", "bracket.step.py", body="def gen_step(): ...")
        self.assertIn("bracket.step.py", message)


class GeneratedHelpTests(unittest.TestCase):
    def test_help_describes_only_this_skill(self):
        implicit_help = help_text(kinds=enabled_kinds(SKILL_KINDS["implicit-cad"]))
        self.assertIn(".implicit.js", implicit_help)
        for absent in (".step", ".urdf", "--params", "--focus"):
            self.assertNotIn(absent, implicit_help, f"{absent} is not this skill's business")

    def test_step_only_options_appear_for_the_cad_skill(self):
        cad_help = help_text(kinds=enabled_kinds(SKILL_KINDS["cad"]))
        for present in ("--params", "--focus", "section", "--view-labels"):
            self.assertIn(present, cad_help)

    def test_theme_is_one_option_everywhere(self):
        for skill, kinds in SKILL_KINDS.items():
            with self.subTest(skill=skill):
                text = help_text(kinds=enabled_kinds(kinds))
                self.assertIn("--theme", text)
                self.assertNotIn("--appearance", text)

    def test_display_is_offered_only_where_it_does_something(self):
        # Display settings ARE STEP topology settings -- mode, clip, exploded and edges all
        # need occurrences and CAD edges -- and every non-STEP resolver rejected all four.
        # Advertising the flag everywhere meant advertising an option that only errors.
        self.assertIn("--display", help_text(kinds=enabled_kinds(SKILL_KINDS["cad"])))
        for skill in ("dxf", "implicit-cad", "urdf", "srdf", "sdf"):
            with self.subTest(skill=skill):
                self.assertNotIn("--display", help_text(kinds=enabled_kinds(SKILL_KINDS[skill])))


if __name__ == "__main__":
    unittest.main()
