"""One snapshot implementation, one front door per FORMAT — so the door is what has to
be right.

Sharing the CLI makes every door mechanically capable of rendering every format. The
kind gate is the only thing left keeping `step snapshot` from quietly rendering a robot,
so these tests cover the gate rather than the rendering: what each door enables, that an
input it does not enable is refused BY NAME with somewhere to go, and that the refusal
happens before anything is built.

The mesh formats are the newest doors. `cadgen step snapshot` used to render `.stl`,
`.3mf` and `.glb` as well as STEP, which made one door the door for four formats; the
mesh arm moved to `cadgen stl|3mf|glb snapshot` unchanged. That cutover is what the
`MeshDoorSplit` cases pin: the STEP door refuses a mesh and says where it went, and each
mesh door takes its own format and nothing else.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.snapshot_door import ALL_KINDS  # noqa: E402
from cadgen._internal.snapshot_door import DOOR_KINDS as DECLARED_DOOR_KINDS  # noqa: E402
from cadgen.snapshot_cli import (  # noqa: E402
    KIND_RESOLVERS,
    SnapshotError,
    enabled_kinds,
    input_kind,
    resolve_render_job_packet,
)

# The command module behind each door, so the help assertions below read the
# text that actually ships rather than a parser rebuilt in the test.
DOOR_COMMANDS = {
    "step": "cadgen.cli.step_snapshot",
    "stl": "cadgen.cli.stl_snapshot",
    "3mf": "cadgen.cli.threemf_snapshot",
    "glb": "cadgen.cli.glb_snapshot",
    "dxf": "cadgen.cli.dxf_snapshot",
    "urdf": "cadgen.cli.urdf_snapshot",
    "sdf": "cadgen.cli.sdf_snapshot",
}


def door_help(door: str) -> str:
    """One door's real ``--help``, generated from its verb's signature."""
    import importlib

    return importlib.import_module(DOOR_COMMANDS[door]).build_parser().format_help()

# What each door declares. Written out rather than imported so a door that quietly
# widens its inputs fails HERE rather than shipping; the declaration itself is
# checked against this below.
DOOR_KINDS = {
    "step": ("step", "stp"),
    "stl": ("stl",),
    "3mf": ("3mf",),
    "glb": ("glb",),
    "dxf": ("dxf",),
    "urdf": ("urdf",),
    "srdf": ("srdf",),
    "sdf": ("sdf",),
}

MESH_DOORS = ("stl", "3mf", "glb")


class InputKindTests(unittest.TestCase):
    def test_a_script_classifies_as_python_whatever_it_declares(self):
        # DOCUMENTS-ONLY: every `.py` is one kind, because the resolver's only
        # use for it is refusing it by naming the run. Which format the script
        # declares no longer matters — nothing downstream will render it.
        for sample in ("panel.dxf.py", "panel.py", "bracket.py"):
            with self.subTest(sample=sample):
                self.assertEqual("python", input_kind(Path(sample)))

    def test_every_kind_it_names_has_a_resolver_or_is_a_generator(self):
        for sample in ("a.step", "a.stp", "a.glb", "a.stl", "a.3mf",
                       "a.urdf", "a.srdf", "a.sdf", "a.dxf"):
            kind = input_kind(Path(sample))
            self.assertTrue(kind, f"{sample} resolved to no kind")
            self.assertIn(kind, set(KIND_RESOLVERS) | {"python", "dxf"}, sample)


class EnabledKindsTests(unittest.TestCase):
    def test_the_declaration_is_what_this_file_says_it_is(self):
        self.assertEqual(DOOR_KINDS, DECLARED_DOOR_KINDS)

    def test_the_polymorphic_door_is_every_door_at_once(self):
        # `cadgen snapshot` routes by suffix, so it must be the union: a kind
        # reachable through no door at all would be unrenderable.
        self.assertEqual(
            {kind for kinds in DOOR_KINDS.values() for kind in kinds}, set(ALL_KINDS)
        )

    def test_a_declared_kind_enables_exactly_itself(self):
        # There is nothing left to expand: `.py` inputs are refused outright,
        # so a door's declared kinds ARE the set it accepts.
        self.assertEqual({"step", "stp"}, set(enabled_kinds(DOOR_KINDS["step"])))

    def test_a_door_gets_only_what_it_declares(self):
        self.assertEqual({"dxf"}, set(enabled_kinds(DOOR_KINDS["dxf"])))
        self.assertEqual({"urdf"}, set(enabled_kinds(DOOR_KINDS["urdf"])))
        self.assertEqual({"stl"}, set(enabled_kinds(DOOR_KINDS["stl"])))

    def test_an_unknown_kind_is_a_programming_error(self):
        with self.assertRaises(SnapshotError):
            enabled_kinds(("gcode",))


class _Gate(unittest.TestCase):
    """Shared refusal helper. Not a case of its own — subclasses are the tests."""

    def _reject(self, door: str, filename: str, body: str = "x"):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "models").mkdir()
            (root / "models" / filename).write_text(body, encoding="utf-8")
            with self.assertRaises(SnapshotError) as ctx:
                resolve_render_job_packet(
                    {"input": f"models/{filename}", "outputs": [{"path": "tmp/o.png"}]},
                    cwd=root,
                    kinds=enabled_kinds(DOOR_KINDS[door]),
                )
            return str(ctx.exception)


class KindGateTests(_Gate):
    def test_each_door_refuses_the_others_formats(self):
        cases = [
            ("step", "arm.urdf"),
            ("step", "panel.dxf"),
            ("dxf", "part.step"),
            ("urdf", "panel.dxf"),
            ("sdf", "part.step"),
            ("stl", "part.step"),
            ("glb", "mesh.stl"),
        ]
        for door, filename in cases:
            with self.subTest(door=door, filename=filename):
                message = self._reject(door, filename)
                self.assertIn("does not render", message)

    def test_a_refusal_never_points_at_another_skill(self):
        # Skills install independently, so naming one assumes something we cannot know.
        # A sibling cadgen COMMAND is a different matter -- see MeshDoorSplit below.
        for door, filename in (("step", "arm.urdf"), ("dxf", "part.step")):
            with self.subTest(door=door):
                message = self._reject(door, filename)
                for other in ("cad skill", "dxf skill", "urdf skill", "sdf skill"):
                    self.assertNotIn(other, message, message)

    def test_the_refusal_lists_what_this_door_does_take(self):
        # A bare "no" makes the reader go read the source; the accepted set is the answer.
        message = self._reject("step", "arm.urdf")
        self.assertIn(".step", message)
        self.assertIn(".stp", message)

    def test_a_step_generator_is_gated_as_step_not_as_python(self):
        # `.py` is rewritten to its logical `.step` path. Gating after that rewrite
        # would report a path the caller never named.
        message = self._reject("urdf", "bracket.py", body="def model(): ...")
        self.assertIn("bracket.py", message)


class MeshDoorSplit(_Gate):
    """`cadgen step snapshot` accepts ONLY STEP; meshes have doors of their own.

    The STEP door rendered meshes until this split, so its refusal has to TEACH
    rather than just refuse: a caller arriving with a `.stl` is following
    instructions that used to be right.
    """

    def test_the_step_door_refuses_every_mesh_format(self):
        for fmt, filename in (("stl", "part.stl"), ("3mf", "part.3mf"), ("glb", "part.glb")):
            with self.subTest(format=fmt):
                message = self._reject("step", filename)
                self.assertIn("does not render", message)
                # The whole point of naming the door is that the reader can
                # RUN it, so the form quoted has to be the form that parses:
                # snapshot takes its target and output positionally.
                self.assertIn(f"cadgen {fmt} snapshot TARGET OUT", message)
                self.assertNotIn("--input", message)

    def test_a_mesh_door_takes_its_own_format_and_no_other(self):
        for fmt in MESH_DOORS:
            with self.subTest(format=fmt):
                self.assertEqual({fmt}, set(enabled_kinds(DOOR_KINDS[fmt])))

    def test_each_mesh_door_is_a_registered_command(self):
        from cadgen import cli

        for fmt in MESH_DOORS:
            with self.subTest(format=fmt):
                self.assertIn(f"{fmt} snapshot", cli._COMMANDS)

    def test_a_mesh_door_advertises_its_own_format_only(self):
        for fmt in MESH_DOORS:
            with self.subTest(format=fmt):
                text = door_help(fmt)
                self.assertIn(f".{fmt}", text)
                for absent in (".step", ".urdf", "--kinematics", "--animation", "--focus"):
                    self.assertNotIn(absent, text, f"{absent} is not a mesh door's business")


class GeneratedHelpTests(unittest.TestCase):
    """The help is the SIGNATURE now.

    Each door's `--help` is derived from the verb it calls, so an option a
    format cannot act on is not merely undocumented — it does not exist on that
    command. The doors used to share one signature and one hand-written help
    blob filtered per kind, which meant the filtering could disagree with the
    parser: a display option could parse and then fail only after kind resolution.
    """

    def test_help_describes_only_this_door(self):
        dxf_help = door_help("dxf")
        self.assertIn(".dxf", dxf_help)
        for absent in (".step", ".urdf", "--kinematics", "--animation", "--time", "--focus"):
            self.assertNotIn(absent, dxf_help, f"{absent} is not this door's business")

    def test_step_only_options_appear_for_the_step_door(self):
        step_help = door_help("step")
        for present in ("--kinematics", "--animation", "--time", "--focus", "section", "--view-labels"):
            self.assertIn(present, step_help)

    def test_display_is_the_one_view_option_everywhere(self):
        for door in DOOR_COMMANDS:
            with self.subTest(door=door):
                text = door_help(door)
                self.assertIn("--display", text)
                self.assertNotIn("--render", text)
                self.assertNotIn("--theme", text)
                self.assertNotIn("--appearance", text)

    def test_every_door_takes_its_target_and_output_positionally(self):
        # One grammar across the schema: `cadgen <fmt> build TARGET [OUT]` and
        # `cadgen <fmt> snapshot TARGET [OUT]` read the same way.
        for door in DOOR_COMMANDS:
            with self.subTest(door=door):
                text = door_help(door)
                self.assertIn("[TARGET] [OUT]", text)
                self.assertNotIn("--input", text)
                self.assertNotIn("--output", text)

    def test_format_neutral_display_is_offered_everywhere(self):
        for door in DOOR_COMMANDS:
            with self.subTest(door=door):
                self.assertIn("--display", door_help(door))

    def test_joint_values_is_offered_only_to_the_robot_doors(self):
        for door in ("urdf", "sdf"):
            with self.subTest(door=door):
                self.assertIn("--joint-values", door_help(door))
        for door in ("step", "stl", "3mf", "glb", "dxf"):
            with self.subTest(door=door):
                self.assertNotIn("--joint-values", door_help(door))


if __name__ == "__main__":
    unittest.main()
