"""Snapshot's answer is a Result dataclass, like every other cadgen verb.

Snapshot used to hand its caller the BROWSER's return value: base64 image bytes,
viewport internals, an echoed job. `--json` was that dict with the known payload
keys filtered out, the human output was three hand-written branches, and a
Python caller had no way in at all — there was a CLI and no function.

So these cover the boundary rather than the rendering: what a SnapshotResult
carries, what `dataclasses.asdict` of it looks like on stdout, and that the
public `<format>.snapshot()` verbs exist and are the same shape. Nothing here
starts a browser.
"""

from __future__ import annotations

import io
import json
import unittest
from unittest import mock
from dataclasses import fields
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal.cli_from_function import emit, result_payload  # noqa: E402
from cadgen.results import SnapshotFile, SnapshotResult, SnapshotTimings  # noqa: E402
from cadgen.snapshot_core import snapshot_result  # noqa: E402

# A file path round-trips through pathlib, so it comes back in the NATIVE
# spelling (backslashes on Windows). Expectations are built with the same
# transform rather than hardcoding the POSIX separator.
def native(posix_path: str) -> str:
    return str(Path(posix_path))


VIEW_RESULT = {
    "ok": True,
    "mode": "view",
    "projection": "orthographic",
    "outputs": [
        {
            "path": "/tmp/review.png",
            "camera": "ISO",
            "width": 1600,
            "height": 1200,
            "mimeType": "image/png",
            "dataUrl": "data:image/png;base64,AAAA",
        }
    ],
    "warnings": ["one part had no material"],
    "timings": {"sceneBuildMs": 12.0, "renderMs": 30.0},
}


class ResultShape(unittest.TestCase):
    def test_one_file_per_written_output(self) -> None:
        result = snapshot_result(VIEW_RESULT, total_ms=42.0)
        self.assertTrue(result.ok)
        self.assertEqual([str(f.path) for f in result.files], [native("/tmp/review.png")])
        self.assertEqual(result.files[0].kind, "png")
        self.assertEqual(result.files[0].view, "ISO")
        self.assertEqual(result.warnings, ("one part had no material",))
        self.assertEqual(result.timings, SnapshotTimings(job_count=1, total_ms=42.0))

    def test_the_encoding_follows_the_render_not_the_filename(self) -> None:
        """An SVG served under a `.png` name is still SVG: the renderer's mime
        type is what actually happened, so it wins over the suffix."""
        listing = {
            "ok": True,
            "mode": "view",
            "outputs": [{"path": "/tmp/plate.png", "mimeType": "image/svg+xml"}],
        }
        self.assertEqual(snapshot_result(listing).files[0].kind, "svg")

    def test_a_path_less_output_is_not_a_file(self) -> None:
        # An animation's frame outputs carry no path; only what was WRITTEN counts.
        payload = {"ok": True, "outputs": [{"path": "", "mimeType": "image/png"}]}
        self.assertEqual(snapshot_result(payload).files, ())

    def test_a_multi_job_packet_flattens_into_one_answer(self) -> None:
        packet = {
            "ok": True,
            "jobs": [
                {"ok": True, "outputs": [{"path": "/tmp/a.png", "mimeType": "image/png"}]},
                {
                    "ok": True,
                    "outputs": [{"path": "/tmp/b.png", "mimeType": "image/png"}],
                    "warnings": ["clamped"],
                },
            ],
        }
        result = snapshot_result(packet, total_ms=5.0)
        self.assertEqual(
            [str(f.path) for f in result.files], [native("/tmp/a.png"), native("/tmp/b.png")]
        )
        self.assertEqual(result.warnings, ("clamped",))
        self.assertEqual(result.timings.job_count, 2)

    def test_files_carry_their_jobs_document_identity(self) -> None:
        # Nothing in a result used to say WHICH geometry it rendered, so a
        # stale render was indistinguishable from a fresh one. The resolved
        # packet knows: input path + the tree hash it rendered.
        browser_result = {
            "ok": True,
            "jobs": [
                {"ok": True, "outputs": [{"path": "/tmp/a.png", "mimeType": "image/png"}]},
                {"ok": True, "outputs": [{"path": "/tmp/b.png", "mimeType": "image/png"}]},
            ],
        }
        resolved_packet = {
            "single": False,
            "jobs": [
                {
                    "input": "STEP/gripper.step",
                    "resolved": {"tree": "abc123"},
                },
                {
                    "input": "STEP/tom.step",
                    "resolved": {"tree": "def456"},
                },
            ],
        }
        result = snapshot_result(browser_result, packet=resolved_packet)
        self.assertEqual(
            [(f.input, f.tree) for f in result.files],
            [("STEP/gripper.step", "abc123"), ("STEP/tom.step", "def456")],
        )

    def test_identity_is_empty_without_a_packet(self) -> None:
        result = snapshot_result(VIEW_RESULT)
        self.assertEqual([(f.input, f.tree) for f in result.files], [("", "")])

    def test_one_failed_job_fails_the_packet(self) -> None:
        packet = {"ok": True, "jobs": [{"ok": True, "outputs": []}, {"ok": False}]}
        self.assertFalse(snapshot_result(packet).ok)

    def test_list_mode_answers_with_parts_and_no_files(self) -> None:
        listing = {
            "ok": True,
            "mode": "list",
            "parts": [{"ref": "#o1.1", "name": "plate", "triangleCount": 12}],
        }
        result = snapshot_result(listing)
        self.assertEqual(result.files, ())
        self.assertEqual(result.parts[0]["ref"], "#o1.1")

    def test_debug_without_json_prints_one_line_per_input_after_the_saved_paths(self) -> None:
        # `--debug` alone used to compute the diagnostics and print nothing.
        result = SnapshotResult(
            ok=True, files=(SnapshotFile(path=Path("/tmp/a.png"), kind="png"),), warnings=("low light",),
            debug=({"input": "part.step", "stageTimings": {"renderMs": 12}},),
        )
        self.assertEqual(result.human_lines(), [
            "saved snapshot: /tmp/a.png",
            "warning: low light",
            'debug: {"input":"part.step","stageTimings":{"renderMs":12}}',
        ])

    def test_an_empty_inventory_still_prints_itself(self) -> None:
        # List mode with zero parts answers `[]`, not silence.
        listing = {"ok": True, "mode": "list", "parts": []}
        self.assertEqual(snapshot_result(listing).human_lines(), ["[]"])


class JsonShape(unittest.TestCase):
    """`--json` IS `dataclasses.asdict`, so the shape is the dataclass."""

    def test_the_payload_is_exactly_the_dataclass_fields(self) -> None:
        payload = result_payload(snapshot_result(VIEW_RESULT, total_ms=42.0))
        self.assertEqual(
            sorted(payload), sorted(field.name for field in fields(SnapshotResult))
        )
        self.assertEqual(
            payload["files"],
            [
                {
                    "path": native("/tmp/review.png"),
                    "kind": "png",
                    "view": "ISO",
                    "input": "",
                    "tree": "",
                    # A still is a video of nothing: `--video` fills these and a
                    # PNG leaves them at zero. They are on the FILE because that
                    # is what they describe.
                    "frames": 0,
                    "fps": 0,
                    "seconds": 0.0,
                }
            ],
        )
        self.assertEqual(payload["timings"], {"job_count": 1, "total_ms": 42.0})
        self.assertEqual(payload["parts"], [])
        self.assertEqual(payload["debug"], [])
        self.assertIs(payload["ok"], True)

    def test_no_browser_internals_survive_into_the_payload(self) -> None:
        # The dataclass has no field for them, so this cannot be forgotten the way
        # a filter over the browser dict could.
        printed = json.dumps(result_payload(snapshot_result(VIEW_RESULT)))
        for internal in ("dataUrl", "mimeType", "projection", "sceneBuildMs", "width"):
            self.assertNotIn(internal, printed)

    def test_the_cli_prints_one_compact_json_line(self) -> None:
        stdout = io.StringIO()
        code = emit(
            lambda: snapshot_result(VIEW_RESULT, total_ms=42.0),
            prog="cadgen step snapshot",
            as_json=True,
            stdout=stdout,
        )
        self.assertEqual(code, 0)
        printed = stdout.getvalue()
        self.assertEqual(len(printed.strip().splitlines()), 1)
        self.assertNotIn(", ", printed)  # compact separators
        self.assertEqual(json.loads(printed)["files"][0]["path"], native("/tmp/review.png"))

    def test_the_human_form_names_the_paths_and_the_warnings(self) -> None:
        stdout = io.StringIO()
        emit(
            lambda: snapshot_result(VIEW_RESULT),
            prog="cadgen step snapshot",
            as_json=False,
            stdout=stdout,
        )
        self.assertEqual(
            stdout.getvalue().splitlines(),
            [
                f"saved snapshot: {native('/tmp/review.png')}",
                "warning: one part had no material",
            ],
        )

    def test_list_mode_prints_the_inventory_and_nothing_else(self) -> None:
        listing = {"ok": True, "mode": "list", "parts": [{"ref": "#o1.1", "name": "plate"}]}
        stdout = io.StringIO()
        emit(
            lambda: snapshot_result(listing),
            prog="cadgen step snapshot",
            as_json=False,
            stdout=stdout,
        )
        self.assertEqual(
            json.loads(stdout.getvalue()), [{"ref": "#o1.1", "name": "plate"}]
        )

    def test_a_failure_is_the_schema_error_line(self) -> None:
        stdout = io.StringIO()
        code = emit(
            lambda: (_ for _ in ()).throw(RuntimeError("browser blew up")),
            prog="cadgen step snapshot",
            as_json=True,
            stdout=stdout,
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            json.loads(stdout.getvalue()), {"ok": False, "error": "browser blew up"}
        )

    def test_a_not_ok_result_exits_nonzero(self) -> None:
        code = emit(
            lambda: SnapshotResult(ok=False, files=(SnapshotFile(Path("/tmp/x.png"), "png"),)),
            prog="cadgen step snapshot",
            as_json=True,
            stdout=io.StringIO(),
        )
        self.assertEqual(code, 1)


class BrowserDiagnostics(unittest.IsolatedAsyncioTestCase):
    async def render_packet(self, jobs, results, *, single=True):
        from cadgen.snapshot_core import render_resolved_job_packet

        renderer = mock.Mock(render=mock.AsyncMock(side_effect=results), close=mock.AsyncMock())
        packet = {"single": single, "jobs": jobs}
        rendered = await render_resolved_job_packet(packet, runtime_dir=Path("."), renderer=renderer)
        renderer.close.assert_awaited_once()
        return result_payload(snapshot_result(rendered, packet=packet))

    async def test_browser_stages_survive_single_job_typed_json_with_resolution_and_input(self):
        stages = {
            "loadSourceMs": 10.5, "preparePoseMs": 0, "buildModelMs": 12,
            "prepareViewportMs": 9, "waitViewportMs": 3, "captureMs": 60,
            "sourceLoad": {"probeMs": 2, "cacheReadMs": 6.5, "cacheHitCount": 513, "cacheMissCount": 0},
            "outputs": [{"path": "/tmp/review.png", "updateModelMs": 4,
                         "frameCameraMs": 30, "drawSubmitMs": 5, "encodeImageMs": 18}],
        }
        job = {"input": "assembly.step", "debug": True, "outputs": [],
               "resolved": {"debug": {"stepArtifact": {"cache": "hit"}}}}
        payload = await self.render_packet([job], [{**VIEW_RESULT, "stageTimings": stages}])
        self.assertEqual(payload["debug"], [{"input": "assembly.step",
                         "stepArtifact": {"cache": "hit"}, "stageTimings": stages}])
        self.assertNotIn("dataUrl", json.dumps(payload))
        stages["outputs"][0]["encodeImageMs"] = 999
        self.assertEqual(payload["debug"][0]["stageTimings"]["outputs"][0]["encodeImageMs"], 18)

    async def test_mixed_packet_reports_only_requested_diagnostics_and_measured_stages(self):
        jobs = [{"input": "first.step", "debug": True, "outputs": []},
                {"input": "second.step", "debug": False, "outputs": []}]
        raw = {**VIEW_RESULT, "stageTimings": {"loadSourceMs": 3}}
        payload = await self.render_packet(jobs, [raw, raw], single=False)
        self.assertEqual(payload["debug"], [{"input": "first.step", "stageTimings": {"loadSourceMs": 3}}])

    async def test_invalid_and_unavailable_timings_do_not_create_diagnostic_placeholders(self):
        values = [None, [], {}, {"sourceLoad": {"cacheHitCount": True, "componentCount": -1,
                  "cacheMissCount": 1.2, "cacheBatchCount": 1 << 2000, "cacheReadMs": float("nan")}}, {"outputs": [{"path": "only-a-path"}]},
                  {"loadSourceMs": True, "captureMs": -1, "buildModelMs": "3",
                   "waitViewportMs": float("inf"), "prepareViewportMs": float("nan"),
                   "preparePoseMs": 1 << 2000},
                  {"dataUrl": "secret image bytes", "outputs": [False, {"drawSubmitMs": -2}]}]
        for stages in values:
            with self.subTest(stages=stages):
                payload = await self.render_packet(
                    [{"input": "part.step", "debug": True, "outputs": [], "resolved": {"debug": {}}}],
                    [{**VIEW_RESULT, "stageTimings": stages}],
                )
                self.assertEqual(payload["debug"], [])
        payload = await self.render_packet(
            [{"input": "part.step", "debug": True, "outputs": [],
              "resolved": {"debug": {"stepArtifact": {"cache": "hit"}}}}],
            [{"ok": True, "mode": "list", "parts": []}],
        )
        self.assertEqual(payload["debug"], [{"input": "part.step", "stepArtifact": {"cache": "hit"}}])


class PublicVerbs(unittest.TestCase):
    """Every snapshot door has a FUNCTION as well as a command."""

    DOORS = ("step", "stl", "threemf", "glb", "dxf", "urdf", "sdf")

    def test_each_door_exports_a_snapshot_verb(self) -> None:
        import importlib

        for door in self.DOORS:
            with self.subTest(door=door):
                module = importlib.import_module(f"cadgen.{door}")
                self.assertIn("snapshot", module.__all__)
                self.assertTrue(callable(module.snapshot))

    def test_each_door_has_its_own_shape(self) -> None:
        """Three signatures, not one shared fifteen-parameter blob.

        The doors used to share ONE signature and refuse the options a format
        cannot act on at runtime — so `cadgen stl snapshot --help` advertised
        `--kinematics`, `--focus` and `--hide` to a reader holding a mesh, and
        every one of them errored. Camera and the unified format-neutral Display
        object are intentionally shared by every door.
        """
        import importlib
        import inspect as inspect_module

        def parameters(module_name: str, attribute: str = "snapshot") -> set[str]:
            verb = getattr(importlib.import_module(module_name), attribute)
            return set(inspect_module.signature(verb).parameters)

        step = parameters("cadgen.step")
        self.assertLessEqual(
            {"display", "kinematics", "focus", "hide"},
            step,
            "the STEP door carries the full surface",
        )
        self.assertNotIn("joint_values", step, "a STEP model has no joints to pose")

        for door in ("stl", "threemf", "glb"):
            with self.subTest(door=door):
                mesh = parameters(f"cadgen.{door}")
                self.assertLessEqual({"camera", "display"}, mesh)
                self.assertNotIn("render", mesh)
                for absent in ("kinematics", "focus", "hide", "joint_values"):
                    self.assertNotIn(absent, mesh, f"{absent} has nothing to act on here")

        # The drawing door is the narrowest of the four shapes: a DXF is drawn
        # flat, so there is no scene to stage and nothing to pose or frame.
        drawing = parameters("cadgen.dxf")
        self.assertIn("appearance", drawing)
        for absent in ("camera", "display", "mode", "view_labels",
                       "kinematics", "focus", "hide", "joint_values", "section"):
            self.assertNotIn(absent, drawing, f"{absent} describes a scene a drawing does not have")

        for door in ("urdf", "sdf"):
            with self.subTest(door=door):
                robot = parameters(f"cadgen.{door}")
                self.assertIn("joint_values", robot)
                self.assertLessEqual({"camera", "display"}, robot)
                self.assertNotIn("render", robot)
                for absent in ("kinematics", "focus", "hide"):
                    self.assertNotIn(absent, robot, f"{absent} requires STEP topology")

        # The polymorphic door routes by suffix, so it is the UNION: a job
        # packet may mix formats, and each input is still held to its own
        # format's rules at resolve time.
        union = parameters("cadgen.cli.snapshot")
        self.assertEqual(
            union,
            step | parameters("cadgen.urdf"),
            "`cadgen snapshot` is exactly the union of the door shapes",
        )

    def test_the_mesh_and_robot_shapes_share_everything_they_can(self) -> None:
        """A robot door IS the mesh door plus posing — not a third dialect."""
        import importlib
        import inspect as inspect_module

        def parameters(door: str) -> set[str]:
            verb = importlib.import_module(f"cadgen.{door}").snapshot
            return set(inspect_module.signature(verb).parameters)

        self.assertEqual(parameters("urdf") - {"joint_values"}, parameters("stl"))
        # A drawing is deliberately NOT one of them: it shares the whole of what
        # is left after the scene goes (where, how big, and which appearance),
        # and adds nothing the mesh shape does not also mean.
        self.assertLessEqual(
            parameters("dxf") - {"appearance"},
            parameters("stl"),
            "the drawing door invented a spelling the mesh door does not have",
        )


    def test_a_verb_with_no_target_says_so_rather_than_reading_stdin(self) -> None:
        from cadgen import step

        with self.assertRaises(Exception) as ctx:
            step.snapshot()
        self.assertIn("requires", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
