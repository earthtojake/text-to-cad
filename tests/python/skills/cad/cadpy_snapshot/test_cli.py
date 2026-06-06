from __future__ import annotations

import asyncio
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("skills/cad/scripts")

import cadpy_snapshot.__main__ as snapshot_main
from cadpy_snapshot.__main__ import (
    RENDER_HTML_PATH,
    RUNTIME_DIR,
    SnapshotError,
    load_job_from_options,
    parse_snapshot_args,
    resolve_render_job_packet,
    resolve_snapshot_route_file,
    timestamp_output_path,
)


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
            "import sys; sys.path.insert(0, 'scripts'); import cadpy_snapshot.__main__; "
            "print('OCP.OCP' in sys.modules); "
            "print('cadpy.step_scene' in sys.modules)"
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
                "models/simple/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--display",
                "wireframe",
                "--size-profile",
                "simple",
            ]
        )

        job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())

        self.assertEqual(job["input"], "models/simple/cylindrical_cap.step")
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
        for raw_mode, expected_mode in [
            ("edges", "solid"),
            ("x-ray", "transparent"),
            ("hidden edges visible", "hidden_edges"),
            ("hidden-lines-removed", "hidden_lines_removed"),
            ("flat", "unshaded"),
            ("appearance", "rendered"),
            ("wire", "wireframe"),
        ]:
            options = parse_snapshot_args(
                [
                    "--input",
                    "models/simple/cylindrical_cap.step",
                    "--output",
                    "tmp/cap.png",
                    "--display",
                    raw_mode,
                ]
            )
            job = load_job_from_options(options, stdin=_TtyStringIO(), cwd=Path.cwd())
            self.assertEqual(job["display"], {"mode": expected_mode})

    def test_display_shortcut_rejects_unknown_modes(self) -> None:
        options = parse_snapshot_args(
            [
                "--input",
                "models/simple/cylindrical_cap.step",
                "--output",
                "tmp/cap.png",
                "--display",
                "mist",
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
            (models / ".part.step.glb").write_bytes(b"glb")

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
            (models / ".part.step.glb").write_bytes(b"glb")

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
        self.assertEqual(job["resolved"]["inputUrl"], "/__render_asset/part.step")
        self.assertEqual(job["resolved"]["glbUrl"], "/__render_asset/.part.step.glb")

    def test_render_job_ensures_step_artifact_for_step_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            step_path = models / "part.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            (models / ".part.step.glb").write_bytes(b"glb")
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
        self.assertEqual(kwargs["owner"], "cad-snapshot")
        self.assertFalse(kwargs["require_selector"])

    def test_render_job_rejects_non_step_input_without_artifact_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "robot.urdf").write_text("<robot name=\"r\" />\n", encoding="utf-8")
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append((target, kwargs))
                return None

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = fake_ensure
                with self.assertRaisesRegex(
                    SnapshotError,
                    "Snapshot supports only STEP/STP inputs or same-stem Python generators",
                ):
                    resolve_render_job_packet(
                        {
                            "input": "models/robot.urdf",
                            "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                        },
                        cwd=root,
                    )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

        self.assertEqual(calls, [])

    def test_render_job_requires_selector_topology_for_cad_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            step_path = models / "assembly.step"
            step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            (models / ".assembly.step.glb").write_bytes(b"glb")
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
            (models / ".assembly.step.glb").write_bytes(b"glb")

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
            (models / ".assembly.step.glb").write_bytes(b"glb")

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
            resolve_snapshot_route_file("http://snapshot.local/render.html"),
            RENDER_HTML_PATH,
        )
        self.assertEqual(
            resolve_snapshot_route_file("http://snapshot.local/snapshot-render.js"),
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
                renderer = snapshot_main.BatchSnapshotRenderer()
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
        snapshot_root = repo_path("skills/cad/scripts/cadpy_snapshot")
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
