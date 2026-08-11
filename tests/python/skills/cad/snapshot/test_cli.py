from __future__ import annotations

import asyncio
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlparse

from tests.python.support.paths import add_repo_path, repo_path


def write_package(step_path, *, entry_kind="part", source_kind="step"):
    """Materialize the canonical render artifact for ``step_path``: a SELF-CONTAINED
    component-GLB PACKAGE directory inside the per-folder cache
    (``__cadgen__/models/<step-filename>/assembly.json``) whose content-addressed component
    GLBs live in the package's own ``components/<hash>.glb`` dir. Returns the package directory
    path, mirroring ``cadgen.catalog.render_package_dir``."""
    step_path = Path(step_path)
    pkg_dir = step_path.parent / "__cadgen__" / "models" / step_path.name
    comp_dir = pkg_dir / "components"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    comp_dir.mkdir(parents=True, exist_ok=True)
    cid = hashlib.sha256(str(step_path).encode()).hexdigest()[:16]
    (comp_dir / f"{cid}.glb").write_bytes(b"component-glb")
    (pkg_dir / "assembly.json").write_text(
        json.dumps(
            {
                "kind": "assembly-package",
                "packageSchemaVersion": 2,
                "entryKind": entry_kind,
                "rootName": step_path.stem,
                "units": "mm",
                "sourceKind": source_kind,
                "stepPath": step_path.name,
                "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]},
                "stats": {"occurrenceCount": 1, "shapeCount": 1},
                "components": {cid: {"glb": f"components/{cid}.glb", "contentHash": cid}},
                "occurrences": [
                    {
                        "id": "o1.1",
                        "name": "occ",
                        "component": cid,
                        "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                    }
                ],
            }
        )
    )
    return pkg_dir

add_repo_path("skills/cad/scripts")
add_repo_path("packages/cadgen/src")

# The CLI itself is shared (cadgen.snapshot_cli); the CAD skill's entrypoint is the
# declaration of which kinds it accepts and where its runtime lives. These tests exercise
# the CAD skill's behaviour, so they drive the shared implementation through that skill's
# runtime directory.
import cadgen.snapshot_cli as snapshot_main
import snapshot.__main__ as cad_snapshot_entry
from cadgen.snapshot_cli import (
    SnapshotError,
    load_job_from_options,
    parse_snapshot_args,
    resolve_render_job_packet,
    resolve_snapshot_route_file,
    timestamp_output_path,
)

RUNTIME_DIR = cad_snapshot_entry.RUNTIME_DIR
RENDER_HTML_PATH = RUNTIME_DIR / "render.html"
CAD_KINDS = snapshot_main.enabled_kinds(cad_snapshot_entry.KINDS)


class _TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


def _selector_artifact(*occurrence_ids: str) -> SimpleNamespace:
    return SimpleNamespace(
        selector_bundle=SimpleNamespace(
            manifest={
                "tables": {
                    "occurrenceColumns": ["id"],
                    "shapeColumns": ["id", "occurrenceId"],
                },
                "occurrences": [[occurrence_id] for occurrence_id in occurrence_ids],
                "shapes": [],
            },
            buffers={},
        )
    )


class SnapshotCliTests(unittest.TestCase):
    def test_cli_import_does_not_import_heavy_cad_modules(self) -> None:
        skill_root = repo_path("skills/cad")
        code = (
            "import sys; sys.path.insert(0, 'scripts'); import snapshot.__main__; "
            "print('OCP.OCP' in sys.modules); "
            "print('cadgen._internal.step_scene' in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=skill_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertEqual(["False", "False"], result.stdout.strip().splitlines())

    def test_shortcut_job_shape_stays_owned_by_python_cli(self) -> None:
        options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--display",
                "wireframe",
                "--size-profile",
                "simple",
            ]
        )

        job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())

        self.assertEqual(job["input"], "models/step/parts/cylindrical_cap.step")
        self.assertNotIn("workspaceRoot", job)
        self.assertNotIn("rootDir", job)
        self.assertEqual(job["outputs"][0]["path"], "tmp/cap.png")
        self.assertEqual(job["display"], {"mode": "wireframe"})
        self.assertEqual(job["render"]["sizeProfile"], "simple")

    def test_shortcut_focus_and_hide_flags_are_mutually_exclusive(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "--focus and --hide cannot be used"):
            parse_snapshot_args(
                [
                    "--input",
                    "models/assembly.step",
                    "--output",
                    "tmp/assembly.png",
                    "--focus",
                    "#o1.2",
                    "--hide=#o1.3.1",
                ]
            )

    def test_display_shortcut_accepts_cad_display_modes(self) -> None:
        for raw_mode, expected_display in [
            ("edges", {"mode": "solid"}),
            ("x-ray", {"mode": "transparent"}),
            ("hidden edges visible", {"mode": "hidden_edges"}),
            ("hidden-lines-removed", {"mode": "hidden_lines_removed"}),
            ("flat", {"mode": "unshaded"}),
            ("theme", {"mode": "rendered"}),
            ("wire", {"mode": "wireframe"}),
        ]:
            options = parse_snapshot_args(
                [
                    "--input",
                    "models/step/parts/cylindrical_cap.step",
                    "--output",
                    "tmp/cap.png",
                    "--display",
                    raw_mode,
                ]
            )
            job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())
            self.assertEqual(job["display"], expected_display)

    def test_display_json_accepts_exploded_settings(self) -> None:
        options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--display",
                '{"projection":"perspective","mode":"rendered","exploded":{"enabled":true,"amount":0.7}}',
            ]
        )
        job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())
        self.assertEqual(
            job["display"],
            {
                "projection": "perspective",
                "mode": "rendered",
                "exploded": {"enabled": True, "amount": 0.7},
            },
        )

    def _display_job(self, display_json: str):
        options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--display",
                display_json,
            ]
        )
        return load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())

    def test_display_json_rejects_bad_projection_value(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "projection must be orthographic or perspective"):
            self._display_job('{"projection":"ortho"}')

    def test_display_json_rejects_bad_mode_value(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "--display mode must be one of"):
            self._display_job('{"mode":"shadedd"}')

    def test_display_json_rejects_retired_exploded_keys(self) -> None:
        # The exploded view is enabled + amount only; retired step-document/auto-hint
        # fields would silently no-op in the renderer, so the CLI rejects them loudly.
        with self.assertRaisesRegex(SnapshotError, "exploded supports only enabled and amount"):
            self._display_job('{"exploded":{"axis":"z"}}')
        with self.assertRaisesRegex(SnapshotError, "exploded supports only enabled and amount"):
            self._display_job('{"exploded":{"enabled":true,"auto":{"mode":"radial"}}}')
        with self.assertRaisesRegex(SnapshotError, "exploded supports only enabled and amount"):
            self._display_job('{"exploded":{"enabled":true,"steps":[]}}')

    def test_display_json_accepts_valid_closed_set_values(self) -> None:
        self.assertEqual(self._display_job('{"projection":"orthographic"}')["display"], {"projection": "orthographic"})
        self.assertEqual(self._display_job('{"mode":"shaded"}')["display"], {"mode": "shaded"})
        self.assertEqual(
            self._display_job('{"exploded":{"enabled":true,"amount":1}}')["display"],
            {"exploded": {"enabled": True, "amount": 1}},
        )

    def test_display_json_treats_empty_string_values_as_unset(self) -> None:
        # The renderer treats an empty string as absent and falls back to the default, so
        # validation must not false-reject empty strings an agent emits for unset fields.
        self.assertEqual(self._display_job('{"projection":""}')["display"], {"projection": ""})
        self.assertEqual(self._display_job('{"mode":""}')["display"], {"mode": ""})

    def test_edge_settings_belong_to_display_json(self) -> None:
        options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--display",
                '{"edges":{"enabled":false,"color":"#123456"}}',
            ]
        )
        job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())
        self.assertEqual(job["display"], {"edges": {"enabled": False, "color": "#123456"}})

        theme_options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--theme",
                '{"edges":{"enabled":false}}',
            ]
        )
        with self.assertRaisesRegex(SnapshotError, "unsupported keys: edges"):
            load_job_from_options(theme_options, stdin=_TtyStringIO(), cwd=Path.cwd())

    def test_theme_accepts_a_full_theme_preset_clone(self) -> None:
        # cloneThemePresetSettings() emits colorMode, projection and modeColors
        # alongside the five settings blocks. Rejecting any of them meant the
        # repo's own theme-clone output could not be passed back to
        # --theme without hand-stripping keys first.
        options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--theme",
                json.dumps(
                    {
                        "colorMode": "light",
                        "projection": "perspective",
                        "materials": {"roughness": 0.5},
                        "background": {"solidColor": "#ffffff"},
                        "floor": {"color": "#b7b6b2"},
                        "environment": {"enabled": True},
                        "lighting": {"toneMappingExposure": 1.1},
                        "modeColors": {"light": {"background": {"solidColor": "#ffffff"}}},
                    }
                ),
            ]
        )
        job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())
        self.assertIn("modeColors", job["theme"])

    def test_display_shortcut_rejects_unknown_modes(self) -> None:
        options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--display",
                "mist",
            ]
        )
        with self.assertRaisesRegex(SnapshotError, "Unsupported display mode"):
            load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())

    def test_display_shortcut_rejects_exploded_mode_alias(self) -> None:
        options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--display",
                "exploded",
            ]
        )
        with self.assertRaisesRegex(SnapshotError, "Unsupported display mode"):
            load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())

    def test_shortcut_focus_flags_apply_selection(self) -> None:
        options = parse_snapshot_args(
            [
                "--input",
                "models/assembly.step",
                "--output",
                "tmp/assembly.png",
                "--focus",
                "#o1.2",
                "#o1.3",
            ]
        )

        job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())

        self.assertEqual(
            job["selection"],
            {
                "focus": ["#o1.2", "#o1.3"],
            },
        )

    def test_output_paths_are_timestamped_when_jobs_are_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "part.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "part.step")

            original_timestamp = snapshot_main.snapshot_timestamp
            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.snapshot_timestamp = lambda: "20260527T163012Z"
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None

                packet = resolve_render_job_packet(
                    {
                        "jobs": [
                            {
                                "input": "models/part.step",
                                "outputs": [
                                    {"path": "tmp/iso.png", "camera": "iso"},
                                    {"path": "tmp/front.png", "camera": "front"},
                                ],
                            },
                            {
                                "input": "models/part.step",
                                "mode": "orbit",
                                "outputs": [{"path": "tmp/orbit.gif"}],
                            },
                        ]
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.snapshot_timestamp = original_timestamp
                snapshot_main.ensure_step_topology_artifact = original_ensure

            output_paths = [
                Path(output["path"]).relative_to(root).as_posix()
                for job in packet["jobs"]
                for output in job["outputs"]
            ]

        self.assertEqual(
            output_paths,
            [
                "tmp/iso_20260527T163012Z.png",
                "tmp/front_20260527T163012Z.png",
                "tmp/orbit_20260527T163012Z.gif",
            ],
        )

    def test_render_job_derives_asset_root_from_input_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "part.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "part.step")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
                packet = resolve_render_job_packet(
                    {
                        "input": "models/part.step",
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        job = packet["jobs"][0]
        self.assertNotIn("workspaceRoot", job)
        self.assertNotIn("rootDir", job)
        self.assertEqual(job["resolved"]["rootPath"], str(models))
        input_url = urlparse(job["resolved"]["inputUrl"])
        self.assertEqual(input_url.path, "/__render_asset/part.step")
        self.assertRegex(parse_qs(input_url.query)["v"][0], r"^[0-9a-f]{16}$")
        # The render artifact is a SELF-CONTAINED component-GLB package, so the resolved job
        # carries a package descriptor with per-component asset URLs (no monolithic glbUrl).
        # Each component URL points into the package's own components/ dir inside __cadgen__.
        self.assertNotIn("glbUrl", job["resolved"])
        package = job["resolved"]["package"]
        self.assertEqual(package["descriptor"]["kind"], "assembly-package")
        component_urls = package["componentUrls"]
        self.assertTrue(component_urls)
        for component_url in component_urls.values():
            parsed_component_url = urlparse(component_url)
            self.assertTrue(
                parsed_component_url.path.startswith(
                    "/__render_asset/__cadgen__/models/part.step/components/"
                ),
                component_url,
            )
            self.assertRegex(parse_qs(parsed_component_url.query)["v"][0], r"^[0-9a-f]{16}$")

    def test_multijob_asset_urls_do_not_collide_across_render_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            for folder_name in ("first", "second"):
                folder = root / folder_name
                folder.mkdir()
                (folder / "model.step").write_text(
                    "ISO-10303-21;\nEND-ISO-10303-21;\n",
                    encoding="utf-8",
                )
                write_package(folder / "model.step")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
                packet = resolve_render_job_packet(
                    {
                        "jobs": [
                            {
                                "input": "first/model.step",
                                "outputs": [{"path": "first.png"}],
                            },
                            {
                                "input": "second/model.step",
                                "outputs": [{"path": "second.png"}],
                            },
                        ]
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        first_resolved = packet["jobs"][0]["resolved"]
        second_resolved = packet["jobs"][1]["resolved"]
        # Each job's render root is its own folder, so both inputs land on the same
        # basename-relative asset path. Only the ?v= key keeps the shared browser
        # runtime from serving the first job's file for the second job's URL.
        self.assertEqual(
            urlparse(first_resolved["inputUrl"]).path,
            urlparse(second_resolved["inputUrl"]).path,
        )
        self.assertNotEqual(
            first_resolved["inputUrl"],
            second_resolved["inputUrl"],
        )

    def test_asset_url_unversioned_for_generator_input_without_step_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            missing_step = root / "model.step"
            self.assertFalse(missing_step.exists())
            url = snapshot_main.asset_url_for_path(missing_step, root)
        self.assertEqual(url, "/__render_asset/model.step")

    def test_asset_url_does_not_swallow_unexpected_stat_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            asset = root / "model.step"
            asset.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

            # Resolve up front: on Python 3.12 Path.resolve() calls Path.stat()
            # internally, so resolving inside the patch would recurse forever.
            resolved_asset = asset.resolve()
            original_stat = Path.stat

            def denying_stat(self, *args, **kwargs):
                if self == resolved_asset:
                    raise PermissionError(13, "stat denied", str(self))
                return original_stat(self, *args, **kwargs)

            with mock.patch.object(Path, "stat", denying_stat):
                with self.assertRaises(PermissionError):
                    snapshot_main.asset_url_for_path(asset, root)

    def test_render_job_ensures_step_artifact_for_step_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            step_path = models / "part.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(step_path)
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append((target, kwargs))
                return None

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                resolve_render_job_packet(
                    {
                        "input": "models/part.step",
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        self.assertEqual(len(calls), 1)
        target, kwargs = calls[0]
        self.assertEqual(target.step_path, step_path)
        self.assertEqual(target.source_path, step_path)
        self.assertFalse(kwargs["require_selector"])
        self.assertIsNone(kwargs["debug"])

    def test_debug_shortcut_flag_sets_job_debug_field(self) -> None:
        options = parse_snapshot_args(
            [
                "--input",
                "models/step/parts/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--debug",
            ]
        )
        job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())
        self.assertTrue(job["debug"])

    def test_render_job_surfaces_step_artifact_debug_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            step_path = models / "part.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(step_path)

            def fake_ensure(target, **kwargs):
                debug_info = kwargs.get("debug")
                if debug_info is not None:
                    debug_info.update(
                        {"source": "generated", "assembly": False, "cacheHit": True, "tookMs": 1.5}
                    )
                return None

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                packet = resolve_render_job_packet(
                    {
                        "input": "models/part.step",
                        "debug": True,
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        job = packet["jobs"][0]
        self.assertEqual(
            job["resolved"]["debug"],
            {"stepArtifact": {"source": "generated", "assembly": False, "cacheHit": True, "tookMs": 1.5}},
        )

    def test_job_level_display_values_are_validated(self) -> None:
        """A display object embedded in a full JSON job must hit the same closed-set
        validation as the --display flag path, or a typo'd value silently renders
        the default (the exact failure validate_display_settings_values exists for)."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            mesh_path = models / "part.stl"
            mesh_path.write_bytes(b"solid part\nendsolid part\n")
            job = {
                "input": "models/part.stl",
                "display": {"projection": "ortho"},
                "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
            }
            with self.assertRaisesRegex(SnapshotError, "projection must be orthographic or perspective"):
                resolve_render_job_packet(job, cwd=root)
            job["display"] = {"projection": "orthographic"}
            packet = resolve_render_job_packet(job, cwd=root)
            self.assertEqual(packet["jobs"][0]["display"], {"projection": "orthographic"})

    def test_json_output_omits_output_payload_blobs(self) -> None:
        """--json must not echo the rendered bytes back. dataUrl/text are how the browser
        returns them for write_output_payload to decode; by print time the file is on disk and
        `path` names it. Echoing them cost 228 KB of stdout for one PNG and 1.7 MB -- ~445k
        tokens -- for an orbit GIF. The one test that covered this path used an empty outputs
        list, which is why it shipped."""
        data_url = "data:image/png;base64," + "A" * 4096
        svg_text = "<svg>" + "x" * 4096 + "</svg>"
        result = {
            "ok": True,
            "jobs": [
                {
                    "ok": True,
                    "mode": "view",
                    "outputs": [
                        {"path": "/tmp/a.png", "width": 800, "height": 600, "dataUrl": data_url},
                        {"path": "/tmp/b.svg", "text": svg_text},
                    ],
                }
            ],
        }
        stream = io.StringIO()
        snapshot_main.print_render_result(result, json_output=True, stdout=stream)
        printed = stream.getvalue()
        self.assertNotIn("dataUrl", printed)
        self.assertNotIn(data_url, printed)
        self.assertNotIn(svg_text, printed)
        # Everything a caller actually uses survives.
        outputs = json.loads(printed)["jobs"][0]["outputs"]
        self.assertEqual([output["path"] for output in outputs], ["/tmp/a.png", "/tmp/b.svg"])
        self.assertEqual(outputs[0]["width"], 800)
        # The caller's dict keeps its payload: write_output_payload reads the same object.
        self.assertEqual(result["jobs"][0]["outputs"][0]["dataUrl"], data_url)

    def test_debug_reaches_rendered_json_output(self) -> None:
        """--debug diagnostics are attached at resolve time, but the printed result is the
        browser's return value — the render stage must merge them in or the help text's
        promised "debug" section never appears in --json output."""

        class StubRenderer:
            async def render(self, job):
                return {"ok": True, "mode": "view", "outputs": []}

            async def close(self):
                return None

        debug_payload = {"stepArtifact": {"source": "generated", "cacheHit": True, "tookMs": 1.5}}
        job = {
            "input": "models/part.step",
            "resolved": {"debug": debug_payload},
        }

        result = asyncio.run(
            snapshot_main.render_resolved_job_packet(
                {"single": True, "jobs": [job]}, runtime_dir=RUNTIME_DIR, renderer=StubRenderer()
            )
        )
        self.assertEqual(result["debug"], debug_payload)
        stream = io.StringIO()
        snapshot_main.print_render_result(result, json_output=True, stdout=stream)
        self.assertEqual(json.loads(stream.getvalue())["debug"], debug_payload)

        multi = asyncio.run(
            snapshot_main.render_resolved_job_packet(
                {"single": False, "jobs": [job]}, runtime_dir=RUNTIME_DIR, renderer=StubRenderer()
            )
        )
        self.assertEqual(multi["jobs"][0]["debug"], debug_payload)

    def test_render_job_omits_debug_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            step_path = models / "part.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(step_path)
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append(kwargs)
                return None

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                packet = resolve_render_job_packet(
                    {
                        "input": "models/part.step",
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        self.assertIsNone(calls[0]["debug"])
        job = packet["jobs"][0]
        self.assertNotIn("debug", job["resolved"])

    def test_render_job_rejects_non_step_input_without_artifact_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            # A drawing. The shared CLI can resolve one, but the CAD skill does not enable
            # it -- so the rejection must name the skill that does, and must happen before
            # anything is built.
            (models / "panel.dxf").write_text("0\nSECTION\n", encoding="utf-8")
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append((target, kwargs))
                return None

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                with self.assertRaisesRegex(
                    SnapshotError,
                    r"does not render \.dxf.*inputs",
                ):
                    resolve_render_job_packet(
                        {
                            "input": "models/panel.dxf",
                            "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                        },
                        cwd=root,
                        kinds=CAD_KINDS,
                    )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        self.assertEqual(calls, [])

    def _mesh_job_env(self, temporary_directory, filename, content=b"mesh-bytes"):
        root = Path(temporary_directory).resolve()
        models = root / "models"
        models.mkdir()
        (models / filename).write_bytes(content)
        return root

    def test_render_job_resolves_direct_glb_without_step_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF-binary-bytes")
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append((target, kwargs))
                return None

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                packet = resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        # The STEP artifact pipeline must never be entered for a direct mesh.
        self.assertEqual(calls, [])
        resolved = packet["jobs"][0]["resolved"]
        self.assertEqual(resolved["kind"], "glb")
        self.assertEqual(urlparse(resolved["inputUrl"]).path, "/__render_asset/widget.glb")
        self.assertEqual(urlparse(resolved["url"]).path, "/__render_asset/widget.glb")
        self.assertEqual(resolved["rootPath"], str(root / "models"))
        self.assertNotIn("package", resolved)
        self.assertNotIn("stepParameterUrl", resolved)

    def test_render_job_resolves_direct_stl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "part.stl", b"solid test\nendsolid test\n")
            packet = resolve_render_job_packet(
                {
                    "input": "models/part.stl",
                    "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                },
                cwd=root,
            )
        resolved = packet["jobs"][0]["resolved"]
        self.assertEqual(resolved["kind"], "stl")
        self.assertEqual(urlparse(resolved["url"]).path, "/__render_asset/part.stl")

    def test_render_job_resolves_direct_3mf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "part.3mf")
            packet = resolve_render_job_packet(
                {
                    "input": "models/part.3mf",
                    "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                },
                cwd=root,
            )
        self.assertEqual(packet["jobs"][0]["resolved"]["kind"], "3mf")

    def test_render_job_surfaces_mesh_source_debug_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "part.stl", b"solid test\nendsolid test\n")
            packet = resolve_render_job_packet(
                {
                    "input": "models/part.stl",
                    "debug": True,
                    "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                },
                cwd=root,
            )
        self.assertEqual(packet["jobs"][0]["resolved"]["debug"], {"meshSource": {"kind": "stl"}})

    def test_render_job_surfaces_implicit_source_debug_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "pulse.implicit.js", b"export default {};\n")
            packet = resolve_render_job_packet(
                {
                    "input": "models/pulse.implicit.js",
                    "debug": True,
                    "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                },
                cwd=root,
            )
        self.assertEqual(packet["jobs"][0]["resolved"]["debug"], {"implicitSource": {"kind": "implicit"}})

    def test_render_job_rejects_top_level_selection_shaped_keys(self) -> None:
        # "hide"/"focus" at top level were historically dropped without a word,
        # so the render completed with nothing hidden. The rejection names the
        # correct selection-object shape.
        with self.assertRaisesRegex(SnapshotError, r'move "hide": \[\.\.\.\] into "selection"'):
            resolve_render_job_packet(
                {
                    "input": "models/part.step",
                    "hide": ["#o1.5"],
                    "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                }
            )

    def test_render_job_rejects_unknown_top_level_keys(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "unknown render job key\\(s\\): framerate"):
            resolve_render_job_packet(
                {
                    "input": "models/part.step",
                    "framerate": 24,
                    "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                }
            )

    def test_render_output_rejects_nested_selection(self) -> None:
        # A selection nested in an output is the documented multi-view trap:
        # selection is job-level only, so this used to render with nothing
        # hidden. The rejection says to split the view into its own job.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "selection applies at job level only"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "outputs": [
                            {
                                "path": "tmp/iso.png",
                                "camera": "iso",
                                "selection": {"hide": ["#o1.5"]},
                            }
                        ],
                    },
                    cwd=root,
                )

    def test_render_output_rejects_unknown_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "unknown key\\(s\\): stepParameters"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "outputs": [
                            {
                                "path": "tmp/iso.png",
                                "camera": "iso",
                                "stepParameters": {"width": 5},
                            }
                        ],
                    },
                    cwd=root,
                )

    def test_render_job_rejects_selection_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "selection focus/hide/refs require STEP topology"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "selection": {"focus": ["#o1.2"]},
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )

    def test_render_job_rejects_step_parameters_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "stepParameters require a STEP model"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "stepParameters": {"width": 5},
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )

    def test_render_job_rejects_step_parameters_path_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "stepParametersPath requires a STEP model"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "stepParametersPath": "models/widget.glb.js",
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )

    def test_render_job_rejects_section_mode_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "section mode requires STEP topology"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "mode": "section",
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )

    def test_render_job_rejects_hidden_edges_display_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            for hidden_mode in ("hidden_edges", "hidden_lines_removed"):
                with self.assertRaisesRegex(SnapshotError, "requires STEP CAD edges"):
                    resolve_render_job_packet(
                        {
                            "input": "models/widget.glb",
                            "display": {"mode": hidden_mode},
                            "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                        },
                        cwd=root,
                    )

    def test_render_job_rejects_exploded_display_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "exploded view requires STEP assembly"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "display": {"exploded": {"enabled": True, "amount": 1}},
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )

    def test_render_job_allows_list_mode_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            packet = resolve_render_job_packet(
                {"input": "models/widget.glb", "mode": "list"},
                cwd=root,
            )
        job = packet["jobs"][0]
        self.assertEqual(job["mode"], "list")
        self.assertEqual(job["resolved"]["kind"], "glb")

    def test_render_job_rejects_non_solid_display_mode_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            for non_solid in ("wireframe", "transparent", "unshaded"):
                with self.assertRaisesRegex(SnapshotError, "display mode is not supported"):
                    resolve_render_job_packet(
                        {
                            "input": "models/widget.glb",
                            "display": {"mode": non_solid},
                            "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                        },
                        cwd=root,
                    )

    def test_render_job_allows_solid_and_projection_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            # Solid mode + orthographic projection both pass (projection is honored by the
            # renderer; it is camera-only, not topology-dependent).
            packet = resolve_render_job_packet(
                {
                    "input": "models/widget.glb",
                    "display": {"mode": "solid", "projection": "orthographic"},
                    "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                },
                cwd=root,
            )
        self.assertEqual(packet["jobs"][0]["display"], {"mode": "solid", "projection": "orthographic"})

    def test_input_kind_detects_implicit_modules(self) -> None:
        self.assertEqual(snapshot_main.input_kind(Path("models/pulse.implicit.js")), "implicit")
        # A plain .js file is not an implicit model and stays unsupported.
        self.assertEqual(snapshot_main.input_kind(Path("models/helper.js")), "")

    def test_render_job_resolves_implicit_module_without_step_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "pulse.implicit.js", b"export default {};\n")
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append(kwargs)
                return None

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                packet = resolve_render_job_packet(
                    {
                        "input": "models/pulse.implicit.js",
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        # Implicit inputs skip the STEP artifact pipeline entirely.
        self.assertEqual(calls, [])
        job = packet["jobs"][0]
        resolved = job["resolved"]
        self.assertEqual(resolved["kind"], "implicit")
        self.assertTrue(urlparse(str(resolved["inputUrl"])).path.endswith("pulse.implicit.js"))
        self.assertEqual(resolved["inputUrl"], resolved["url"])

    def test_render_job_supports_orbit_for_implicit_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "pulse.implicit.js", b"export default {};\n")
            packet = resolve_render_job_packet(
                {"input": "models/pulse.implicit.js", "mode": "orbit", "outputs": [{"path": "tmp/orbit.gif"}]},
                cwd=root,
            )
        self.assertEqual(packet["jobs"][0]["mode"], "orbit")
        self.assertEqual(packet["jobs"][0]["resolved"]["kind"], "implicit")

    def test_render_job_rejects_static_gif_outside_orbit_mode(self) -> None:
        # A .gif output in a static job would silently save a single frame; the
        # CLI must instead point at orbit mode or animated params.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "pulse.implicit.js", b"export default {};\n")
            with self.assertRaisesRegex(SnapshotError, "renders a single frame.*--mode orbit"):
                resolve_render_job_packet(
                    {"input": "models/pulse.implicit.js", "outputs": [{"path": "tmp/spin.gif"}]},
                    cwd=root,
                )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "renders a single frame.*--mode orbit"):
                resolve_render_job_packet(
                    {"input": "models/widget.glb", "outputs": [{"path": "tmp/spin.gif", "camera": "iso"}]},
                    cwd=root,
                )

    def test_render_job_allows_gif_for_animated_step_parameters(self) -> None:
        # Animated --params sweeps legitimately render multi-frame GIFs in view
        # mode; the static-gif guard must not reject them.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "part.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            package_dir = write_package(models / "part.step")
            # stepParameters require a declared sidecar; point the descriptor at one.
            descriptor_path = Path(package_dir) / "assembly.json"
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            descriptor["paramsPath"] = "part.params.js"
            descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
            (models / "part.params.js").write_text("export default {};\n", encoding="utf-8")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
                packet = resolve_render_job_packet(
                    {
                        "input": "models/part.step",
                        "stepParameters": {"animate": {"from": {"width": 1}, "to": {"width": 2}}},
                        "outputs": [{"path": "tmp/sweep.gif"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        self.assertEqual(packet["jobs"][0]["mode"], "view")
        self.assertTrue(str(packet["jobs"][0]["outputs"][0]["path"]).endswith(".gif"))

    def test_render_job_rejects_step_only_options_for_implicit_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "pulse.implicit.js", b"export default {};\n")
            base = {"input": "models/pulse.implicit.js", "outputs": [{"path": "tmp/iso.png", "camera": "iso"}]}
            with self.assertRaisesRegex(SnapshotError, "list mode is not supported for implicit"):
                resolve_render_job_packet({**base, "mode": "list", "outputs": []}, cwd=root)
            with self.assertRaisesRegex(SnapshotError, "selection focus/hide/refs require STEP topology"):
                resolve_render_job_packet({**base, "selection": {"focus": ["#o1.2"]}}, cwd=root)
            with self.assertRaisesRegex(SnapshotError, "display mode is not supported for implicit"):
                resolve_render_job_packet({**base, "display": {"mode": "wireframe"}}, cwd=root)
            with self.assertRaisesRegex(SnapshotError, "exploded view requires STEP assembly"):
                resolve_render_job_packet(
                    {**base, "display": {"exploded": {"enabled": True, "amount": 1}}}, cwd=root
                )
            # stepParameters and section mode are STEP-only for implicit inputs too.
            with self.assertRaisesRegex(SnapshotError, "stepParameters require a STEP model"):
                resolve_render_job_packet({**base, "stepParameters": {"width": 5}}, cwd=root)
            with self.assertRaisesRegex(SnapshotError, "section mode is not supported for implicit"):
                resolve_render_job_packet({**base, "mode": "section"}, cwd=root)

    def test_input_kind_detects_robot_descriptions(self) -> None:
        self.assertEqual(snapshot_main.input_kind(Path("robots/arm.urdf")), "urdf")
        self.assertEqual(snapshot_main.input_kind(Path("robots/arm.srdf")), "srdf")
        self.assertEqual(snapshot_main.input_kind(Path("robots/arm.sdf")), "sdf")

    def test_render_job_resolves_robot_description_without_step_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "arm.urdf", b"<robot name='arm'/>\n")
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append(kwargs)
                return None

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                packet = resolve_render_job_packet(
                    {"input": "models/arm.urdf", "outputs": [{"path": "tmp/iso.png"}]},
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        # A robot assembles in the browser from its own description; no STEP pipeline.
        self.assertEqual(calls, [])
        job = packet["jobs"][0]
        resolved = job["resolved"]
        self.assertEqual(resolved["kind"], "urdf")
        self.assertTrue(urlparse(str(resolved["inputUrl"])).path.endswith("arm.urdf"))
        self.assertEqual(resolved["inputUrl"], resolved["url"])
        # Robots are authored in metres; the CAD profile would frame one for a workpiece a
        # thousand times its size.
        self.assertEqual(job["render"]["scale"], "urdf")

    def test_render_job_poses_a_robot_with_joint_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "arm.urdf", b"<robot name='arm'/>\n")
            packet = resolve_render_job_packet(
                {
                    "input": "models/arm.urdf",
                    "jointValues": {"shoulder_pan": 55, "elbow_flex": -20},
                    "outputs": [{"path": "tmp/iso.png"}],
                },
                cwd=root,
            )
            resolved = packet["jobs"][0]["resolved"]
            self.assertEqual(resolved["jointValues"], {"shoulder_pan": 55, "elbow_flex": -20})

            base = {"input": "models/arm.urdf", "outputs": [{"path": "tmp/iso.png"}]}
            with self.assertRaisesRegex(SnapshotError, "jointValues must be an object"):
                resolve_render_job_packet({**base, "jointValues": [1, 2]}, cwd=root)
            with self.assertRaisesRegex(SnapshotError, "must be a number"):
                resolve_render_job_packet({**base, "jointValues": {"j": "45"}}, cwd=root)

    def test_render_job_rejects_step_only_options_for_robot_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "arm.urdf", b"<robot name='arm'/>\n")
            base = {"input": "models/arm.urdf", "outputs": [{"path": "tmp/iso.png"}]}
            with self.assertRaisesRegex(SnapshotError, "selection focus/hide/refs require STEP topology"):
                resolve_render_job_packet({**base, "selection": {"focus": ["#o1"]}}, cwd=root)
            # A robot IS parametric, just not by STEP sidecar — the error says which key to use.
            with self.assertRaisesRegex(SnapshotError, "pose a URDF robot with jointValues"):
                resolve_render_job_packet({**base, "stepParameters": {"width": 5}}, cwd=root)
            with self.assertRaisesRegex(SnapshotError, "cannot be exploded"):
                resolve_render_job_packet(
                    {**base, "display": {"exploded": {"enabled": True, "amount": 1}}}, cwd=root
                )
            with self.assertRaisesRegex(SnapshotError, "section mode requires STEP topology"):
                resolve_render_job_packet({**base, "mode": "section"}, cwd=root)

    def test_render_job_missing_mesh_file_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            (root / "models").mkdir()
            with self.assertRaisesRegex(SnapshotError, "Render input does not exist"):
                resolve_render_job_packet(
                    {"input": "models/absent.stl", "outputs": [{"path": "tmp/iso.png"}]},
                    cwd=root,
                )

    def test_content_type_for_mesh_suffixes(self) -> None:
        self.assertEqual(snapshot_main.content_type_for_path(Path("x.stl")), "model/stl")
        self.assertEqual(snapshot_main.content_type_for_path(Path("x.3mf")), "model/3mf")
        self.assertEqual(snapshot_main.content_type_for_path(Path("x.glb")), "model/gltf-binary")

    def test_render_job_requires_selector_topology_for_cad_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            step_path = models / "assembly.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(step_path, entry_kind="assembly")
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append((target, kwargs))
                return _selector_artifact("o1", "o1.2")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                resolve_render_job_packet(
                    {
                        "input": "models/assembly.step",
                        "selection": {"focus": ["#o1.2"]},
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        self.assertEqual(len(calls), 1)
        target, kwargs = calls[0]
        self.assertEqual(target.step_path, step_path)
        self.assertTrue(kwargs["require_selector"])

    def test_render_job_normalizes_focus_selector_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "assembly.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "assembly.step", entry_kind="assembly")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: _selector_artifact(
                    "o1",
                    "o1.2",
                    "o1.2.1",
                    "o1.3",
                )
                packet = resolve_render_job_packet(
                    {
                        "input": "models/assembly.step",
                        "selection": {
                            "focus": ["#o1.2", "#o1.3"],
                        },
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        selection = packet["jobs"][0]["selection"]
        self.assertEqual(selection["focus"], ["o1.2", "o1.3"])

    def test_render_job_normalizes_hide_selector_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "assembly.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "assembly.step", entry_kind="assembly")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: _selector_artifact(
                    "o1",
                    "o1.2",
                    "o1.2.1",
                    "o1.3",
                )
                packet = resolve_render_job_packet(
                    {
                        "input": "models/assembly.step",
                        "selection": {"hide": ["#o1.2.1"]},
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        selection = packet["jobs"][0]["selection"]
        self.assertEqual(selection["hide"], ["o1.2.1"])

    def test_render_job_rejects_face_focus_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "assembly.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            (models / ".assembly.step.glb").write_bytes(b"glb")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: _selector_artifact("o1", "o1.2")
                with self.assertRaisesRegex(SnapshotError, "part/subassembly occurrence refs"):
                    resolve_render_job_packet(
                        {
                            "input": "models/assembly.step",
                            "selection": {"focus": ["#o1.2.f1"]},
                            "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                        },
                        cwd=root,
                    )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

    def test_render_job_rejects_mixed_focus_and_hide_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "assembly.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            (models / ".assembly.step.glb").write_bytes(b"glb")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: _selector_artifact(
                    "o1",
                    "o1.2",
                    "o1.3",
                )
                with self.assertRaisesRegex(SnapshotError, "selection.focus/refs and selection.hide cannot be used"):
                    resolve_render_job_packet(
                        {
                            "input": "models/assembly.step",
                            "selection": {
                                "focus": ["#o1.2"],
                                "hide": ["#o1.3"],
                            },
                            "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                        },
                        cwd=root,
                    )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

    def test_snapshot_root_flags_and_job_fields_are_removed(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "Unknown argument: --workspace-root"):
            parse_snapshot_args(["--workspace-root", "/tmp"])
        with self.assertRaisesRegex(SnapshotError, "Unknown argument: --root-dir"):
            parse_snapshot_args(["--root-dir", "models"])
        with self.assertRaisesRegex(SnapshotError, "no longer accept workspaceRoot or rootDir"):
            resolve_render_job_packet(
                {
                    "input": "part.step",
                    "workspaceRoot": "/tmp",
                    "outputs": [{"path": "tmp/iso.png"}],
                },
                cwd=Path.cwd(),
            )

    def test_timestamp_output_path_preserves_extension(self) -> None:
        self.assertEqual(
            timestamp_output_path("snapshots/review.png", "20260527T163012Z"),
            "snapshots/review_20260527T163012Z.png",
        )

    def test_removed_daemon_flags_stay_removed(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "daemon commands have been removed"):
            parse_snapshot_args(["daemon"])
        with self.assertRaisesRegex(SnapshotError, "--socket has been removed"):
            parse_snapshot_args(["--socket", "snapshot.sock"])

    def test_runtime_routes_are_self_contained(self) -> None:
        self.assertEqual(
            resolve_snapshot_route_file(
                "http://snapshot.local/render.html", runtime_dir=RUNTIME_DIR
            ),
            RENDER_HTML_PATH,
        )
        self.assertEqual(
            resolve_snapshot_route_file(
                "http://snapshot.local/snapshot-render.js", runtime_dir=RUNTIME_DIR
            ),
            RUNTIME_DIR / "snapshot-render.js",
        )

    def test_snapshot_renderer_does_not_force_chromium_single_process(self) -> None:
        captured_launch_options = {}

        class FakePage:
            async def route(self, *args, **kwargs):
                pass

            async def goto(self, *args, **kwargs):
                pass

            async def wait_for_function(self, *args, **kwargs):
                pass

        class FakeContext:
            async def new_page(self):
                return FakePage()

            async def close(self):
                pass

        class FakeBrowser:
            async def new_context(self, *args, **kwargs):
                return FakeContext()

            async def close(self):
                pass

        class FakeChromium:
            async def launch(self, **kwargs):
                captured_launch_options.update(kwargs)
                return FakeBrowser()

        class FakePlaywright:
            def __init__(self) -> None:
                self.chromium = FakeChromium()

            async def stop(self):
                pass

        fake_playwright = FakePlaywright()

        class FakeAsyncPlaywright:
            async def start(self):
                return fake_playwright

        async_api_module = ModuleType("playwright.async_api")
        async_api_module.async_playwright = FakeAsyncPlaywright
        playwright_module = ModuleType("playwright")
        playwright_module.__path__ = []

        original_playwright = sys.modules.get("playwright")
        original_async_api = sys.modules.get("playwright.async_api")
        try:
            sys.modules["playwright"] = playwright_module
            sys.modules["playwright.async_api"] = async_api_module

            async def start_renderer() -> None:
                renderer = snapshot_main.BatchSnapshotRenderer(RUNTIME_DIR)
                try:
                    await renderer.start()
                finally:
                    await renderer.close()

            asyncio.run(start_renderer())
        finally:
            if original_playwright is None:
                sys.modules.pop("playwright", None)
            else:
                sys.modules["playwright"] = original_playwright
            if original_async_api is None:
                sys.modules.pop("playwright.async_api", None)
            else:
                sys.modules["playwright.async_api"] = original_async_api

        self.assertNotIn("--single-process", captured_launch_options.get("args") or [])

    def test_snapshot_tool_has_no_sideways_runtime_dependencies(self) -> None:
        snapshot_root = repo_path("skills/cad/scripts/snapshot")
        checked_files = [
            snapshot_root / "__main__.py",
            snapshot_root / "runtime" / "render.html",
            snapshot_root / "runtime" / "snapshot-render.js",
        ]
        forbidden = (
            "packages/cadjs",
            "skills/cad-viewer",
            "/node_modules/",
            "\\node_modules\\",
            "CADJS_NODE_MODULES_ROOT",
        )
        for checked_file in checked_files:
            text = checked_file.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{checked_file} should not reference {token}")


if __name__ == "__main__":
    unittest.main()


class JobThemeResolutionTests(unittest.TestCase):
    """A job's own `theme` string must get the same treatment as the
    `--theme` flag. It used to fall through to a saved-theme-id lookup,
    miss, and silently render on the default workbench theme with diagnostic
    dimensions — exit 0, no warning, a plausible but wrong image."""

    def _packet_for(self, theme_value, *, theme_body=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models = root / "models"
            models.mkdir(parents=True)
            (models / "part.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "part.step")
            if theme_body is not None:
                (models / "stage.theme.json").write_text(
                    json.dumps(theme_body), encoding="utf-8"
                )
            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *a, **k: None
                return resolve_render_job_packet(
                    {
                        "input": "models/part.step",
                        "theme": theme_value,
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

    def test_job_theme_file_path_is_loaded_into_settings(self):
        theme = {
            "_comment": "why these numbers are what they are",
            "colorMode": "dark",
            "projection": "perspective",
            "materials": {"roughness": 0.56},
        }
        packet = self._packet_for("models/stage.theme.json", theme_body=theme)
        theme = packet["jobs"][0]["theme"]
        self.assertIsInstance(
            theme, dict, "a theme FILE PATH must resolve to settings, not stay a string"
        )
        self.assertEqual(theme["materials"]["roughness"], 0.56)
        # keys the renderer genuinely consumes must survive validation
        self.assertEqual(theme["projection"], "perspective")
        self.assertEqual(theme["colorMode"], "dark")
        # underscore-prefixed keys are comments, dropped rather than rejected
        self.assertNotIn("_comment", theme)

    def test_job_theme_rejects_edges_and_names_its_real_home(self):
        """Edge settings belong in display JSON. Rejecting them is correct; the
        message must say where they go rather than just 'unsupported keys'."""
        with self.assertRaises(snapshot_main.SnapshotError) as ctx:
            self._packet_for(
                "models/stage.theme.json",
                theme_body={"materials": {"roughness": 0.5}, "edges": {"enabled": False}},
            )
        message = str(ctx.exception)
        self.assertIn("unsupported keys: edges", message)
        self.assertIn("edges belongs in display JSON", message)

    def test_job_theme_saved_theme_name_stays_a_name(self):
        packet = self._packet_for("workbench")
        self.assertEqual(packet["jobs"][0]["theme"], "workbench")

    def test_job_theme_missing_file_raises(self):
        with self.assertRaises(snapshot_main.SnapshotError) as ctx:
            self._packet_for("models/no_such_theme.json")
        self.assertIn("does not exist", str(ctx.exception))


class JobOutputResolutionTests(unittest.TestCase):
    """`outputs` element types were never validated. A bare string was coerced
    to {} and the caller's path discarded, so the render ran to completion and
    then wrote nothing, printed nothing, and exited 0."""

    def _packet_for(self, outputs):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models = root / "models"
            models.mkdir(parents=True)
            (models / "part.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "part.step")
            original_ensure = snapshot_main.ensure_step_topology_artifact
            original_timestamp = snapshot_main.snapshot_timestamp
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *a, **k: None
                snapshot_main.snapshot_timestamp = lambda: "20260527T163012Z"
                packet = resolve_render_job_packet(
                    {"input": "models/part.step", "outputs": outputs},
                    cwd=root,
                )
                return packet, root
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure
                snapshot_main.snapshot_timestamp = original_timestamp

    def test_render_job_output_path_string_is_accepted(self):
        packet, root = self._packet_for(["tmp/iso.png"])
        resolved = Path(packet["jobs"][0]["outputs"][0]["path"]).resolve()
        self.assertEqual(
            resolved.relative_to(root.resolve()).as_posix(),
            "tmp/iso_20260527T163012Z.png",
        )

    def test_render_job_output_without_path_is_rejected(self):
        with self.assertRaises(SnapshotError) as ctx:
            self._packet_for([{"camera": "iso"}])
        self.assertIn("has no path", str(ctx.exception))


class JobDisplayResolutionTests(unittest.TestCase):
    """A job's own `display` string must get the same treatment as the
    `--display` flag. It used to be discarded in favour of {"mode": "solid"},
    so a mode name, a file path, and an outright typo all rendered the default."""

    def _packet_for(self, display_value, *, display_body=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models = root / "models"
            models.mkdir(parents=True)
            (models / "part.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "part.step")
            if display_body is not None:
                (models / "stage.display.json").write_text(
                    json.dumps(display_body), encoding="utf-8"
                )
            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *a, **k: None
                return resolve_render_job_packet(
                    {
                        "input": "models/part.step",
                        "display": display_value,
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

    def test_job_display_mode_string_is_resolved(self):
        packet = self._packet_for("wireframe")
        self.assertEqual(packet["jobs"][0]["display"]["mode"], "wireframe")

    def test_job_display_file_path_is_loaded_into_settings(self):
        body = {"mode": "wireframe", "edges": {"enabled": False}}
        packet = self._packet_for("models/stage.display.json", display_body=body)
        display = packet["jobs"][0]["display"]
        self.assertEqual(display["mode"], "wireframe")
        self.assertEqual(display["edges"]["enabled"], False)

    def test_job_display_invalid_mode_raises(self):
        with self.assertRaises(SnapshotError):
            self._packet_for("totally_not_a_mode")

    def test_job_display_object_is_unchanged(self):
        packet = self._packet_for({"mode": "wireframe"})
        self.assertEqual(packet["jobs"][0]["display"]["mode"], "wireframe")


class StepParameterSidecarTests(unittest.TestCase):
    """Where a STEP parameter sidecar may come from, per entry kind.

    A generated model declares its sidecar from ``gen_step()``, so the render
    package descriptor names it and the command line may not. An imported
    ``.step``/``.stp`` declares nothing, so the sidecar has to be named with
    ``--params-path`` -- and stepParameters without one is an error rather than
    a render that silently ignores them."""

    SIDECAR = "export default { manifest: {}, update() {} };\n"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.models = self.root / "models"
        self.models.mkdir()
        (self.root / "tmp").mkdir()

    def _imported_step(self, name="part.step", *, sidecar=True):
        step_path = self.models / name
        step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        write_package(step_path)
        if sidecar:
            (self.models / f"{name}.js").write_text(self.SIDECAR, encoding="utf-8")
        return step_path

    def _generated_step(self, name="widget.step.py"):
        generator = self.models / name
        generator.write_text("def gen_step():\n    return None\n", encoding="utf-8")
        write_package(generator, source_kind="python")
        return generator

    def _job(self, **overrides):
        job = {
            "input": f"models/{overrides.pop('name', 'part.step')}",
            "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
        }
        job.update(overrides)
        return job

    def _resolve(self, job):
        # The artifact build is out of scope here: these are input-shape rules.
        original = snapshot_main.ensure_step_topology_artifact
        try:
            snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
            return resolve_render_job_packet(job, cwd=self.root)
        finally:
            snapshot_main.ensure_step_topology_artifact = original

    def test_params_path_flag_reaches_the_job(self) -> None:
        options = parse_snapshot_args(
            [
                "--input", "models/part.step",
                "--output", "tmp/part.png",
                "--params", '{"stroke": 1}',
                "--params-path", "models/part.step.js",
            ]
        )
        job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=self.root)
        self.assertEqual(job["stepParameters"], {"stroke": 1})
        self.assertEqual(job["stepParametersPath"], "models/part.step.js")

    def test_params_path_flag_overrides_a_json_job(self) -> None:
        options = parse_snapshot_args(["--params-path=models/part.step.js"])
        overridden = snapshot_main.apply_option_overrides_to_payload(
            {"input": "models/part.step", "outputs": []}, options, cwd=self.root
        )
        self.assertEqual(overridden["stepParametersPath"], "models/part.step.js")

    def test_imported_step_renders_parameters_from_the_named_sidecar(self) -> None:
        self._imported_step()
        packet = self._resolve(
            self._job(stepParameters={"stroke": 1}, stepParametersPath="models/part.step.js")
        )
        resolved = packet["jobs"][0]["resolved"]
        self.assertEqual(resolved["stepParameterPath"], str(self.models / "part.step.js"))
        self.assertIn("stepParameterUrl", resolved)

    def test_imported_step_rejects_parameters_without_a_named_sidecar(self) -> None:
        self._imported_step()
        with self.assertRaisesRegex(SnapshotError, "require --params-path"):
            self._resolve(self._job(stepParameters={"stroke": 1}))

    def test_generated_model_rejects_a_named_sidecar(self) -> None:
        self._generated_step()
        (self.models / "widget.params.js").write_text(self.SIDECAR, encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "stepParametersPath is for imported"):
            self._resolve(
                self._job(
                    name="widget.step.py",
                    stepParameters={"stroke": 1},
                    stepParametersPath="models/widget.params.js",
                )
            )

    def test_named_sidecar_requires_parameter_values(self) -> None:
        self._imported_step()
        with self.assertRaisesRegex(SnapshotError, "needs stepParameters values"):
            self._resolve(self._job(stepParametersPath="models/part.step.js"))

    def test_named_sidecar_must_exist_and_be_javascript(self) -> None:
        self._imported_step(sidecar=False)
        with self.assertRaisesRegex(SnapshotError, "does not exist"):
            self._resolve(
                self._job(stepParameters={"stroke": 1}, stepParametersPath="models/part.step.js")
            )
        with self.assertRaisesRegex(SnapshotError, "must be a .js or .mjs"):
            self._resolve(
                self._job(stepParameters={"stroke": 1}, stepParametersPath="models/part.step")
            )

    def test_named_sidecar_must_live_beside_the_step_file(self) -> None:
        # The renderer serves assets relative to the model folder, so an outside
        # path has no URL -- reject it here rather than fail mid-render.
        self._imported_step()
        outside = self.root / "elsewhere"
        outside.mkdir()
        (outside / "part.step.js").write_text(self.SIDECAR, encoding="utf-8")
        with self.assertRaisesRegex(SnapshotError, "must sit inside the STEP model folder"):
            self._resolve(
                self._job(stepParameters={"stroke": 1}, stepParametersPath="elsewhere/part.step.js")
            )

    def test_job_paramsPath_key_is_rejected_with_the_right_name(self) -> None:
        self._imported_step()
        with self.assertRaisesRegex(SnapshotError, "render jobs use stepParametersPath"):
            self._resolve(self._job(paramsPath="models/part.step.js"))


if __name__ == "__main__":
    unittest.main()
