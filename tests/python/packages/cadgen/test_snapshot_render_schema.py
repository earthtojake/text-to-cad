"""Unified display, technical output, and tessellation are closed schemas."""

from __future__ import annotations

import inspect
import re
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_core import (  # noqa: E402
    MIN_RENDER_TESSELLATION,
    RENDER_BACKDROP_KEYS,
    RENDER_LIGHTING_KEYS,
    RENDER_QUALITY_IDS,
    RENDER_STUDIO_IDS,
    SUPPORTED_OUTPUT_SETTINGS_KEYS,
    SUPPORTED_QUALITY_KEYS,
    SnapshotError,
    load_display_option,
    normalize_common_job,
    validate_render_tessellation,
)


def normalize(**settings: object) -> dict[str, object]:
    return normalize_common_job(
        {"input": "part.step", "outputs": [{"path": "out.png"}], **settings},
        mode="view",
        resolved_cwd=Path("."),
        timestamp="20260907-000000",
    )


class RenderDisplaySchemaTest(unittest.TestCase):
    def test_render_ids_are_closed_and_render_shortcut_is_a_display_mode(self):
        self.assertEqual({"light", "dark"}, set(RENDER_STUDIO_IDS))
        self.assertEqual({"preview", "final"}, set(RENDER_QUALITY_IDS))
        self.assertEqual({"mode": "render"}, load_display_option("render", cwd=Path(".")))
        for invalid in ("unknown", None, True, [], {}):
            with self.subTest(studio=invalid), self.assertRaisesRegex(
                SnapshotError, "display.render.studio must be light or dark"
            ):
                load_display_option({"mode": "render", "render": {"studio": invalid}}, cwd=Path("."))
        for invalid in ("unknown", None, False, [], {}):
            with self.subTest(quality=invalid), self.assertRaisesRegex(
                SnapshotError, "display.render.quality must be preview or final"
            ):
                load_display_option({"mode": "render", "render": {"quality": invalid}}, cwd=Path("."))

    def test_render_values_are_strict_and_sparse(self):
        render = {
            "studio": "dark",
            "quality": "preview",
            "exposure": -1.25,
            "lighting": {"rotation": 180, "size": 0.25, "fill": 1},
            "backdrop": {"color": "#123456", "transparent": True, "ground": False, "groundPlacement": "lowest"},
        }
        display = load_display_option({"mode": "render", "render": render}, cwd=Path("."))
        self.assertEqual(render, display["render"])
        self.assertEqual({"rotation", "size", "fill"}, set(RENDER_LIGHTING_KEYS))
        self.assertEqual({"color", "transparent", "ground", "groundPlacement"}, set(RENDER_BACKDROP_KEYS))

        invalid = (
            {"exposure": True}, {"exposure": "0"}, {"exposure": -5.01}, {"exposure": 5.01},
            {"lighting": []}, {"lighting": {"rotation": float("inf")}},
            {"lighting": {"rotation": -180.01}}, {"lighting": {"size": 0.24}},
            {"lighting": {"size": 3.01}}, {"lighting": {"fill": -0.01}},
            {"lighting": {"fill": 1.01}}, {"lighting": {"fill": False}},
            {"lighting": {"key": 1}}, {"backdrop": []},
            {"backdrop": {"color": "white"}}, {"backdrop": {"transparent": 1}},
            {"backdrop": {"ground": "true"}}, {"backdrop": {"floor": True}},
            {"backdrop": {"groundPlacement": "auto"}},
        )
        for render_value in invalid:
            with self.subTest(render=render_value), self.assertRaises(SnapshotError):
                load_display_option({"mode": "render", "render": render_value}, cwd=Path("."))

    def test_camera_is_top_level_and_render_settings_require_render_mode(self):
        with self.assertRaisesRegex(SnapshotError, r"display.render has unknown key\(s\): camera"):
            load_display_option({"mode": "render", "render": {"camera": {"preset": "front"}}}, cwd=Path("."))
        with self.assertRaisesRegex(SnapshotError, "requires display.mode 'render'"):
            load_display_option({"mode": "shaded", "render": {}}, cwd=Path("."))

    def test_animation_and_output_capture_controls_remain_composable(self):
        job = normalize(
            camera={"preset": "front"}, display={"mode": "render"},
            animation={"clip": "spin", "time": 0.5},
            output={"sizeProfile": "diagnostic", "viewLabels": True},
        )
        self.assertEqual(job["camera"], {"preset": "front"})
        self.assertEqual(job["display"]["mode"], "render")
        self.assertEqual(job["animation"], {"clip": "spin", "time": 0.5})
        self.assertEqual(job["output"], {"sizeProfile": "diagnostic", "viewLabels": True})

    def test_public_api_has_one_display_surface_and_no_render_parameter(self):
        from cadgen import step
        signature = inspect.signature(step.snapshot)
        self.assertIn("display", signature.parameters)
        self.assertIn("camera", signature.parameters)
        self.assertNotIn("render", signature.parameters)

    def test_output_and_quality_are_closed(self):
        output = {
            "sizeProfile": "diagnostic", "padding": 0.1, "paddingPercent": 0.1,
            "viewLabels": True, "tightFrame": True, "transparent": True, "renderScale": 2,
        }
        self.assertEqual(set(output), set(SUPPORTED_OUTPUT_SETTINGS_KEYS))
        self.assertEqual({"tessellation"}, set(SUPPORTED_QUALITY_KEYS))
        normalize(output=output, quality={"tessellation": {"chordTolerance": 0.001}})
        with self.assertRaisesRegex(SnapshotError, "output has unknown key"):
            normalize(output={"pixels": 2})


class RenderTessellationLimitsTest(unittest.TestCase):
    def test_unknown_field_and_non_numbers_are_refused(self):
        for value in ({"quality": "high"}, {"chordTolerance": "0.001"}, {"chordTolerance": True}):
            with self.assertRaises(SnapshotError):
                validate_render_tessellation(value)
        with self.assertRaises(SnapshotError):
            validate_render_tessellation([0.001])

    def test_tolerances_below_the_floor_are_refused_here_not_in_the_browser(self):
        with self.assertRaises(SnapshotError) as caught:
            normalize(quality={"tessellation": {"chordTolerance": 1e-12}})
        self.assertIn("at least 1e-05", str(caught.exception))
        with self.assertRaises(SnapshotError):
            normalize(quality={"tessellation": {"angleTolerance": 1e-6}})
        # The floors themselves, and everything coarser, are legal requests.
        validate_render_tessellation(dict(MIN_RENDER_TESSELLATION))
        validate_render_tessellation({"chordTolerance": 0.0005, "angleTolerance": 0.10})
        validate_render_tessellation(None)

    def test_the_floors_match_the_page_that_tessellates(self):
        source = repo_path("packages/core/src/common/source.js").read_text(encoding="utf-8")
        block = re.search(r"RENDER_TESSELLATION_FLOORS = Object\.freeze\(\{(.*?)\}\)", source, re.S)
        self.assertIsNotNone(block, "source.js no longer declares RENDER_TESSELLATION_FLOORS")
        declared = {
            key: float(value)
            for key, value in re.findall(r"(\w+):\s*([0-9.e-]+)", block.group(1))
        }
        self.assertEqual(declared, MIN_RENDER_TESSELLATION)


if __name__ == "__main__":
    unittest.main()
