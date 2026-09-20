"""Unified display, technical output, and tessellation are closed schemas."""

from __future__ import annotations

import inspect
import re
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_core import (  # noqa: E402
    MIN_RENDER_TESSELLATION,
    DISPLAY_APPEARANCES,
    DISPLAY_GROUP_KEYS,
    DISPLAY_MODES,
    RENDER_QUALITY_IDS,
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
    def test_presets_and_appearance_are_closed(self):
        self.assertEqual({"solid", "render", "xray", "hidden-line", "wireframe"}, set(DISPLAY_MODES))
        self.assertEqual({"light", "dark"}, set(DISPLAY_APPEARANCES))
        self.assertEqual({"preview", "final"}, set(RENDER_QUALITY_IDS))
        for mode in DISPLAY_MODES:
            self.assertEqual({"mode": mode}, load_display_option(mode, cwd=Path(".")))
        for invalid in ("shaded", "transparent", "hidden_edges", "unshaded", None, True, [], {}):
            with self.subTest(mode=invalid), self.assertRaises(SnapshotError):
                load_display_option({"mode": invalid}, cwd=Path("."))
        for invalid in ("system", "LIGHT", None, False, [], {}):
            with self.subTest(appearance=invalid), self.assertRaises(SnapshotError):
                load_display_option({"appearance": invalid}, cwd=Path("."))

    def test_preset_names_do_not_depend_on_existing_output_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "render").mkdir()
            self.assertEqual({"mode": "render"}, load_display_option("render", cwd=root))

    def test_groups_are_strict_sparse_overrides_in_every_mode(self):
        display = {
            "mode": "solid", "appearance": "dark",
            "camera": {"projection": "perspective", "focalLength": 85},
            "surfaces": {"style": "flat", "colorMode": "by-part", "colors": ["#abc"], "opacity": 0.5},
            "edges": {"visibility": "all", "color": "#123456"},
            "lighting": {"quality": "preview", "exposure": -1.25, "rotation": 180, "size": 0.25, "fill": 1},
            "background": {"color": "#abc", "opacity": 0.4},
            "floor": {"enabled": False, "placement": "origin", "opacity": 0.6},
            "grid": {}, "axes": {"enabled": False},
            "clip": {"enabled": True, "axis": "z", "offsets": {"z": 0.5}},
            "exploded": {"enabled": True, "amount": 0.5},
        }
        self.assertEqual(display, load_display_option(display, cwd=Path(".")))
        for name in DISPLAY_GROUP_KEYS:
            self.assertEqual({name: {}}, load_display_option({name: {}}, cwd=Path(".")))
            for invalid in (None, True, [], "off", {"typo": True}, {"enabled": 1}):
                with self.subTest(group=name, invalid=invalid), self.assertRaises(SnapshotError):
                    load_display_option({name: invalid}, cwd=Path("."))

    def test_group_numbers_and_values_are_strict(self):
        invalid = (
            {"lighting": {"exposure": True}}, {"lighting": {"exposure": "0"}},
            {"lighting": {"exposure": -5.01}}, {"lighting": {"rotation": float("inf")}},
            {"lighting": {"rotation": -180.01}}, {"lighting": {"size": 0.24}},
            {"lighting": {"size": 3.01}}, {"lighting": {"fill": -0.01}},
            {"lighting": {"fill": 1.01}}, {"lighting": {"quality": "high"}},
            {"background": {"color": "white"}}, {"background": {"opacity": True}},
            {"background": {"opacity": -0.1}}, {"background": {"opacity": 1.1}},
            {"floor": {"placement": "auto"}}, {"floor": {"color": "blue"}},
            {"camera": {"focalLength": 19.9}}, {"camera": {"focalLength": 200.1}},
            {"camera": {"projection": "ortho"}}, {"surfaces": {"style": "smooth"}},
            {"surfaces": {"colorMode": "by_part"}}, {"surfaces": {"colors": []}},
            {"surfaces": {"colors": ["white"]}}, {"edges": {"visibility": "hidden"}},
        )
        for display in invalid:
            with self.subTest(display=display), self.assertRaises(SnapshotError):
                load_display_option(display, cwd=Path("."))

    def test_old_nested_surfaces_are_rejected(self):
        for key in ("render", "guides", "partColor"):
            with self.subTest(key=key), self.assertRaises(SnapshotError):
                load_display_option({key: {}}, cwd=Path("."))

    def test_default_job_is_light_solid_without_overriding_groups(self):
        self.assertEqual({"mode": "solid", "appearance": "light"}, normalize()["display"])
        self.assertEqual({"mode": "render", "appearance": "light"}, normalize(display={"mode": "render"})["display"])
        self.assertEqual({"mode": "solid", "appearance": "dark", "background": {"opacity": 0.3}},
                         normalize(display={"appearance": "dark", "background": {"opacity": 0.3}})["display"])

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
