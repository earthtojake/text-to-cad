"""Python snapshots accept exactly the shared scene/camera/display vocabulary."""

from __future__ import annotations

import json
import re
import subprocess
import unittest

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.snapshot_core import (  # noqa: E402
    CAMERA_OPTION_KEYS,
    DISPLAY_AXIS_GUIDE_KEYS,
    DISPLAY_CLIP_KEYS,
    DISPLAY_EDGE_KEYS,
    DISPLAY_EXPLODED_KEYS,
    DISPLAY_GRID_GUIDE_KEYS,
    DISPLAY_GUIDE_KEYS,
    DISPLAY_MODES,
    DISPLAY_OPTION_KEYS,
    DISPLAY_PART_COLOR_KEYS,
    PART_COLOR_MODES,
    RENDER_BACKDROP_KEYS,
    RENDER_LIGHTING_KEYS,
    RENDER_QUALITY_IDS,
    RENDER_STUDIO_IDS,
    SUPPORTED_RENDER_KEYS,
    SnapshotError,
    validate_camera_option,
    validate_display_render_settings,
    validate_display_settings_values,
)

SCENE = repo_path("packages/core/src/common/sceneSettings.js")
CAMERA = repo_path("packages/core/src/common/camera.js")
DISPLAY = repo_path("packages/core/src/common/displaySettings.js")


def exported_strings(path, export: str) -> set[str]:
    source = path.read_text(encoding="utf-8")
    match = re.search(
        rf"export const {re.escape(export)}\s*=\s*Object\.freeze\(\[(.*?)\]\);",
        source,
        re.S,
    )
    assert match, f"{path.name} no longer exports {export} as a frozen array"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def frozen_enum_values(path, export: str, next_export: str) -> set[str]:
    source = path.read_text(encoding="utf-8")
    start = source.index(f"export const {export} =")
    end = source.index(f"export const {next_export}", start)
    return set(re.findall(r':\s*"([^"]+)"', source[start:end]))


class SharedSceneContractParityTests(unittest.TestCase):
    def test_retired_top_level_render_field_is_rejected_by_shared_js(self):
        cases = [
            {},
            {"display": {"mode": "wireframe"}},
            {"display": {"mode": "render"}},
            {"display": {"mode": "render", "render": {"quality": "preview"}}, "camera": {"preset": "front"}},
            {"render": {}},
        ]
        validator = repo_path("packages/core/src/common/snapshotJobValidation.js")
        script = f"""
import fs from "node:fs";
import {{ validateSnapshotRenderJob }} from {json.dumps(validator.as_uri())};
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map((job) => {{
  try {{ validateSnapshotRenderJob(job); return true; }}
  catch {{ return false; }}
}})));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            input=json.dumps(cases), text=True, capture_output=True, check=True,
            cwd=repo_path(),
        )
        self.assertEqual([True, True, True, True, False], json.loads(completed.stdout))

    def test_render_envelope_keys_match(self):
        self.assertEqual(exported_strings(SCENE, "RENDER_PAYLOAD_KEYS"), set(SUPPORTED_RENDER_KEYS))

    def test_studio_ids_match(self):
        self.assertEqual(
            frozen_enum_values(SCENE, "RENDER_STUDIO", "RENDER_STUDIO_PRESETS"),
            set(RENDER_STUDIO_IDS),
        )

    def test_render_quality_and_nested_keys_match(self):
        self.assertEqual(
            frozen_enum_values(SCENE, "RENDER_QUALITY", "RENDER_QUALITY_PRESETS"),
            set(RENDER_QUALITY_IDS),
        )
        self.assertEqual(exported_strings(SCENE, "RENDER_LIGHTING_KEYS"), set(RENDER_LIGHTING_KEYS))
        self.assertEqual(exported_strings(SCENE, "RENDER_BACKDROP_KEYS"), set(RENDER_BACKDROP_KEYS))

    def test_strict_render_values_match_shared_js(self):
        cases = [
            {},
            {"studio": "light", "quality": "final", "exposure": 0},
            {"studio": "studio-light"},
            {"studio": []},
            {"studio": {}},
            {"studio": True},
            {"studio": None},
            {"quality": "high"},
            {"quality": []},
            {"quality": {}},
            {"quality": False},
            {"quality": None},
            {"display": {}},
            {"settings": {}},
            {"appearance": "dark"},
            {"_comment": "unsupported"},
            {"exposure": True},
            {"exposure": 5.01},
            {"lighting": {"rotation": -180, "size": 0.25, "fill": 1}},
            {"lighting": {"rotation": -180.01}},
            {"lighting": {"size": "1"}},
            {"lighting": {"fill": False}},
            {"lighting": {"key": 1}},
            {"backdrop": {"color": "#abc", "transparent": False, "ground": True}},
            {"backdrop": {"color": "white"}},
            {"backdrop": {"transparent": 0}},
            {"backdrop": {"floor": True}},
        ]
        script = f"""
import fs from "node:fs";
import {{ normalizeRenderPayload }} from {json.dumps(SCENE.as_uri())};
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map((render) => {{
  try {{ normalizeRenderPayload(render); return true; }}
  catch {{ return false; }}
}})));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            input=json.dumps(cases),
            text=True,
            capture_output=True,
            check=True,
            cwd=repo_path(),
        )
        js_accepted = json.loads(completed.stdout)
        python_accepted = []
        for render in cases:
            try:
                validate_display_render_settings(render, source_label="parity test")
            except SnapshotError:
                python_accepted.append(False)
            else:
                python_accepted.append(True)
        self.assertEqual(js_accepted, python_accepted)
        self.assertEqual(
            [True, True, False, False, False, False, False, False, False, False,
             False, False, False, False, False, False, False, False, True, False, False,
             False, False, True, False, False, False],
            python_accepted,
        )

    def test_camera_keys_match(self):
        self.assertEqual(exported_strings(CAMERA, "CAMERA_SPEC_KEYS"), set(CAMERA_OPTION_KEYS))

    def test_malformed_camera_numbers_fail_in_python_and_shared_js(self):
        malformed = [
            {"position": [1, 2, "3"]},
            {"target": [1, 2, True]},
            {"up": None},
            {"direction": [1, 2, 3, 4]},
            {"zoom": "2"},
            {"zoom": True},
            {"zoom": None},
            {"orthographicHalfHeight": "12"},
            {"orthographicHalfHeight": False},
            {"orthographicHalfHeight": None},
            {"focalLength": "50"},
            {"focalLength": True},
            {"focalLength": 19.9},
            {"focalLength": 200.1},
            {"focalLength": None},
        ]
        script = f"""
import fs from "node:fs";
import {{ normalizeCameraSpec }} from {json.dumps(CAMERA.as_uri())};
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map((camera) => {{
  try {{ normalizeCameraSpec(camera, {{ strict: true }}); return true; }}
  catch {{ return false; }}
}})));
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            input=json.dumps(malformed),
            text=True,
            capture_output=True,
            check=True,
            cwd=repo_path(),
        )
        js_accepted = json.loads(completed.stdout)
        python_accepted = []
        for camera in malformed:
            try:
                validate_camera_option(camera, source_label="parity test")
            except SnapshotError:
                python_accepted.append(False)
            else:
                python_accepted.append(True)
        self.assertEqual(js_accepted, python_accepted)
        self.assertEqual([False] * len(malformed), python_accepted)

    def test_display_keys_match(self):
        self.assertEqual(exported_strings(DISPLAY, "DISPLAY_SETTINGS_KEYS"), set(DISPLAY_OPTION_KEYS))

    def test_display_modes_match(self):
        self.assertEqual(
            frozen_enum_values(DISPLAY, "CAD_DISPLAY_MODE", "CAD_DISPLAY_MODE_VALUES"),
            set(DISPLAY_MODES),
        )
        self.assertEqual(
            frozen_enum_values(DISPLAY, "CAD_PART_COLOR_MODE", "CAD_PART_COLOR_MODE_VALUES"),
            set(PART_COLOR_MODES),
        )

    def test_nested_display_keys_match(self):
        pairs = {
            "DISPLAY_EDGE_SETTINGS_KEYS": DISPLAY_EDGE_KEYS,
            "DISPLAY_GUIDE_SETTINGS_KEYS": DISPLAY_GUIDE_KEYS,
            "DISPLAY_GRID_GUIDE_SETTINGS_KEYS": DISPLAY_GRID_GUIDE_KEYS,
            "DISPLAY_AXIS_GUIDE_SETTINGS_KEYS": DISPLAY_AXIS_GUIDE_KEYS,
            "DISPLAY_PART_COLOR_SETTINGS_KEYS": DISPLAY_PART_COLOR_KEYS,
            "DISPLAY_EXPLODED_SETTINGS_KEYS": DISPLAY_EXPLODED_KEYS,
            "DISPLAY_CLIP_SETTINGS_KEYS": DISPLAY_CLIP_KEYS,
        }
        for exported, expected in pairs.items():
            with self.subTest(export=exported):
                self.assertEqual(exported_strings(DISPLAY, exported), set(expected))
        self.assertEqual(set(DISPLAY_EDGE_KEYS), {"enabled", "silhouette"})
        self.assertEqual(set(DISPLAY_GRID_GUIDE_KEYS), {"enabled"})

    def test_snapshot_and_viewer_accept_only_edge_visibility_and_grid_toggle(self):
        cases = [
            {"edges": {"enabled": True, "silhouette": False}},
            {"guides": {"grid": {"enabled": False}}},
            *({"edges": {key: value}} for key, value in (
                ("color", "#ffffff"), ("thickness", 3), ("opacity", 0.5),
                ("classes", {"feature": {"thickness": 2}}), ("highlightThickness", 3),
            )),
            *({"guides": {"grid": {key: value}}} for key, value in (
                ("density", 2), ("opacity", 0.5), ("cellColor", "#ffffff"), ("centerColor", "#000000"),
            )),
        ]
        script = f'''
import fs from "node:fs";
import {{ validateDisplaySettings }} from {json.dumps(DISPLAY.as_uri())};
console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,"utf8")).map(value => {{
  try {{ validateDisplaySettings(value); return true; }} catch {{ return false; }}
}})));
'''
        completed = subprocess.run(["node", "--input-type=module", "-e", script],
                                   input=json.dumps(cases), text=True, capture_output=True, check=True)
        accepted = []
        for case in cases:
            try:
                validate_display_settings_values(case, source_label="fixed ink parity")
            except SnapshotError:
                accepted.append(False)
            else:
                accepted.append(True)
        self.assertEqual(accepted, [True, True] + [False] * 9)
        self.assertEqual(accepted, json.loads(completed.stdout))

if __name__ == "__main__":
    unittest.main()
