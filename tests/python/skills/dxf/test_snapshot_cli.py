"""What `cadgen dxf snapshot` accepts, and what it refuses BY NAME.

Job resolution is shared (`cadgen.snapshot_cli`); this door is a GENERATED CLI
over `cadgen.dxf.snapshot` (`cadgen.cli.dxf_snapshot`), and which input kinds it
takes is declared beside the verb. What is DXF-specific is the SURFACE, and that
is what these tests cover.

A DXF is drawn as a flat 2D drawing — the same picture, from the same payload,
with the same code as the CAD Viewer's DXF pane. It has no camera, display
settings, render mode or view label, and both surfaces say so:

* the verb's SIGNATURE takes none of them, so `--camera`, `--display`, `--mode`
  and `--view-labels` are out of `--help`, and argparse refuses each as an
  unrecognized argument;
* the shared per-kind check refuses them by name, so a `--job` file — and
  `cadgen snapshot`, which routes a `.dxf` through the same check — is told what
  a drawing is instead of being rendered as if the request had not been made.

The pixels are `test_snapshot_render.py`.
"""

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path

from cadgen.assets import browser_runtime_dir

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

import cadgen.snapshot_cli as snapshot
from cadgen._internal.snapshot_door import (
    DOOR_KINDS,
    drawing_camera_refusal,
    drawing_mode_refusal,
)

DXF_KINDS = snapshot.enabled_kinds(DOOR_KINDS["dxf"])
ALL_KINDS = snapshot.enabled_kinds(("step", "stp", "dxf", "glb", "stl", "3mf", "urdf", "srdf", "sdf"))


class DxfSnapshotRefusalTests(unittest.TestCase):
    """Every option that only ever meant something for the 3D flat pattern."""

    def setUp(self) -> None:
        self.temporary = temporary_directory(prefix="dxf-snapshot-cli-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        # Preparation decides every refusal below, and never opens the file: a
        # stub is enough, and keeps these tests off ezdxf entirely.
        (self.root / "a.dxf").write_text("0\nSECTION\n", encoding="utf-8")

    def prepare(self, job, *, kinds=None):
        return snapshot.prepare_render_job_packet(job, cwd=self.root, kinds=kinds or DXF_KINDS)

    def refuses(self, job, pattern, *, kinds=None):
        with self.assertRaisesRegex(snapshot.SnapshotError, pattern):
            self.prepare(job, kinds=kinds)

    def job(self, **overrides):
        return {"input": "a.dxf", "outputs": [{"path": "a.png"}], **overrides}

    def test_display_settings_describe_a_scene_a_drawing_does_not_have(self) -> None:
        for display in (
            {"mode": "render"},
            {"mode": "hidden-line"},
            {"surfaces": {"style": "flat"}},
            {"lighting": {"enabled": True}},
            {"floor": {"enabled": True}},
            {"background": {"color": "#112233"}},
            {"camera": {"projection": "perspective"}},
            {"edges": {"enabled": True}},
            {"clip": {"enabled": True}},
            {"exploded": {"amount": 0.5}},
            {"grid": {"enabled": True}},
            {"axes": {"enabled": True}},
        ):
            with self.subTest(display=display):
                self.refuses(self.job(display=display), r"describes? a 3D scene")

    def test_the_refusal_names_the_setting_and_the_flag_that_replaces_it(self) -> None:
        with self.assertRaises(snapshot.SnapshotError) as raised:
            self.prepare(self.job(display={"mode": "render", "floor": {"enabled": True}}))
        message = str(raised.exception)
        self.assertIn("display.floor, display.mode", message)
        self.assertIn("a.dxf", message)
        self.assertIn("--appearance light|dark", message)

    def test_appearance_is_the_one_display_setting_that_survives(self) -> None:
        single, prepared = self.prepare(self.job(display={"appearance": "dark"}))
        self.assertTrue(single)
        self.assertEqual("dark", prepared[0].job["display"]["appearance"])

    def test_a_camera_poses_a_model_and_a_drawing_is_not_posed(self) -> None:
        self.refuses(self.job(camera="top"), r"camera poses a model in space")
        self.refuses(
            self.job(outputs=[{"path": "a.png", "camera": "iso"}]),
            r"camera poses a model in space",
        )

    def test_the_job_refusal_is_the_drawing_sentence_naming_the_file(self) -> None:
        for job, sentence in (
            (self.job(camera="top"), drawing_camera_refusal("a.dxf")),
            (self.job(mode="list", outputs=[]), drawing_mode_refusal("a.dxf")),
        ):
            with self.subTest(sentence=sentence):
                with self.assertRaises(snapshot.SnapshotError) as raised:
                    self.prepare(job)
                self.assertEqual(sentence, str(raised.exception))

    def test_view_is_the_only_mode_a_drawing_renders_in(self) -> None:
        # `list` reports a model's renderable parts; a drawing has none.
        self.refuses(self.job(mode="list", outputs=[]), r"no parts to list, so view is the only mode")

    def test_scene_scale_means_nothing_to_a_drawing(self) -> None:
        self.refuses(self.job(scale="urdf"), r"scale picks the units a 3D scene")

    def test_output_settings_that_frame_a_camera_are_refused_by_name(self) -> None:
        for key, value, reason in (
            ("viewLabels", True, r"no camera, so there is no view name"),
            ("padding", 0.1, r"fixed gutter the viewer leaves"),
            ("tightFrame", True, r"already framed on the bounds"),
        ):
            with self.subTest(setting=key):
                self.refuses(self.job(output={key: value}), reason)

    def test_an_output_cannot_name_a_view_it_does_not_have(self) -> None:
        for key in ("label", "viewLabel"):
            with self.subTest(key=key):
                self.refuses(
                    self.job(outputs=[{"path": "a.png", key: "FRONT"}]),
                    r"names the view burnt into the image",
                )

    def test_output_settings_a_drawing_keeps(self) -> None:
        single, prepared = self.prepare(
            self.job(output={"sizeProfile": "simple", "renderScale": 2, "transparent": True})
        )
        self.assertTrue(single)
        settings = prepared[0].job["output"]
        self.assertEqual(2, settings["renderScale"])
        self.assertTrue(settings["transparent"])
        output = prepared[0].job["outputs"][0]
        self.assertEqual((1200, 900), (output["width"], output["height"]))

    def test_the_refusals_every_non_step_input_shares_still_apply(self) -> None:
        for job, pattern in (
            (self.job(kinematics={"lift": 10}), r"kinematics values require a STEP model"),
            (self.job(jointValues={"j1": 10}), r"jointValues pose a robot description"),
            (self.job(animation={"clip": "open"}), r"an animation frame requires a STEP document"),
            (self.job(selection={"focus": ["#o1"]}), r"selection focus/hide require STEP topology"),
        ):
            with self.subTest(keys=sorted(set(job) - {"input", "outputs"})):
                self.refuses(job, pattern)

    def test_the_polymorphic_door_routes_a_drawing_through_the_same_check(self) -> None:
        # `cadgen snapshot` accepts a camera and a display for the STEP it may
        # also be handed; a .dxf in the same packet still gets the drawing's
        # answer rather than a 3D render nobody could reproduce in the viewer.
        self.refuses(self.job(camera="top"), r"camera poses a model in space", kinds=ALL_KINDS)
        self.refuses(self.job(display={"mode": "render"}), r"describes? a 3D scene", kinds=ALL_KINDS)

    def test_a_non_drawing_input_is_refused_by_what_it_is(self) -> None:
        (self.root / "part.step").write_text("ISO-10303-21;\n", encoding="utf-8")
        self.refuses(
            {"input": "part.step", "outputs": [{"path": "a.png"}]},
            r"snapshot does not render \.step inputs",
        )

    def test_a_script_is_not_a_snapshot_input(self) -> None:
        # Drawings are made by running their script; snapshot renders the DOCUMENT.
        (self.root / "x.py").write_text("def drawing():\n    ...\n", encoding="utf-8")
        self.refuses({"input": "x.py", "outputs": [{"path": "a.png"}]}, r"x\.py")


class DrawingPayloadFileTests(unittest.TestCase):
    """The resolver's half: the `.dxf`'s 2D payload, on a path the page fetches."""

    def setUp(self) -> None:
        self.temporary = temporary_directory(prefix="dxf-payload-file-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_rejects_a_non_drawing_input(self) -> None:
        with self.assertRaisesRegex(snapshot.SnapshotError, r"must be a \.dxf document"):
            snapshot.drawing_payload_file(self.root / "part.step")

    def test_reports_a_missing_input(self) -> None:
        with self.assertRaisesRegex(snapshot.SnapshotError, r"does not exist"):
            snapshot.drawing_payload_file(self.root / "definitely-absent.dxf")

    def test_an_unreadable_drawing_is_an_error_not_a_blank_image(self) -> None:
        # The payload reader's own words, moved onto the snapshot error type:
        # they already name the file and what to do about it.
        broken = self.root / "broken.dxf"
        broken.write_text("this is not a DXF at all\n", encoding="utf-8")
        with self.assertRaisesRegex(snapshot.SnapshotError, r"broken\.dxf is not a readable DXF"):
            snapshot.drawing_payload_file(broken)

    def test_the_payload_is_written_once_and_named_by_its_content(self) -> None:
        import ezdxf

        document = ezdxf.new("R2010")
        document.header["$INSUNITS"] = 4
        document.modelspace().add_line((0, 0), (10, 0))
        source = self.root / "line.dxf"
        document.saveas(source)

        first = snapshot.drawing_payload_file(source)
        self.assertTrue(first.is_file())
        self.assertEqual(".json", first.suffix)
        # A second resolve of the same bytes reuses the same file: the payload is
        # content-addressed, so nothing re-enters ezdxf and nothing is rewritten.
        self.assertEqual(first, snapshot.drawing_payload_file(source))


class DxfSnapshotDoorSurfaceTests(unittest.TestCase):
    def test_help_names_a_drawing_and_offers_no_scene(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "cadgen.cli", "dxf", "snapshot", "--help"],
            check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        # The help is GENERATED from cadgen.dxf.snapshot's signature, so what it
        # names is what the verb takes.
        self.assertIn("usage: cadgen dxf snapshot", result.stdout)
        self.assertIn("[TARGET] [OUT]", result.stdout)
        self.assertIn(".dxf", result.stdout)
        self.assertIn("--appearance", result.stdout)
        for absent in ("--camera", "--display", "--mode", "--view-labels",
                       "--kinematics", "--focus", "--input", "--output"):
            self.assertNotIn(absent, result.stdout, f"{absent} is not a drawing's business")

    def test_a_scene_flag_is_an_ordinary_parse_error(self) -> None:
        # The parser holds the signature and nothing else: a flag it does not
        # have is argparse's usage error, whatever the flag is.
        from cadgen.cli import dxf_snapshot

        for argv in (
            ["a.dxf", "a.png", "--camera", "iso"],
            ["a.dxf", "a.png", "--display=solid"],
            ["a.dxf", "a.png", "--view-labels"],
            ["--mode", "list", "a.dxf", "a.png"],
        ):
            with self.subTest(argv=argv):
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as caught:
                    dxf_snapshot.main(argv)
                self.assertEqual(2, caught.exception.code)
                self.assertIn("unrecognized arguments", errors.getvalue())

    def test_appearance_takes_light_or_dark_and_says_so(self) -> None:
        import cadgen.dxf as dxf_door

        with self.assertRaisesRegex(ValueError, r"appearance is dark or light; got 'purple'"):
            dxf_door.snapshot(Path("a.dxf"), Path("a.png"), appearance="purple")

    def test_runtime_is_bundled_beside_the_cli(self) -> None:
        # The skill must carry its own render runtime: it may not reach into the CAD
        # skill's copy, and a published skill ships no node_modules.
        runtime = browser_runtime_dir()
        self.assertTrue((Path(runtime) / "render.html").is_file())
        self.assertTrue((Path(runtime) / "snapshot-render.js").is_file())


if __name__ == "__main__":
    unittest.main()
