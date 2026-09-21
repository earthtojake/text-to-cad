"""What a snapshot REQUEST can be refused for, and what a refusal leaves behind.

Every test here drives the real path — a door's ``main(argv)``, the public verb,
or ``resolve_render_job_packet`` over tiny temp fixtures — and none of them
launches a browser: a refusal is decided before one could start, which is the
point. The rules:

* a refused request leaves an existing OUT untouched; an accepted one clears it
  before anything is built;
* an option an input cannot honour is refused BY NAME, never ignored;
* each setting has one name, and a retired name says which replaced it;
* sizes, timeouts and section planes are closed and ranged here, not in the page.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

import cadgen.cli.dxf_snapshot as dxf_door  # noqa: E402
import cadgen.cli.snapshot as any_door  # noqa: E402
import cadgen.cli.step_snapshot as step_door  # noqa: E402
import cadgen.cli.stl_snapshot as stl_door  # noqa: E402
import cadgen.cli.urdf_snapshot as urdf_door  # noqa: E402
import cadgen.snapshot_cli as snapshot_cli  # noqa: E402
import cadgen.snapshot_core as snapshot_core  # noqa: E402
from cadgen.snapshot_cli import (  # noqa: E402
    SnapshotError,
    SnapshotOptions,
    load_job_from_options,
    resolve_render_job_packet,
)

STL = "solid part\nendsolid part\n"
URDF = "<robot name='arm'><link name='base'/></robot>\n"
YESTERDAY = b"yesterday's render"


def run_door(door, argv) -> tuple[int, str]:
    """``cadgen <door> snapshot ARGV``: the exit code and everything it said."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = door.main([str(arg) for arg in argv])
        except SystemExit as exit_:  # argparse's own refusals
            code = int(exit_.code or 0)
    return code, stdout.getvalue() + stderr.getvalue()


class _Workspace(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="snapshot-requests-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.stl = self.write("part.stl", STL)
        self.out = self.root / "review.png"

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def resolve(self, job: dict, **kwargs):
        return resolve_render_job_packet(job, cwd=self.root, **kwargs)

    def stl_job(self, **overrides) -> dict:
        return {"input": "part.stl", "outputs": [{"path": "review.png"}], **overrides}


class RefusedRequestsLeaveOutUntouched(_Workspace):
    """S2: the docs promise it, so it is tested where a user would see it."""

    def assert_refused_and_untouched(self, door, argv, pattern: str, *, out: Path | None = None) -> None:
        target = out or self.out
        target.write_bytes(YESTERDAY)
        # A browser here would mean the request was NOT refused up front.
        with mock.patch.object(snapshot_core.BatchSnapshotRenderer, "start", side_effect=AssertionError("browser")):
            code, said = run_door(door, argv)
        self.assertEqual(1, code, said)
        self.assertRegex(said, pattern)
        self.assertEqual(YESTERDAY, target.read_bytes(), f"a refused request deleted {target.name}: {said}")

    def test_every_refusal_decided_from_the_request_keeps_the_existing_file(self) -> None:
        urdf = self.write("arm.urdf", URDF)
        srdf = self.write("lonely.srdf", "<robot name='nobody'/>\n")
        script = self.write("model.py", "print('hi')\n")
        job = self.write("job.json", json.dumps({"input": "part.stl", "framerate": 3, "outputs": [str(self.out)]}))
        svg = self.root / "review.svg"
        cases = [
            (stl_door, [self.stl, self.out, "--display", "wireframe"], r"applies to STEP models only"),
            (stl_door, [self.stl, self.out, "--display", '{"clip":{"axis":"x"}}'], r"display\.clip applies to STEP"),
            (stl_door, [self.stl, self.out, "--display", '{"lighting":{"fill":9}}'], r"display\.lighting\.fill"),
            (step_door, [self.stl, self.out], r"does not render \.stl inputs"),
            (step_door, [script, self.out], r"a model script is a program"),
            (stl_door, [self.stl, self.out, "--mode", "section"], r"section mode requires STEP topology"),
            (stl_door, [self.stl, self.out, "--mode", "orbit"], r"Unsupported render mode: orbit"),
            (stl_door, ["--job", job], r"unknown render job key\(s\): framerate"),
            (stl_door, [self.stl, self.out, "--width", "0"], r"output width must be a positive whole number"),
            (stl_door, [self.stl, self.out, "--height", "100000"], r"exceeds the maximum of 8192 px"),
            (stl_door, [self.stl, self.out, "--size-profile", "nonsense"], r"Unknown size profile: 'nonsense'"),
            (stl_door, [self.stl, self.out, "--camera", "30:20:5"], r"exactly\s+azimuth:elevation"),
            (any_door, [self.stl, self.out, "--joint-values", '{"elbow": 10}'], r"jointValues pose a robot description"),
            (any_door, [self.stl, self.out, "--kinematics", "open"], r"kinematics values require a STEP model"),
            (any_door, [self.stl, self.out, "--section", "XZ:4"], r"section mode requires STEP topology"),
            (any_door, [srdf, self.out], r"no paired URDF"),
            (urdf_door, [urdf, self.out, "--joint-values", '{"elbow": 10}'], r"Unknown joint\(s\): elbow"),
        ]
        for door, argv, pattern in cases:
            with self.subTest(argv=[str(arg) for arg in argv[1:]]):
                self.assert_refused_and_untouched(door, argv, pattern)
        with self.subTest("a view cannot be written as .svg"):
            self.assert_refused_and_untouched(
                stl_door, [self.stl, svg], r"view mode writes \.png", out=svg
            )

    def test_a_refusal_in_a_later_job_keeps_every_earlier_jobs_file_too(self) -> None:
        """The whole packet is accepted before anything is cleared, not job by job."""
        first = self.root / "first.png"
        first.write_bytes(YESTERDAY)
        job = self.write("packet.json", json.dumps({"jobs": [
            {"input": str(self.stl), "outputs": [str(first)]},
            {"input": str(self.stl), "display": {"mode": "xray"}, "outputs": [str(self.out)]},
        ]}))
        self.assert_refused_and_untouched(stl_door, ["--job", job], r"display\.mode 'xray' applies to STEP")
        self.assertEqual(YESTERDAY, first.read_bytes())

    def test_an_accepted_request_clears_out_before_anything_is_built(self) -> None:
        """The other half of the contract: once the request stands, a failure during
        the build must not leave yesterday's image at the path that was asked for."""
        self.out.write_bytes(YESTERDAY)
        seen: list[bool] = []

        def failing_build(single, prepared):
            seen.append(self.out.exists())
            raise SnapshotError("the build failed")

        with mock.patch.object(snapshot_cli, "resolve_prepared_job_packet", failing_build):
            code, said = run_door(stl_door, [self.stl, self.out])
        self.assertEqual(1, code)
        self.assertIn("the build failed", said)
        self.assertEqual([False], seen, "OUT must already be gone when the build starts")
        self.assertFalse(self.out.exists())

    def test_preparing_a_step_request_never_touches_the_store(self) -> None:
        """Preparation is what runs before the clear, so it may not compile a tree."""
        step = self.write("part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        with mock.patch.object(snapshot_cli, "document_snapshot", side_effect=AssertionError("compiled")), \
             mock.patch.object(snapshot_cli, "ensure_step_topology_artifact", side_effect=AssertionError("built")):
            single, prepared = snapshot_cli.prepare_render_job_packet(
                {"input": str(step), "mode": "section", "section": {"plane": "YZ", "offset": 2},
                 "selection": {"hide": ["#o1.2"]}, "outputs": [{"path": str(self.root / "cut.svg")}]},
                cwd=self.root,
            )
        self.assertTrue(single)
        self.assertEqual({"plane": "YZ", "offset": 2}, prepared[0].job["section"])


class CrossKindOptionsAreRefusedByName(_Workspace):
    """S3 and the DXF wording: nothing an input cannot honour is dropped in silence."""

    def test_joint_values_pose_robots_only(self) -> None:
        self.write("panel.dxf", "0\nEOF\n")
        self.write("part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        for name, expected in (
            ("part.stl", r"jointValues pose a robot description \(URDF, SRDF or SDF\); STL mesh inputs have no joints"),
            ("panel.dxf", r"jointValues pose a robot description.*DXF drawings have no joints"),
            ("part.step", r"jointValues pose a robot description.*pose a STEP model with kinematics"),
        ):
            with self.subTest(input=name), self.assertRaisesRegex(SnapshotError, expected):
                self.resolve({"input": name, "jointValues": {"elbow": 10}, "outputs": [{"path": "o.png"}]})

    def test_a_drawing_is_called_a_drawing(self) -> None:
        self.write("panel.dxf", "0\nEOF\n")
        # And is refused before the file is ever opened: a request this input
        # cannot honour must not cost a flattening first.
        with mock.patch.object(snapshot_cli, "drawing_payload_file", side_effect=AssertionError("flattened")):
            with self.assertRaises(SnapshotError) as caught:
                self.resolve({"input": "panel.dxf", "outputs": [{"path": "o.png"}],
                              "quality": {"tessellation": {"chordTolerance": 0.001}}})
        self.assertIn("a DXF drawing is line work, not a tessellated surface", str(caught.exception))
        self.assertNotIn("GLB", str(caught.exception))

    def test_a_robots_link_meshes_cannot_be_retessellated_either(self) -> None:
        self.write("arm.urdf", URDF)
        with self.assertRaisesRegex(SnapshotError, r"quality\.tessellation requires an exact-surface STEP package"):
            self.resolve({"input": "arm.urdf", "outputs": [{"path": "o.png"}],
                          "quality": {"tessellation": {"chordTolerance": 0.001}}})

    def test_a_mesh_doors_mode_error_offers_only_the_modes_it_accepts(self) -> None:
        """S12: `--display Wireframe` on an STL used to list all five presets."""
        code, said = run_door(stl_door, [self.stl, self.out, "--display", "Wireframe"])
        self.assertEqual(1, code)
        self.assertIn("Supported modes: render, solid", said)
        for step_only in ("xray", "hidden-line", "wireframe"):
            self.assertNotIn(step_only, said)
        with self.assertRaises(SnapshotError) as caught:
            self.resolve(self.stl_job(display={"mode": "Wireframe"}))
        self.assertIn("display.mode must be one of: render, solid;", str(caught.exception))
        # A STEP door still offers every preset.
        step = self.write("part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        code, said = run_door(step_door, [step, self.out, "--display", "Wireframe"])
        self.assertIn("hidden-line, render, solid, wireframe, xray", said)


class SrdfPairingTests(_Workspace):
    """S9: an SRDF renders its paired URDF, found the way `cadgen srdf validate` finds it."""

    def test_the_pairing_is_by_robot_name_not_by_file_stem(self) -> None:
        self.write("robots/description.urdf", URDF)
        self.write("robots/planning.srdf", "<robot name='arm'/>\n")
        packet = self.resolve({"input": "robots/planning.srdf", "outputs": [{"path": "o.png"}]})
        self.assertIn("description.urdf", packet["jobs"][0]["resolved"]["urdfUrl"])

    def test_no_match_names_what_was_looked_for_and_what_was_found(self) -> None:
        self.write("robots/other.urdf", "<robot name='crane'/>\n")
        self.write("robots/planning.srdf", "<robot name='arm'/>\n")
        with self.assertRaises(SnapshotError) as caught:
            self.resolve({"input": "robots/planning.srdf", "outputs": [{"path": "o.png"}]})
        message = str(caught.exception)
        self.assertIn("planning.srdf has no paired URDF", message)
        self.assertIn("<robot name='arm'>", message)
        self.assertIn("other.urdf (robot 'crane')", message)
        self.assertIn("cadgen srdf validate", message)

    def test_an_empty_folder_and_an_ambiguous_one_are_told_apart(self) -> None:
        self.write("alone/planning.srdf", "<robot name='arm'/>\n")
        with self.assertRaisesRegex(SnapshotError, "it holds no .urdf files"):
            self.resolve({"input": "alone/planning.srdf", "outputs": [{"path": "o.png"}]})
        for name in ("a.urdf", "b.urdf"):
            self.write(f"twins/{name}", URDF)
        self.write("twins/planning.srdf", "<robot name='arm'/>\n")
        with self.assertRaisesRegex(SnapshotError, r"ambiguous: 2 \.urdf files .* \(a\.urdf, b\.urdf\)"):
            self.resolve({"input": "twins/planning.srdf", "outputs": [{"path": "o.png"}]})

    def test_joint_names_come_from_the_paired_urdf(self) -> None:
        self.write("robots/description.urdf", (
            "<robot name='arm'><link name='a'/><link name='b'/>"
            "<joint name='elbow' type='revolute'><parent link='a'/><child link='b'/>"
            "<axis xyz='0 0 1'/><limit lower='-1' upper='1' effort='1' velocity='1'/></joint></robot>\n"
        ))
        self.write("robots/planning.srdf", "<robot name='arm'/>\n")
        job = {"input": "robots/planning.srdf", "outputs": [{"path": "o.png"}]}
        self.resolve({**job, "jointValues": {"elbow": 10}})
        with self.assertRaisesRegex(SnapshotError, r"Unknown joint\(s\): elbw"):
            self.resolve({**job, "jointValues": {"elbw": 10}})


class SectionPlaneTests(_Workspace):
    """S4: the plane is a validated job key and a STEP flag, and OUT's extension is the format."""

    def setUp(self) -> None:
        super().setUp()
        self.step = self.write("part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")

    def prepared(self, **job) -> dict:
        _single, prepared = snapshot_cli.prepare_render_job_packet(
            {"input": "part.step", "outputs": [{"path": "cut.png"}], **job}, cwd=self.root
        )
        return prepared[0].job

    def section_from_argv(self, *argv: str) -> dict:
        captured = {}

        def capture(options, **_kwargs):
            captured["job"] = load_job_from_options(options, cwd=self.root)
            return snapshot_core.snapshot_result({"ok": True, "outputs": []})

        with mock.patch.object(snapshot_cli, "run_snapshot", capture):
            code, said = run_door(step_door, [self.step, self.root / "cut.png", *argv])
        self.assertEqual(0, code, said)
        return captured["job"]

    def test_the_flag_and_the_job_key_are_the_same_request(self) -> None:
        self.assertEqual({"plane": "XZ", "offset": 12.5},
                         self.section_from_argv("--mode", "section", "--section", "XZ:12.5")["section"])
        self.assertEqual({"plane": "YZ", "offset": 0},
                         self.section_from_argv("--mode", "section", "--section", "YZ")["section"])
        self.assertEqual({"plane": "XZ", "offset": -3},
                         self.prepared(mode="section", section={"plane": "XZ", "offset": -3})["section"])
        # Section mode with no plane named is the XY cut at 0, stated on the job.
        self.assertEqual({"plane": "XY", "offset": 0}, self.prepared(mode="section")["section"])

    def test_the_python_verb_takes_the_same_two_spellings(self) -> None:
        from cadgen import step

        seen = []
        with mock.patch.object(snapshot_cli, "run_snapshot", lambda options, **_: seen.append(options) or "result"):
            step.snapshot(self.step, self.out, mode="section", section="XZ:4")
            step.snapshot(self.step, self.out, mode="section", section={"plane": "YZ", "offset": 1})
        jobs = [load_job_from_options(options, cwd=self.root) for options in seen]
        self.assertEqual([{"plane": "XZ", "offset": 4.0}, {"plane": "YZ", "offset": 1}],
                         [job["section"] for job in jobs])

    def test_the_plane_vocabulary_is_closed_and_ranged(self) -> None:
        for section, pattern in (
            ({"plane": "XW"}, r"section\.plane must be one of: XY, XZ, YZ; got 'XW'"),
            ({"plane": "xy"}, r"section\.plane must be one of"),
            ({"plane": "XY", "offset": "3"}, r"section\.offset must be a finite number"),
            ({"plane": "XY", "offset": float("inf")}, r"section\.offset must be a finite number"),
            ({"plane": "XY", "offset": True}, r"section\.offset must be a finite number"),
            ({"normal": [0, 0, 1]}, r"section has unknown key\(s\): normal; supported keys: offset, plane"),
            ({"plane": "XY", "format": "svg"}, r"section has unknown key\(s\): format"),
            ("XZ", r"section must be a \{"),
        ):
            with self.subTest(section=section), self.assertRaisesRegex(SnapshotError, pattern):
                self.prepared(mode="section", section=section)
        for flag, pattern in (("XZ:deep", r"--section offset must be a number"), ("", r"--section requires PLANE")):
            with self.subTest(flag=flag), self.assertRaisesRegex(SnapshotError, pattern):
                snapshot_core.parse_section_option(flag)

    def test_a_section_outside_section_mode_is_refused_not_ignored(self) -> None:
        with self.assertRaisesRegex(SnapshotError, r"section positions the cut of section mode.*mode is view"):
            self.prepared(section={"plane": "XZ"})

    def test_outs_extension_decides_the_format_and_a_wrong_one_is_refused(self) -> None:
        def prepared_path(mode: str, path: str) -> str:
            return self.prepared(mode=mode, outputs=[{"path": path}])["outputs"][0]["path"]

        self.assertTrue(prepared_path("section", "cut.svg").endswith("cut.svg"))
        self.assertTrue(prepared_path("section", "cut.PNG").endswith("cut.PNG"))
        self.assertTrue(prepared_path("view", "iso.png").endswith("iso.png"))
        for mode, path, pattern in (
            ("view", "iso.svg", r"view mode writes \.png: render output 0 names 'iso\.svg'.*--mode section"),
            ("view", "iso.jpg", r"view mode writes \.png"),
            ("view", "iso", r"view mode writes \.png"),
            ("section", "cut.pdf", r"section mode writes \.png or \.svg"),
        ):
            with self.subTest(mode=mode, path=path), self.assertRaisesRegex(SnapshotError, pattern):
                prepared_path(mode, path)
        # `format` was never reachable from Python and is not a key anywhere now.
        with self.assertRaisesRegex(SnapshotError, r"render output 0 has unknown key\(s\): format"):
            self.prepared(mode="section", outputs=[{"path": "cut.png", "format": "svg"}])

    def test_the_planes_match_the_page_that_cuts(self) -> None:
        source = repo_path("packages/core/src/common/renderMeshScene.js").read_text(encoding="utf-8")
        declared = re.search(r"export const SECTION_PLANES = Object\.freeze\(\[(.*?)\]\)", source)
        self.assertIsNotNone(declared, "renderMeshScene.js no longer declares SECTION_PLANES")
        self.assertEqual(tuple(re.findall(r'"(\w+)"', declared.group(1))), snapshot_core.SECTION_PLANES)
        # The page reads exactly the keys Python validates: nothing else of `section`.
        read = set(re.findall(r"\bsection\??\.(\w+)", source)) - {"segmentCount"}
        self.assertEqual(set(snapshot_core.SECTION_KEYS), read)


class SizingTests(_Workspace):
    """S6/S7: a size is one of the listed profiles or a ranged whole number of pixels."""

    def size(self, **job) -> tuple[int, int]:
        output = self.resolve(self.stl_job(**job))["jobs"][0]["outputs"][0]
        return output["width"], output["height"]

    def test_the_profiles_are_a_closed_set_with_one_name_each(self) -> None:
        self.assertEqual((1600, 1200), self.size())
        for name, expected in snapshot_core.SIZE_PROFILES.items():
            with self.subTest(profile=name):
                self.assertEqual(expected, self.size(output={"sizeProfile": name}))
        for retired, replacement in snapshot_core.RETIRED_SIZE_PROFILES.items():
            self.assertIn(replacement, snapshot_core.SIZE_PROFILES)
            with self.subTest(retired=retired), self.assertRaisesRegex(
                SnapshotError, rf"size profile '{retired}' was removed; use '{replacement}'"
            ):
                self.size(output={"sizeProfile": retired})
        with self.assertRaisesRegex(SnapshotError, r"Unknown size profile: 'nonsense'\. Size profiles: simple \(1200x900\)"):
            self.size(output={"sizeProfile": "nonsense"})
        # No case or underscore folding: exactly the listed names.
        with self.assertRaisesRegex(SnapshotError, "Unknown size profile"):
            self.size(output={"sizeProfile": "Contact_Sheet"})

    def test_every_door_lists_exactly_those_profiles_and_that_maximum(self) -> None:
        for door in (step_door, stl_door, urdf_door, dxf_door, any_door):
            # argparse breaks a line after a hyphen; rejoin what it split.
            text = " ".join(door.build_parser().format_help().split()).replace("- ", "-")
            for name, (width, height) in snapshot_core.SIZE_PROFILES.items():
                self.assertIn(f"{name} ({width}x{height}", text, door.DEFAULT_PROG)
            self.assertIn(f"1..{snapshot_core.MAX_OUTPUT_DIMENSION}", text)
        review = repo_path("skills/cad/references/snapshot-review.md").read_text(encoding="utf-8")
        for name in snapshot_core.SIZE_PROFILES:
            self.assertIn(f"`{name}`", review)

    def test_explicit_sizes_are_whole_pixels_within_the_maximum(self) -> None:
        self.assertEqual((640, 1200), self.size(outputs=[{"path": "o.png", "width": 640}]))
        limit = snapshot_core.MAX_OUTPUT_DIMENSION
        self.assertEqual((limit, limit), self.size(outputs=[{"path": "o.png", "width": limit, "height": limit}]))
        for key, value, pattern in (
            ("width", 0, "positive whole number"), ("height", -5, "positive whole number"),
            ("width", 640.5, "positive whole number"), ("width", "640", "positive whole number"),
            ("width", True, "positive whole number"),
            ("height", limit + 1, rf"output height {limit + 1} exceeds the maximum of {limit} px"),
        ):
            with self.subTest(key=key, value=value), self.assertRaisesRegex(SnapshotError, pattern):
                self.size(outputs=[{"path": "o.png", key: value}])

    def test_output_settings_values_are_typed_and_ranged(self) -> None:
        self.resolve(self.stl_job(output={"padding": 0.15, "renderScale": 3, "tightFrame": False,
                                          "transparent": True, "viewLabels": True}))
        for output, pattern in (
            ({"padding": 0.5}, r"output\.padding must be a finite number between 0 and 0\.15"),
            ({"padding": "0.1"}, r"output\.padding"),
            ({"renderScale": 0}, r"output\.renderScale must be a finite number between 1 and 3"),
            ({"renderScale": 8}, r"output\.renderScale"),
            ({"tightFrame": "yes"}, r"output\.tightFrame must be a boolean"),
            ({"viewLabels": 1}, r"output\.viewLabels must be a boolean"),
            ({"transparent": None}, r"output\.transparent must be a boolean"),
            ({"sizeProfile": 7}, r"Unknown size profile: 7"),
        ):
            with self.subTest(output=output), self.assertRaisesRegex(SnapshotError, pattern):
                self.resolve(self.stl_job(output=output))

    def test_the_ranges_are_the_ones_the_page_clamps_to(self) -> None:
        source = repo_path("packages/core/src/common/renderOptions.js").read_text(encoding="utf-8")
        padding = re.search(r"clamp\(toFiniteNumber\(job\.output\?\.padding, [0-9.]+\), ([0-9.]+), ([0-9.]+)\)", source)
        scale = re.search(r"renderScale, defaultRenderScale\), ([0-9.]+), ([0-9.]+)\)", source)
        self.assertEqual(snapshot_core.OUTPUT_PADDING_RANGE, tuple(float(n) for n in padding.groups()))
        self.assertEqual(snapshot_core.OUTPUT_RENDER_SCALE_RANGE, tuple(float(n) for n in scale.groups()))

    def test_width_and_height_override_every_output_of_a_job_packet(self) -> None:
        """S6: they were dropped in silence whenever --job was given."""
        job = self.write("packet.json", json.dumps({"jobs": [
            {"input": "part.stl", "outputs": ["a.png", {"path": "b.png", "width": 100, "height": 100}]},
            {"input": "part.stl", "outputs": [{"path": "c.png"}]},
        ]}))
        options = SnapshotOptions(job=str(job), width=800)
        packet = self.resolve(load_job_from_options(options, cwd=self.root))
        sizes = [(o["width"], o["height"]) for j in packet["jobs"] for o in j["outputs"]]
        self.assertEqual([(800, 1200), (800, 100), (800, 1200)], sizes)
        with self.assertRaisesRegex(SnapshotError, "output height must be a positive whole number"):
            self.resolve(load_job_from_options(SnapshotOptions(job=str(job), height=0), cwd=self.root))

    def test_a_result_key_is_not_a_request_key(self) -> None:
        for key in ("dataUrl", "text"):
            with self.subTest(key=key), self.assertRaisesRegex(
                SnapshotError, rf"render output 0 carries {key}: those are what the renderer reports"
            ):
                self.resolve(self.stl_job(outputs=[{"path": "o.png", key: "x"}]))


class TimeoutAndModeTests(_Workspace):
    def test_a_bad_timeout_is_refused_when_the_job_is_resolved(self) -> None:
        """S8: it used to raise a raw ValueError after the browser had launched."""
        self.assertEqual(2.5, self.resolve(self.stl_job(timeoutSeconds=2.5))["jobs"][0]["timeoutSeconds"])
        for value in (0, -1, "30", True, None, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(
                SnapshotError, "timeoutSeconds must be a positive finite number"
            ):
                self.resolve(self.stl_job(timeoutSeconds=value))

    def test_mode_case_is_decided_in_one_place(self) -> None:
        """S13: `--mode LIST` used to demand an OUT that list mode does not take."""
        job = load_job_from_options(
            SnapshotOptions(input="part.stl", mode="LIST", mode_specified=True), cwd=self.root
        )
        self.assertEqual(("list", []), (job["mode"], job["outputs"]))
        self.assertEqual("list", self.resolve({"input": "part.stl", "mode": " List "})["jobs"][0]["mode"])
        packet = self.write("packet.json", json.dumps({"input": "part.stl", "outputs": ["o.png"]}))
        overridden = load_job_from_options(
            SnapshotOptions(job=str(packet), mode="LIST", mode_specified=True), cwd=self.root
        )
        self.assertEqual("list", overridden["mode"])
        with self.assertRaisesRegex(SnapshotError, r"Unsupported render mode: orbit\. Modes: list, section, view"):
            load_job_from_options(SnapshotOptions(input="part.stl", output="o.png", mode="orbit"), cwd=self.root)


class JobFileAndDisplayFileTests(_Workspace):
    """S5/S11: a job is a file, and a path that is not one is said so."""

    def test_there_is_no_stdin_job(self) -> None:
        with self.assertRaisesRegex(SnapshotError, r"reading a job from stdin \(--job -\) was removed"):
            load_job_from_options(SnapshotOptions(job="-"), cwd=self.root)
        with self.assertRaisesRegex(SnapshotError, r"render requires a TARGET or --job") as caught:
            load_job_from_options(SnapshotOptions(), cwd=self.root)
        self.assertNotIn("stdin", str(caught.exception))
        # Nothing reads the process's stdin: a piped packet is not a request.
        with mock.patch("sys.stdin", io.StringIO(json.dumps(self.stl_job()))):
            code, said = run_door(stl_door, [])
        self.assertEqual(1, code)
        self.assertIn("requires a TARGET or --job", said)

    def test_a_missing_or_directory_path_is_a_snapshot_error(self) -> None:
        (self.root / "folder").mkdir()
        for argv, pattern in (
            (["--job", self.root / "nope.json"], r"--job file does not exist: .*nope\.json"),
            (["--job", self.root / "folder"], r"--job names a directory, not a render-job JSON file"),
            ([self.stl, self.out, "--display", self.root / "folder"], r"--display names a directory, not a display JSON file"),
        ):
            with self.subTest(argv=[str(a) for a in argv]):
                code, said = run_door(stl_door, argv)
                self.assertEqual(1, code)
                self.assertRegex(said, pattern)
                self.assertNotIn("Traceback", said)
                self.assertNotIn("Errno", said)


class OneNamePerSettingTests(_Workspace):
    def test_selection_is_focus_or_hide(self) -> None:
        self.write("part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        with self.assertRaisesRegex(
            SnapshotError, r"selection has unknown key\(s\): refs; supported keys: focus, hide; "
                           r"selection\.refs was removed; use selection\.focus"
        ):
            self.resolve({"input": "part.step", "selection": {"refs": ["#o1.2"]}, "outputs": [{"path": "o.png"}]})
        with self.assertRaisesRegex(SnapshotError, "selection must be a"):
            self.resolve({"input": "part.step", "selection": ["#o1.2"], "outputs": [{"path": "o.png"}]})

    def test_each_view_has_one_camera_preset(self) -> None:
        for retired, replacement in snapshot_core.RETIRED_CAMERA_PRESETS.items():
            for camera in (retired, {"preset": retired}):
                with self.subTest(camera=camera), self.assertRaisesRegex(
                    SnapshotError, rf"camera preset '{retired}' was removed; use '{replacement}'"
                ):
                    self.resolve(self.stl_job(camera=camera))
        for preset in snapshot_core.CAMERA_PRESETS:
            self.resolve(self.stl_job(camera=preset))
        self.resolve(self.stl_job(camera="35:-20"))
        with self.assertRaisesRegex(SnapshotError, r"Unknown camera preset: sideways\. Presets: back, bottom"):
            self.resolve(self.stl_job(outputs=[{"path": "o.png", "camera": "sideways"}]))

    def test_the_presets_match_the_page_that_frames(self) -> None:
        source = repo_path("packages/core/src/common/camera.js").read_text(encoding="utf-8")
        block = re.search(r"RENDER_CAMERA_PRESETS = Object\.freeze\(\{(.*?)\n\}\);", source, re.S)
        self.assertEqual(set(re.findall(r"^\s+(\w+): Object\.freeze", block.group(1), re.M)),
                         set(snapshot_core.CAMERA_PRESETS))
        retired = re.search(r"RETIRED_CAMERA_PRESETS = Object\.freeze\(\{(.*?)\}\)", source, re.S)
        self.assertEqual(dict(re.findall(r'(\w+): "(\w+)"', retired.group(1))),
                         snapshot_core.RETIRED_CAMERA_PRESETS)


class DisplayIsValidatedOncePerJob(_Workspace):
    def count(self, run) -> int:
        with mock.patch.object(
            snapshot_core, "validate_display_settings_values",
            wraps=snapshot_core.validate_display_settings_values,
        ) as validate:
            run()
        return validate.call_count

    def test_whichever_way_the_display_arrives(self) -> None:
        display = {"mode": "render", "lighting": {"fill": 0.4}}
        self.write("stage.json", json.dumps(display))
        packet = self.write("packet.json", json.dumps({"jobs": [self.stl_job(), self.stl_job(display="solid")]}))
        ways = {
            "job object": lambda: self.resolve(self.stl_job(display=display)),
            "job file path": lambda: self.resolve(self.stl_job(display="stage.json")),
            "no display": lambda: self.resolve(self.stl_job()),
            "flag": lambda: self.resolve(load_job_from_options(
                SnapshotOptions(input="part.stl", output="o.png", display=json.dumps(display), display_specified=True),
                cwd=self.root)),
        }
        for name, run in ways.items():
            with self.subTest(way=name):
                self.assertEqual(1, self.count(run))
        # An override lands on every job of a packet: one validation per job, not three.
        self.assertEqual(2, self.count(lambda: self.resolve(load_job_from_options(
            SnapshotOptions(job=str(packet), display="render", display_specified=True), cwd=self.root))))


class PythonVerbTests(_Workspace):
    """S10: the library call reads like Python, not like argv."""

    def options_for(self, **kwargs) -> SnapshotOptions:
        from cadgen import step

        seen = []
        with mock.patch.object(snapshot_cli, "run_snapshot", lambda options, **_: seen.append(options) or "result"):
            step.snapshot(self.root / "part.step", self.out, **kwargs)
        return seen[0]

    def test_an_explicit_none_is_an_omitted_option(self) -> None:
        options = self.options_for(display=None, camera=None, kinematics=None, animation=None,
                                   video=None, section=None, time=None)
        for name in ("display", "camera", "kinematics", "animation", "video", "section"):
            self.assertFalse(getattr(options, f"{name}_specified"), name)
        self.write("part.step", "ISO-10303-21;\nEND-ISO-10303-21;\n")
        job = load_job_from_options(options, cwd=self.root)
        self.assertEqual({"input", "mode", "outputs"}, set(job))

    def test_a_bare_string_is_not_a_sequence_of_refs(self) -> None:
        for name in ("focus", "hide"):
            with self.subTest(option=name), self.assertRaisesRegex(
                ValueError, rf"{name} takes a sequence of occurrence refs, not one string: pass {name}=\('#o1\.2',\)"
            ):
                self.options_for(**{name: "#o1.2"})
        self.assertEqual(["#o1.2", "#o1.3"], self.options_for(focus=["#o1.2", "#o1.3"]).focus)
        self.assertEqual(["#o1.2"], self.options_for(hide=("#o1.2",)).hide)


class StepDebugReportsWhatWasResolved(unittest.TestCase):
    def test_the_step_artifact_entry_carries_this_documents_values(self) -> None:
        """S13: `source`, `assembly` and `selectorReextracted` were constants."""
        import os

        from tests.python.support.store_fixtures import seed_result

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": f"{tmp}/cache"}):
            step = Path(tmp).resolve() / "part.step"
            step.write_text("ISO-10303-21;\npart\nEND-ISO-10303-21;\n", encoding="utf-8")
            seed_result(step, {
                "kind": "assembly-package", "entryKind": "part", "rootName": "part", "units": "mm",
                "sourceKind": "step", "stepPath": "part.step",
                "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]},
                "stats": {"occurrenceCount": 1, "shapeCount": 1},
                "components": {"c1": {"contentHash": "c1"}},
                "occurrences": [{"id": "o1.1", "name": "occ", "component": "c1",
                                 "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}],
            })
            packet = resolve_render_job_packet(
                {"input": str(step), "debug": True, "outputs": [{"path": f"{tmp}/o.png"}]}, cwd=Path(tmp)
            )
        resolved = packet["jobs"][0]["resolved"]
        entry = resolved["debug"]["stepArtifact"]
        self.assertEqual(
            {"documentHash", "tree", "view", "componentCount", "occurrenceCount", "selectorIndex"}, set(entry)
        )
        self.assertEqual((resolved["documentHash"], resolved["tree"]), (entry["documentHash"], entry["tree"]))
        self.assertEqual((1, 1, False), (entry["componentCount"], entry["occurrenceCount"], entry["selectorIndex"]))


if __name__ == "__main__":
    unittest.main()
