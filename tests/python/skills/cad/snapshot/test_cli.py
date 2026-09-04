from __future__ import annotations

import asyncio
import base64
import contextlib
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


def write_package(step_path, *, entry_kind="part", source_kind="step", kinematics=None, animation=None):
    """Materialize the canonical render artifact for ``step_path``: a SELF-CONTAINED
    component-GLB PACKAGE directory inside the per-folder cache
    (``__cadgen__/models/<step-filename>/assembly.json``) whose content-addressed component
    GLBs live in the tree's own ``components/<hash>.glb`` dir. Returns the view directory
    path, mirroring ``cadgen.catalog.result_view_dir``."""
    from cadgen.catalog import result_view_dir

    step_path = Path(step_path)
    if not step_path.is_file():
        step_path.parent.mkdir(parents=True, exist_ok=True)
        step_path.write_text(f"ISO-10303-21;\n{step_path.name}\n")
    pkg_dir = result_view_dir(step_path)
    comp_dir = pkg_dir / "components"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    comp_dir.mkdir(parents=True, exist_ok=True)
    cid = hashlib.sha256(str(step_path).encode()).hexdigest()[:16]
    (comp_dir / f"{cid}.surf").write_bytes(b"component-surf")
    (pkg_dir / "assembly.json").write_text(
        json.dumps(
            {
                "kind": "assembly-package",
                "entryKind": entry_kind,
                "rootName": step_path.stem,
                "units": "mm",
                "sourceKind": source_kind,
                "stepPath": step_path.name,
                "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]},
                "stats": {"occurrenceCount": 1, "shapeCount": 1},
                "components": {cid: {"surf": f"components/{cid}.surf", "contentHash": cid}},
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
    if kinematics or animation:
        # Kinematics/animation (source-derived) ride the MODEL-SIDE sidecar,
        # never assembly.json.
        from cadgen._internal.source_sidecar import SOURCE_SIDECAR_SCHEMA_VERSION

        sidecar = {"schemaVersion": SOURCE_SIDECAR_SCHEMA_VERSION}
        if kinematics:
            sidecar["kinematics"] = kinematics
        if animation:
            sidecar["animation"] = animation
        Path(f"{step_path}.json").write_text(
            json.dumps(sidecar)
        )
    return pkg_dir

add_repo_path("packages/cadgen/src")

# Job resolution and the run loop are shared (cadgen.snapshot_cli);
# `cadgen step snapshot` (cadgen.cli.step_snapshot) is the CAD entrypoint, a
# GENERATED CLI over cadgen.step.snapshot. The skill shims are gone; these tests
# drive the shared implementation through that cadgen verb directly.
import cadgen.snapshot_cli as snapshot_main
import cadgen.cli.step_snapshot as cad_snapshot_entry
from cadgen.assets import browser_runtime_dir
from cadgen._internal.snapshot_door import DOOR_KINDS
from cadgen.snapshot_cli import (
    SnapshotError,
    load_job_from_options,
    resolve_render_job_packet,
    resolve_snapshot_route_file,
)
from cadgen.snapshot_core import (
    clear_render_output_targets,
    resolve_output_target,
    snapshot_result,
)
from cadgen._internal.cli_from_function import emit, result_payload

# The shim no longer names a runtime directory: cadgen.assets resolves it, finding the
# repo's live source here and the packaged copy in an installed wheel.
RUNTIME_DIR = browser_runtime_dir()
RENDER_HTML_PATH = RUNTIME_DIR / "render.html"
STEP_KINDS = DOOR_KINDS["step"]
CAD_KINDS = snapshot_main.enabled_kinds(STEP_KINDS)


def options_from_argv(argv, entry=None):
    """The SnapshotOptions `cadgen step snapshot ARGV` hands the run loop.

    Snapshot's parser is GENERATED from `cadgen.step.snapshot`'s signature, so
    there is no argv-to-options function to call: the options object exists only
    for as long as it takes the verb to pass it on. Driving the real command
    module and intercepting that hand-off is what keeps these tests pointed at
    the grammar that ships rather than at a parser rebuilt in the test file.
    """
    module = entry or cad_snapshot_entry
    captured = {}

    def capture(options, **kwargs):
        captured["options"] = options
        captured["kinds"] = kwargs.get("kinds")
        return snapshot_result({"ok": True, "mode": "view", "outputs": []}, total_ms=0.0)

    with mock.patch.object(snapshot_main, "run_snapshot", capture):
        code = module.main(list(argv))
    if "options" not in captured:
        raise AssertionError(
            f"`{module.DEFAULT_PROG} {' '.join(argv)}` exited {code} before the run started"
        )
    return captured["options"]


def job_from_argv(argv, entry=None):
    """One documented invocation, all the way to the render job it becomes."""
    return load_job_from_options(
        options_from_argv(argv, entry), stdin=_TtyStringIO(), cwd=Path.cwd()
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
        code = (
            "import cadgen.cli.step_snapshot; "
            "print('OCP.OCP' in sys.modules); "
            "print('cadgen._internal.step_scene' in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", "import sys; " + code],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertEqual(["False", "False"], result.stdout.strip().splitlines())

    def test_shortcut_job_shape_stays_owned_by_python_cli(self) -> None:
        job = job_from_argv(
            [
                "models/examples/STEP/cylindrical_cap.step",
                "tmp/cap.png",
                "--display",
                "wireframe",
                "--size-profile",
                "simple",
            ]
        )

        # TARGET and OUT are both Path parameters on the generated parser, so
        # they reach the job in the NATIVE spelling; build the expectations the
        # same way rather than hardcoding the POSIX separator.
        self.assertEqual(job["input"], str(Path("models/examples/STEP/cylindrical_cap.step")))
        self.assertNotIn("workspaceRoot", job)
        self.assertNotIn("rootDir", job)
        self.assertEqual(job["outputs"][0]["path"], str(Path("tmp/cap.png")))
        self.assertEqual(job["display"], {"mode": "wireframe"})
        self.assertEqual(job["render"]["sizeProfile"], "simple")

    def test_the_target_and_output_are_positional(self) -> None:
        """One grammar across the schema: `snapshot TARGET [OUT]` reads the same
        way `build TARGET [OUT]` does, and there is nothing to spell twice."""
        options = options_from_argv(["models/part.step", "tmp/part.png"])
        self.assertEqual(str(Path("models/part.step")), options.input)
        self.assertEqual(str(Path("tmp/part.png")), options.output)

    #: Flags the door does not have. The parser is GENERATED from the verb's
    #: signature, so what it accepts is exactly what the verb takes — anything
    #: else is argparse's own "unrecognized arguments", with no pre-parse scan
    #: recognizing particular spellings.
    NON_FLAGS = ("--input", "-i", "--output", "--params", "--params-path")

    def test_a_flag_the_door_does_not_have_is_an_ordinary_parse_error(self) -> None:
        for argv in (
            ["--input", "models/part.step"],
            ["-i", "models/part.step"],
            ["--output", "tmp/o.png"],
            ["--params", '{"jaw": 40}'],
            ["--params=x", "models/part.step"],
            ["--params-path", "models/part.step.js"],
        ):
            with self.subTest(argv=" ".join(argv)):
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as caught:
                    cad_snapshot_entry.main(argv)
                self.assertEqual(2, caught.exception.code)
                message = errors.getvalue()
                self.assertIn("unrecognized arguments", message)
                self.assertNotIn("renamed", message)
                self.assertNotIn("retired", message)

    def test_the_door_advertises_only_what_it_takes(self) -> None:
        text = cad_snapshot_entry.build_parser().format_help()
        for flag in self.NON_FLAGS:
            if flag.startswith("--"):
                with self.subTest(flag=flag):
                    self.assertNotIn(flag, text)

    def test_focus_and_hide_cannot_be_used_together(self) -> None:
        from cadgen import step

        with self.assertRaisesRegex(ValueError, "focus and hide cannot be used"):
            step.snapshot(
                Path("models/assembly.step"),
                Path("tmp/assembly.png"),
                focus=("#o1.2",),
                hide=("#o1.3.1",),
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
            job = job_from_argv(
                [
                    "models/examples/STEP/cylindrical_cap.step",
                    "tmp/cap.png",
                    "--display",
                    raw_mode,
                ]
            )
            self.assertEqual(job["display"], expected_display)

    def test_display_json_accepts_exploded_settings(self) -> None:
        job = job_from_argv(
            [
                "models/examples/STEP/cylindrical_cap.step",
                "tmp/cap.png",
                "--display",
                '{"projection":"perspective","mode":"rendered","exploded":{"enabled":true,"amount":0.7}}',
            ]
        )
        self.assertEqual(
            job["display"],
            {
                "projection": "perspective",
                "mode": "rendered",
                "exploded": {"enabled": True, "amount": 0.7},
            },
        )

    def _display_job(self, display_json: str):
        return job_from_argv(
            [
                "models/examples/STEP/cylindrical_cap.step",
                "tmp/cap.png",
                "--display",
                display_json,
            ]
        )

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
        job = job_from_argv(
            [
                "models/examples/STEP/cylindrical_cap.step",
                "tmp/cap.png",
                "--display",
                '{"edges":{"enabled":false,"color":"#123456"}}',
            ]
        )
        self.assertEqual(job["display"], {"edges": {"enabled": False, "color": "#123456"}})

        with self.assertRaisesRegex(SnapshotError, "unsupported keys: edges"):
            job_from_argv(
                [
                    "models/examples/STEP/cylindrical_cap.step",
                    "tmp/cap.png",
                    "--theme",
                    '{"edges":{"enabled":false}}',
                ]
            )

    def test_theme_accepts_a_full_theme_preset_clone(self) -> None:
        # cloneThemePresetSettings() emits colorMode, projection and modeColors
        # alongside the five settings blocks. Rejecting any of them meant the
        # repo's own theme-clone output could not be passed back to
        # --theme without hand-stripping keys first.
        job = job_from_argv(
            [
                "models/examples/STEP/cylindrical_cap.step",
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
        self.assertIn("modeColors", job["theme"])

    def test_display_shortcut_rejects_unknown_modes(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "Unsupported display mode"):
            job_from_argv(
                [
                    "models/examples/STEP/cylindrical_cap.step",
                    "tmp/cap.png",
                    "--display",
                    "mist",
                ]
            )

    def test_display_shortcut_rejects_exploded_mode_alias(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "Unsupported display mode"):
            job_from_argv(
                [
                    "models/examples/STEP/cylindrical_cap.step",
                    "tmp/cap.png",
                    "--display",
                    "exploded",
                ]
            )

    def test_shortcut_focus_flags_apply_selection(self) -> None:
        # Repeatable rather than variadic: one ref per flag, so a ref can never
        # be swallowed by the positional TARGET standing next to it.
        job = job_from_argv(
            [
                "models/assembly.step",
                "tmp/assembly.png",
                "--focus",
                "#o1.2",
                "--focus",
                "#o1.3",
            ]
        )

        self.assertEqual(
            job["selection"],
            {
                "focus": ["#o1.2", "#o1.3"],
            },
        )

    def test_declared_output_paths_are_used_exactly(self) -> None:
        """Every explicit output path is the path that gets written -- per output,
        across jobs, in every mode. This used to append a shared UTC timestamp
        before each extension (`iso.png` -> `iso_20260527T163012Z.png`), so the
        command's output never matched its declaration and callers had to parse
        the "saved snapshot:" line to learn where their own file went."""
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
                                "mode": "section",
                                "outputs": [{"path": "tmp/section.png"}],
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

        self.assertEqual(output_paths, ["tmp/iso.png", "tmp/front.png", "tmp/section.png"])

    def test_a_directory_output_gets_a_generated_name_inside_it(self) -> None:
        """The don't-care case: `--output tmp/` names no file, so one is generated
        -- timestamped, inside that directory, always ``.png`` (snapshot is
        PNG-only). A trailing separator counts before the directory exists; an
        existing directory counts without one."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "part.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "part.step")
            (root / "shots").mkdir()

            original_timestamp = snapshot_main.snapshot_timestamp
            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.snapshot_timestamp = lambda: "20260527T163012Z"
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
                packet = resolve_render_job_packet(
                    {
                        "jobs": [
                            # A trailing slash, on a directory that does not exist yet.
                            {"input": "models/part.step", "outputs": [{"path": "tmp/"}]},
                            # No trailing slash, but the directory is already there.
                            {"input": "models/part.step", "outputs": [{"path": "shots"}]},
                            # Several outputs into one directory stay distinct.
                            {
                                "input": "models/part.step",
                                "outputs": [{"path": "tmp/", "camera": "iso"}, {"path": "tmp/", "camera": "top"}],
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

        # Every name in a packet shares one timestamp, so the discriminator is all
        # that keeps them apart: `j<n>` for the job, then the output index within it.
        self.assertEqual(
            output_paths,
            [
                "tmp/part_j1_20260527T163012Z.png",
                "shots/part_j2_20260527T163012Z.png",
                "tmp/part_j3_1_20260527T163012Z.png",
                "tmp/part_j3_2_20260527T163012Z.png",
            ],
        )

    def test_a_lone_job_and_output_gets_an_undecorated_generated_name(self) -> None:
        """The common case reads cleanly: one job, one output, nothing to
        discriminate against, so no discriminator appears."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            (root / "models").mkdir()
            (root / "models" / "part.step").write_text(
                "ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8"
            )
            write_package(root / "models" / "part.step")
            original_timestamp = snapshot_main.snapshot_timestamp
            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.snapshot_timestamp = lambda: "20260527T163012Z"
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
                packet = resolve_render_job_packet(
                    {"input": "models/part.step", "outputs": [{"path": "tmp/"}]}, cwd=root
                )
            finally:
                snapshot_main.snapshot_timestamp = original_timestamp
                snapshot_main.ensure_step_topology_artifact = original_ensure
            self.assertEqual(
                Path(packet["jobs"][0]["outputs"][0]["path"]).name,
                "part_20260527T163012Z.png",
            )

    def test_one_directory_shared_by_several_jobs_gets_distinct_names(self) -> None:
        """The collision the job discriminator exists for.

        A packet rendering ONE model from several cameras is the ordinary
        multi-view request, and every job in it carries a single output. With
        only the output index to discriminate, no job had an index — so all of
        them generated the identical `<stem>_<ts>.png`, every render finished,
        and one file survived."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            (root / "models").mkdir()
            (root / "models" / "part.step").write_text(
                "ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8"
            )
            write_package(root / "models" / "part.step")
            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
                packet = resolve_render_job_packet(
                    {
                        "jobs": [
                            {
                                "input": "models/part.step",
                                "camera": camera,
                                "outputs": [{"path": "shots/"}],
                            }
                            for camera in ("iso", "front", "top")
                        ]
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure
            names = [Path(job["outputs"][0]["path"]).name for job in packet["jobs"]]
            self.assertEqual(len(set(names)), 3, names)

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
        # The render artifact is a SELF-CONTAINED tree, so the resolved job
        # carries an assembly.json with per-component asset URLs (no monolithic glbUrl).
        # Each component URL points into the tree's own components/ dir inside __cadgen__.
        self.assertNotIn("glbUrl", job["resolved"])
        package = job["resolved"]["package"]
        self.assertEqual(package["descriptor"]["kind"], "assembly-package")
        component_urls = package["componentUrls"]
        self.assertTrue(component_urls)
        for component_url in component_urls.values():
            parsed_component_url = urlparse(component_url)
            self.assertTrue(
                parsed_component_url.path.startswith(
                    "/__store_asset/"
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
        job = job_from_argv(
            [
                "models/examples/STEP/cylindrical_cap.step",
                "tmp/cap.png",
                "--debug",
            ]
        )
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

    def test_the_typed_result_cannot_carry_output_payload_blobs(self) -> None:
        """--json must not echo the rendered bytes back. dataUrl/text are how the browser
        returns them for write_output_payload to decode; by report time the file is on disk
        and `path` names it. Echoing them cost 228 KB of stdout for one PNG and 1.7 MB --
        ~445k tokens -- for a large presentation PNG.

        This used to be a filter over the browser dict, which had to KNOW every payload
        key. SnapshotResult has no field one could land in, so a new payload key in the
        browser cannot reach stdout by default."""
        data_url = "data:image/png;base64," + "A" * 4096
        svg_text = "<svg>" + "x" * 4096 + "</svg>"
        result = {
            "ok": True,
            "jobs": [
                {
                    "ok": True,
                    "mode": "view",
                    "outputs": [
                        {
                            "path": "/tmp/a.png",
                            "width": 800,
                            "height": 600,
                            "camera": "ISO",
                            "mimeType": "image/png",
                            "dataUrl": data_url,
                        },
                        {"path": "/tmp/b.svg", "mimeType": "image/svg+xml", "text": svg_text},
                    ],
                }
            ],
        }
        typed = snapshot_result(result)
        printed = json.dumps(result_payload(typed), separators=(",", ":"))
        self.assertNotIn("dataUrl", printed)
        self.assertNotIn(data_url, printed)
        self.assertNotIn(svg_text, printed)
        # Everything a caller actually uses survives.
        self.assertEqual(
            [str(f.path) for f in typed.files],
            [str(Path("/tmp/a.png")), str(Path("/tmp/b.svg"))],
        )
        self.assertEqual([f.kind for f in typed.files], ["png", "svg"])
        self.assertEqual(typed.files[0].view, "ISO")
        # The caller's dict keeps its payload: write_output_payload reads the same object.
        self.assertEqual(result["jobs"][0]["outputs"][0]["dataUrl"], data_url)

    def test_debug_reaches_rendered_json_output(self) -> None:
        """--debug diagnostics are attached at resolve time, but the rendered result is the
        browser's return value — the render stage must merge them in or the help text's
        promised "debug" section never appears in --json output. The typed result keeps
        one entry per job, tagged with the input it describes."""

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
        typed = snapshot_result(result)
        self.assertEqual(
            result_payload(typed)["debug"], [{**debug_payload}]
        )

        multi = asyncio.run(
            snapshot_main.render_resolved_job_packet(
                {"single": False, "jobs": [job]}, runtime_dir=RUNTIME_DIR, renderer=StubRenderer()
            )
        )
        self.assertEqual(multi["jobs"][0]["debug"], debug_payload)
        self.assertEqual(
            snapshot_result(multi).debug,
            ({"input": "models/part.step", **debug_payload},),
        )

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

    def test_render_job_rejects_top_level_selection_shaped_keys(self) -> None:
        # "hide"/"focus" belong inside the selection object; at top level they
        # are unknown keys and fail through the ordinary closed-schema error.
        with self.assertRaisesRegex(SnapshotError, r"unknown render job key\(s\): hide"):
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
            with self.assertRaisesRegex(SnapshotError, "unknown key\\(s\\): kinematics"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "outputs": [
                            {
                                "path": "tmp/iso.png",
                                "camera": "iso",
                                "kinematics": {"width": 5},
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

    def test_render_job_rejects_kinematics_for_mesh_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "kinematics values require a STEP model"):
                resolve_render_job_packet(
                    {
                        "input": "models/widget.glb",
                        "kinematics": {"width": 5},
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )

    def test_render_job_rejects_a_key_outside_the_closed_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "unknown render job key"):
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

    def test_input_kind_leaves_plain_javascript_unsupported(self) -> None:
        self.assertEqual(snapshot_main.input_kind(Path("models/helper.js")), "")

    def test_render_job_resolves_a_mesh_without_a_step_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            calls = []

            def fake_ensure(target, **kwargs):
                calls.append(kwargs)
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

        # Mesh inputs skip the STEP artifact pipeline entirely.
        self.assertEqual(calls, [])
        job = packet["jobs"][0]
        resolved = job["resolved"]
        self.assertEqual(resolved["kind"], "glb")
        self.assertTrue(urlparse(str(resolved["inputUrl"])).path.endswith("widget.glb"))

    def test_render_job_rejects_orbit_mode(self) -> None:
        # GIF export is deleted, and orbit mode went with it: the mode is not in
        # any kind's supported set any more.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "Unsupported render mode: orbit"):
                resolve_render_job_packet(
                    {"input": "models/widget.glb", "mode": "orbit", "outputs": [{"path": "tmp/spin.png"}]},
                    cwd=root,
                )

    def test_render_job_rejects_gif_outputs(self) -> None:
        # Snapshot is PNG-only; a .gif output fails loudly instead of saving a
        # still under an animation-suggesting name.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = self._mesh_job_env(temporary_directory, "widget.glb", b"glTF")
            with self.assertRaisesRegex(SnapshotError, "snapshot renders PNG stills"):
                resolve_render_job_packet(
                    {"input": "models/widget.glb", "outputs": [{"path": "tmp/spin.gif", "camera": "iso"}]},
                    cwd=root,
                )

    def test_render_job_rejects_a_kinematics_key_the_model_does_not_declare(self) -> None:
        # Pose values name DECLARED DOFs. Anything else is an unknown parameter
        # — no key is special-cased, so nothing renders silently static.
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "part.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "part.step", kinematics={
                "mates": [{"name": "width", "kind": "slider", "parent": "#a", "child": "#b",
                           "axis": {"origin": [0, 0, 0], "dir": [1, 0, 0]},
                           "limits": {"value": [0, 5]}}],
            })

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
                with self.assertRaisesRegex(SnapshotError, "[Uu]nknown"):
                    resolve_render_job_packet(
                        {
                            "input": "models/part.step",
                            "kinematics": {"animate": {"width": {"from": 1, "to": 2}}},
                            "outputs": [{"path": "tmp/sweep.png"}],
                        },
                        cwd=root,
                    )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure

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
                resolve_render_job_packet({**base, "kinematics": {"width": 5}}, cwd=root)
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

    def _group_selection(self, selection: dict) -> dict:
        """Resolve `selection` against a LEAF-ONLY occurrence index.

        That is what a real assembly package produces: only the instance tree's leaves own
        geometry, so only leaves become selector-index rows (cadgen.assembly_lookup). The
        subassembly nodes `o1` and `o1.4` are carried by the ids alone.
        """
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            models = root / "models"
            models.mkdir()
            (models / "assembly.step").write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
            write_package(models / "assembly.step", entry_kind="assembly")

            original_ensure = snapshot_main.ensure_step_topology_artifact
            try:
                snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: _selector_artifact(
                    "o1.1.1",
                    "o1.1.2",
                    "o1.4.1",
                    "o1.4.2",
                    "o1.4.10",
                )
                packet = resolve_render_job_packet(
                    {
                        "input": "models/assembly.step",
                        "selection": selection,
                        "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
                    },
                    cwd=root,
                )
            finally:
                snapshot_main.ensure_step_topology_artifact = original_ensure
        return packet["jobs"][0]["selection"]

    def test_focus_expands_a_group_ref_to_its_subtree(self) -> None:
        """A subassembly ref covers every rendered part under it.

        `#o1.4` names an instance-tree NODE, which kinematics mates address and pose
        without complaint; it carried no selector-index row of its own and so was refused
        as "unknown", by an error that claimed to support subassemblies. Ordered by
        numeric path, so o1.4.10 follows o1.4.2 rather than o1.4.1.
        """
        selection = self._group_selection({"focus": ["#o1.4"]})
        self.assertEqual(selection["focus"], ["o1.4.1", "o1.4.2", "o1.4.10"])

    def test_hide_expands_a_group_ref_the_same_way(self) -> None:
        selection = self._group_selection({"hide": ["#o1.4"]})
        self.assertEqual(selection["hide"], ["o1.4.1", "o1.4.2", "o1.4.10"])

    def test_the_root_group_covers_the_whole_model(self) -> None:
        selection = self._group_selection({"focus": ["#o1"]})
        self.assertEqual(
            selection["focus"], ["o1.1.1", "o1.1.2", "o1.4.1", "o1.4.2", "o1.4.10"]
        )

    def test_a_group_and_one_of_its_parts_do_not_duplicate(self) -> None:
        selection = self._group_selection({"focus": ["#o1.4", "#o1.4.2"]})
        self.assertEqual(selection["focus"], ["o1.4.1", "o1.4.2", "o1.4.10"])

    def test_an_unknown_group_ref_names_what_does_exist(self) -> None:
        """Expansion must not turn every typo into a silent no-op: a ref with nothing
        under it still fails, and the error walks up to the deepest node that IS there."""
        with self.assertRaisesRegex(SnapshotError, r"o1\.9.*o1 does exist, and holds: o1\.1, o1\.4"):
            self._group_selection({"focus": ["#o1.9"]})
        with self.assertRaisesRegex(SnapshotError, r"o1\.4\.99.*o1\.4 does exist, and holds: "):
            self._group_selection({"focus": ["#o1.4.99"]})

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
        for flag, value in (("--workspace-root", "/tmp"), ("--root-dir", "models")):
            with self.subTest(flag=flag):
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
                    cad_snapshot_entry.build_parser().parse_args([flag, value])
                self.assertIn("unrecognized arguments", errors.getvalue())
        with self.assertRaisesRegex(SnapshotError, r"unknown render job key\(s\): workspaceRoot"):
            resolve_render_job_packet(
                {
                    "input": "part.step",
                    "workspaceRoot": "/tmp",
                    "outputs": [{"path": "tmp/iso.png"}],
                },
                cwd=Path.cwd(),
            )

    def test_output_target_resolution_is_native_and_cwd_relative(self) -> None:
        # The helper returns a NATIVE absolute path, so the expectation is built the
        # same way rather than hard-coding `/` -- which failed on Windows against the
        # `\` it actually returns (issue #196). A relative path resolves against the
        # invoking process's working directory, never the model's folder.
        cwd = Path.cwd().resolve()
        self.assertEqual(
            resolve_output_target("snapshots/review.png", resolved_cwd=cwd, generated_name="ignored.png"),
            str(cwd / "snapshots" / "review.png"),
        )
        self.assertEqual(
            resolve_output_target("snapshots/", resolved_cwd=cwd, generated_name="part_20260527T163012Z.png"),
            str(cwd / "snapshots" / "part_20260527T163012Z.png"),
        )

    def test_removed_daemon_flags_stay_removed(self) -> None:
        """`--socket` is not a flag any more, and `daemon` is not a subcommand.

        The generated parser has no room for either: `--socket` is unrecognized,
        and a bare `daemon` reads as the TARGET positional and fails as a render
        input that does not exist."""
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit):
            cad_snapshot_entry.build_parser().parse_args(["--socket", "snapshot.sock"])
        self.assertIn("unrecognized arguments", errors.getvalue())

        options = options_from_argv(["daemon", "tmp/o.png"])
        self.assertEqual("daemon", options.input)

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
        """The shipped runtime must not reach outside itself.

        It used to be vendored beside the skill; it now ships inside cadgen, but the
        invariant is the same and matters more: a reference to a repo path or a
        node_modules tree resolves on a developer's machine and nowhere else, so it
        would pass every check here and fail for anyone who installed the wheel.
        """
        checked_files = [
            RUNTIME_DIR / "render.html",
            RUNTIME_DIR / "snapshot-render.js",
        ]
        forbidden = (
            "packages/cadgen-js",
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
        self.assertEqual(resolved.relative_to(root.resolve()).as_posix(), "tmp/iso.png")

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


class StepPoseParameterTests(unittest.TestCase):
    """The job's `kinematics` key drives the model's declarative kinematics
    block — the ONE parameter transport, spelled the same as the flag and the
    sidecar section. The retired spellings (`stepParameters`, --params-path,
    stepParametersPath, descriptor paramsPath) are hard teaching errors."""

    POSE = {
        "mates": [{"name": "stroke", "kind": "slider", "parent": "#body", "child": "#ram",
                   "axis": {"origin": [0, 0, 0], "dir": [0, 0, 1]},
                   "limits": {"value": [0, 1]}}],
    }

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.models = self.root / "models"
        self.models.mkdir()
        (self.root / "tmp").mkdir()

    def _step(self, name="part.step", *, pose=True):
        step_path = self.models / name
        step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        write_package(step_path, kinematics=self.POSE if pose else None)
        return step_path

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

    def test_pose_values_and_pose_names_both_reach_the_job(self) -> None:
        """`--kinematics` takes either spelling, told apart by SHAPE.

        A name cannot be resolved here — the declared names live in the model's
        kinematics block, which only the renderer has loaded — so it travels
        through as a string and the job's `kinematics` key carries either form."""
        values = job_from_argv(
            ["models/part.step", "tmp/o.png", "--kinematics", '{"jaw": 40}']
        )
        self.assertEqual({"jaw": 40}, values["kinematics"])

        named = job_from_argv(["models/part.step", "tmp/o.png", "--kinematics", "open"])
        self.assertEqual("open", named["kinematics"])

    def test_pose_parameters_resolve_the_sidecar_url(self) -> None:
        self._step()
        packet = self._resolve(self._job(kinematics={"stroke": 1}))
        resolved = packet["jobs"][0]["resolved"]
        self.assertIn(".step.json", str(resolved["stepParameterUrl"]))
        self.assertNotIn("stepParameterPath", resolved)

    def test_animation_never_gates_the_parameter_url(self) -> None:
        # Choreography is sidecar-borne but INDEPENDENT: an animation section
        # without kinematics gives pose values nothing to drive.
        step_path = self._step(pose=False)
        write_package(step_path, animation={"clips": "export const clips = {};"})
        with self.assertRaisesRegex(SnapshotError, "declares no kinematics"):
            self._resolve(self._job(kinematics={"stroke": 1}))

    def test_parameters_without_kinematics_teach_the_migration(self) -> None:
        self._step(pose=False)
        with self.assertRaisesRegex(SnapshotError, "declares no kinematics"):
            self._resolve(self._job(kinematics={"stroke": 1}))

    def test_a_key_outside_the_closed_schema_is_named_with_the_supported_set(self) -> None:
        """The job schema is closed, and that is the whole answer: a key it does
        not have fails with the keys it does, whatever the key happens to be."""
        self._step()
        for key in ("paramsPath", "stepParametersPath", "stepParameters"):
            with self.subTest(key=key):
                with self.assertRaisesRegex(SnapshotError, "unknown render job key") as caught:
                    self._resolve(self._job(**{key: "models/part.step.js"}))
                message = str(caught.exception)
                self.assertIn("kinematics", message)  # named in the supported set
                self.assertNotIn("renamed", message)
                self.assertNotIn("retired", message)


class StepAnimationFrameTests(unittest.TestCase):
    """The job's `animation` key freezes ONE frame of ONE clip: `{"clip": name,
    "time": seconds}`, spelled the same as the flag (`--animation CLIP --time
    SECONDS`) and the sidecar section it reads. It is layered over `kinematics`
    the way the viewer layers its Animation tab over the Pose tab — the two
    travel independently and meet only in the renderer's effect records."""

    CLIPS = (
        "export const clips = {\n"
        "  demo: { label: 'Demo', duration: 8, update(t, m) { m.get('ram').translate([0, 0, t]); } },\n"
        "  spin: { duration: 2, update(t, m) { m.get('ram').rotate([0, 0, 1], 45 * t); } },\n"
        "};\n"
    )

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.models = self.root / "models"
        self.models.mkdir()
        (self.root / "tmp").mkdir()

    def _step(self, name="part.step", *, clips=CLIPS, kinematics=None):
        step_path = self.models / name
        step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
        write_package(
            step_path,
            kinematics=kinematics,
            animation={"clips": clips} if clips is not None else None,
        )
        return step_path

    def _job(self, **overrides):
        job = {
            "input": f"models/{overrides.pop('name', 'part.step')}",
            "outputs": [{"path": "tmp/iso.png", "camera": "iso"}],
        }
        job.update(overrides)
        return job

    def _resolve(self, job):
        original = snapshot_main.ensure_step_topology_artifact
        try:
            snapshot_main.ensure_step_topology_artifact = lambda *args, **kwargs: None
            return resolve_render_job_packet(job, cwd=self.root)
        finally:
            snapshot_main.ensure_step_topology_artifact = original

    def test_the_flag_pair_becomes_one_job_field(self) -> None:
        """`--animation CLIP --time SECONDS` is ONE request on the job, and the
        time defaults to 0 when only the clip is named."""
        job = job_from_argv(["models/part.step", "tmp/o.png", "--animation", "demo", "--time", "2.5"])
        self.assertEqual({"clip": "demo", "time": 2.5}, job["animation"])

        at_start = job_from_argv(["models/part.step", "tmp/o.png", "--animation", "demo"])
        self.assertEqual({"clip": "demo", "time": 0.0}, at_start["animation"])

    def test_the_flag_pair_overrides_a_job_file_like_kinematics_does(self) -> None:
        job_file = self.root / "job.json"
        job_file.write_text(json.dumps(self._job()), encoding="utf-8")
        options = options_from_argv(
            ["--job", str(job_file), "--animation", "spin", "--time", "1"]
        )
        payload = load_job_from_options(options, stdin=_TtyStringIO(), cwd=self.root)
        self.assertEqual({"clip": "spin", "time": 1.0}, payload["animation"])

    def test_time_without_animation_is_refused(self) -> None:
        """The moment indexes a clip; without one it is meaningless — refused
        the way focus+hide is, before any job is built."""
        from cadgen import step

        with self.assertRaisesRegex(ValueError, "time requires animation"):
            step.snapshot(Path("models/part.step"), Path("tmp/part.png"), time=1.0)

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = cad_snapshot_entry.main(["models/part.step", "tmp/o.png", "--time", "1"])
        self.assertEqual(1, code)
        self.assertIn("time requires animation", errors.getvalue())

    def test_the_library_door_takes_the_request_as_one_object(self) -> None:
        """`snapshot(animation={"clip": ..., "time": ...})` is the dict spelling
        of the flag pair; the clip name alone, and inline JSON, are the others.
        Naming the time twice is refused rather than silently picking one."""
        from cadgen.snapshot_cli import parse_animation_option

        self.assertEqual({"clip": "demo", "time": 3.0}, parse_animation_option({"clip": "demo", "time": 3}))
        self.assertEqual({"clip": "demo", "time": 0.0}, parse_animation_option({"clip": "demo"}))
        self.assertEqual({"clip": "demo", "time": 1.0}, parse_animation_option('{"clip": "demo", "time": 1}'))
        self.assertEqual({"clip": "demo", "time": 2.0}, parse_animation_option("demo", 2))
        with self.assertRaisesRegex(SnapshotError, "given twice"):
            parse_animation_option({"clip": "demo", "time": 3}, 1)

    def test_the_request_has_a_closed_shape(self) -> None:
        from cadgen.snapshot_cli import parse_animation_option

        for bad, pattern in (
            ({"clip": "demo", "speed": 2}, r"unknown key\(s\): speed; supported keys: clip, time"),
            ({"time": 2}, "must name a clip"),
            ({"clip": "demo", "time": -1}, "time must be seconds >= 0"),
            ({"clip": "demo", "time": "soon"}, "time must be seconds >= 0"),
            ({"clip": "demo", "time": True}, "time must be seconds >= 0"),
        ):
            with self.subTest(request=bad):
                with self.assertRaisesRegex(SnapshotError, pattern):
                    parse_animation_option(bad)

    def test_a_job_packet_request_is_validated_for_shape_too(self) -> None:
        """A packet carries the field directly, so it never met the flag parser;
        the resolver holds it to the same shape."""
        self._step()
        with self.assertRaisesRegex(SnapshotError, r'render job animation must be a \{"clip": name, "time": seconds\} object'):
            self._resolve(self._job(animation="demo"))
        with self.assertRaisesRegex(SnapshotError, r"render job animation has unknown key\(s\): loop"):
            self._resolve(self._job(animation={"clip": "demo", "loop": False}))

    def test_a_declared_clip_resolves_the_sidecar_url_and_normalizes_the_request(self) -> None:
        # An animation-only model: no kinematics at all, and the frame still
        # needs the sidecar, because that is where the copied .anim.js lives.
        self._step()
        packet = self._resolve(self._job(animation={"clip": "demo", "time": 2}))
        resolved_job = packet["jobs"][0]
        self.assertIn(".step.json", str(resolved_job["resolved"]["stepParameterUrl"]))
        self.assertEqual({"clip": "demo", "time": 2.0}, resolved_job["animation"])

    def test_an_unknown_clip_is_refused_with_the_declared_clips(self) -> None:
        """A typo fails as a CLI error naming what the model has — never as a
        stack trace out of the browser, and never as a rest-pose render."""
        self._step()
        with self.assertRaisesRegex(
            SnapshotError, r"Unknown animation clip: orbit\. This model declares: demo, spin"
        ):
            self._resolve(self._job(animation={"clip": "orbit"}))

    def test_a_module_that_declares_no_clips_says_so(self) -> None:
        self._step(clips="export const clips = {};")
        with self.assertRaisesRegex(
            SnapshotError, r"Unknown animation clip: demo\. This model declares no animation clips"
        ):
            self._resolve(self._job(animation={"clip": "demo"}))

    def test_a_module_built_indirectly_defers_the_name_check_to_the_runtime(self) -> None:
        # The CLI reads the literal the contract requires; a module that assembles
        # its clips some other way is not refused on a guess — the runtime, with
        # the compiled clips in hand, is the authority that names the set.
        self._step(clips="const build = () => ({ demo: { update() {} } });\nexport const clips = build();")
        packet = self._resolve(self._job(animation={"clip": "anything"}))
        self.assertEqual({"clip": "anything", "time": 0.0}, packet["jobs"][0]["animation"])

    def test_a_model_without_animation_has_no_frame_to_render(self) -> None:
        self._step(clips=None)
        with self.assertRaisesRegex(SnapshotError, "declares no animation") as caught:
            self._resolve(self._job(animation={"clip": "demo"}))
        self.assertIn("animation=", str(caught.exception))

    def test_a_frame_is_layered_over_kinematics_not_instead_of_it(self) -> None:
        """Both fields travel; neither gates the other — the same sidecar URL
        serves both loaders, and each reads only its own section."""
        pose = {
            "mates": [{"name": "stroke", "kind": "slider", "parent": "#body", "child": "#ram",
                       "axis": {"origin": [0, 0, 0], "dir": [0, 0, 1]},
                       "limits": {"value": [0, 1]}}],
        }
        self._step(kinematics=pose)
        packet = self._resolve(self._job(kinematics={"stroke": 1}, animation={"clip": "spin", "time": 0.5}))
        resolved_job = packet["jobs"][0]
        self.assertEqual({"stroke": 1}, resolved_job["kinematics"])
        self.assertEqual({"clip": "spin", "time": 0.5}, resolved_job["animation"])
        self.assertIn(".step.json", str(resolved_job["resolved"]["stepParameterUrl"]))

    def test_a_frame_supports_only_view_mode(self) -> None:
        self._step()
        with self.assertRaisesRegex(SnapshotError, "animation frame supports only view mode"):
            self._resolve(self._job(mode="section", animation={"clip": "demo"}))

    def test_a_frame_requires_a_step_model(self) -> None:
        (self.models / "part.stl").write_bytes(b"solid part\nendsolid part\n")
        with self.assertRaisesRegex(SnapshotError, "animation frame requires a STEP model"):
            self._resolve(self._job(name="part.stl", animation={"clip": "demo"}))


class ExactOutputContractTests(unittest.TestCase):
    """The declared path is the written path, and a failure leaves nothing there.

    The two halves are one contract. Honouring the declaration is only safe
    because the target is cleared BEFORE the render: what used to protect an
    agent from reading yesterday's image was the datetimestamp appended to its
    filename, and dropping that without the pre-delete would reintroduce exactly
    the silently-plausible stale read the timestamp existed to prevent.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="snapshot-exact-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.target = self.root / "tmp" / "review.png"
        self.target.parent.mkdir(parents=True)

    def _packet(self, *outputs: dict) -> dict:
        return {
            "single": True,
            "jobs": [{"input": "models/part.step", "outputs": list(outputs)}],
        }

    def _render(self, packet: dict, renderer) -> object:
        return asyncio.run(
            snapshot_main.render_resolved_job_packet(packet, runtime_dir=RUNTIME_DIR, renderer=renderer)
        )

    @staticmethod
    def _renderer(result: object = None, *, error: str | None = None):
        class StubRenderer:
            async def render(self, job):
                if error is not None:
                    raise SnapshotError(error)
                return result if result is not None else {"ok": True, "mode": "view", "outputs": []}

            async def close(self):
                return None

        return StubRenderer()

    def test_a_successful_render_writes_exactly_the_declared_path(self) -> None:
        payload = b"\x89PNG\r\n\x1a\n" + b"rendered"
        output = {
            "path": str(self.target),
            "dataUrl": "data:image/png;base64," + base64.b64encode(payload).decode("ascii"),
        }
        result = {"ok": True, "mode": "view", "outputs": [output]}
        self._render(self._packet({"path": str(self.target)}), self._renderer(result))
        snapshot_main.write_render_outputs(result)

        self.assertEqual(self.target.read_bytes(), payload)
        # No timestamped sibling, and no temp file left beside it either.
        self.assertEqual([p.name for p in sorted(self.target.parent.iterdir())], ["review.png"])

    def test_a_failed_render_leaves_no_file_at_the_target(self) -> None:
        self.target.write_bytes(b"yesterday's render")
        with self.assertRaises(SnapshotError):
            self._render(self._packet({"path": str(self.target)}), self._renderer(error="browser blew up"))
        self.assertFalse(self.target.exists(), "a failed render must leave nothing to read")
        self.assertEqual(list(self.target.parent.iterdir()), [])

    def test_the_target_is_cleared_before_the_browser_starts(self) -> None:
        """Ordering, not just outcome: the clear happens before any rendering, so a
        render that hangs or is killed cannot leave the old file readable either."""
        self.target.write_bytes(b"yesterday's render")
        seen: list[bool] = []

        class ObservingRenderer:
            async def render(inner, job):  # noqa: N805 - stub signature
                seen.append(self.target.exists())
                return {"ok": True, "mode": "view", "outputs": []}

            async def close(inner):  # noqa: N805 - stub signature
                return None

        self._render(self._packet({"path": str(self.target)}), ObservingRenderer())
        self.assertEqual(seen, [False])

    def test_a_multi_output_packet_clears_every_declared_target(self) -> None:
        """Per output, and across jobs -- an earlier job's render must not leave a
        later job's stale file readable while it runs."""
        second = self.root / "tmp" / "front.png"
        for path in (self.target, second):
            path.write_bytes(b"stale")
        packet = {
            "single": False,
            "jobs": [
                {"input": "models/part.step", "outputs": [{"path": str(self.target)}]},
                {"input": "models/part.step", "outputs": [{"path": str(second)}]},
            ],
        }
        clear_render_output_targets(packet["jobs"])
        self.assertFalse(self.target.exists())
        self.assertFalse(second.exists())

    def test_a_directory_output_is_left_alone(self) -> None:
        """A directory-valued output generates a fresh name, so it has nothing of
        its own to clear -- and unlinking the directory would be the wrong move
        besides."""
        shots = self.root / "shots"
        shots.mkdir()
        (shots / "old.png").write_bytes(b"an earlier generated name")
        clear_render_output_targets(
            [{"outputs": [{"path": "shots/"}, {"path": "shots"}]}], resolved_cwd=self.root
        )
        self.assertTrue(shots.is_dir())
        self.assertTrue((shots / "old.png").exists())

    def test_declared_paths_are_cleared_from_an_unresolved_payload(self) -> None:
        """The clear runs on the RAW job, before resolution -- the stage where a bad
        input actually fails. Bare-string outputs and cwd-relative paths are both
        read here, because that is the shape the caller wrote."""
        self.target.write_bytes(b"stale")
        second = self.root / "tmp" / "front.png"
        second.write_bytes(b"stale")
        clear_render_output_targets(
            [{"outputs": ["tmp/review.png", {"path": "tmp/front.png"}]}], resolved_cwd=self.root
        )
        self.assertFalse(self.target.exists())
        self.assertFalse(second.exists())

    def test_a_write_that_fails_leaves_no_partial_file(self) -> None:
        """Atomicity: the payload lands through a temp file and a rename, so a write
        that dies mid-stream leaves the target absent rather than half a PNG at the
        exact name the caller is about to read."""
        def exploding_replace(temp_path, target_path):
            Path(temp_path).unlink(missing_ok=True)
            raise OSError("disk went away mid-rename")

        with mock.patch.object(
            sys.modules["cadgen._internal.atomic_replace"], "replace_atomic", exploding_replace
        ):
            with self.assertRaises(OSError):
                snapshot_main.write_output_payload(
                    {
                        "path": str(self.target),
                        "dataUrl": "data:image/png;base64," + base64.b64encode(b"x" * 4096).decode("ascii"),
                    }
                )
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.iterdir()), [])

    def test_a_missing_data_url_writes_nothing_at_the_target(self) -> None:
        with self.assertRaisesRegex(SnapshotError, "base64 data URL"):
            snapshot_main.write_output_payload({"path": str(self.target)})
        self.assertFalse(self.target.exists())

    def test_a_target_that_cannot_be_cleared_fails_before_the_render(self) -> None:
        def refuse(self_path, *, missing_ok=False):
            raise PermissionError("held open")

        self.target.write_bytes(b"held")
        with mock.patch.object(Path, "unlink", refuse):
            with self.assertRaisesRegex(SnapshotError, "Cannot clear the snapshot output path"):
                clear_render_output_targets(self._packet({"path": str(self.target)})["jobs"])

    def test_a_run_that_fails_before_the_render_still_leaves_no_file(self) -> None:
        """End to end through the CLI: an input that fails during RESOLUTION -- the
        expensive stage, where a broken model actually fails -- must not leave the
        previous render sitting at the requested path. Clearing at render time
        alone left it there for exactly the runs most likely to be misread."""
        self.target.write_bytes(b"yesterday's render")
        (self.root / "STEP").mkdir()
        (self.root / "STEP" / "broken.step").write_text("not a step file at all\n", encoding="utf-8")

        stdout = io.StringIO()
        stderr = io.StringIO()
        options = snapshot_main.SnapshotOptions(
            input="STEP/broken.step", output="tmp/review.png"
        )
        code = emit(
            lambda: snapshot_main.run_snapshot(
                options, kinds=STEP_KINDS, cwd=self.root, stdin=_TtyStringIO()
            ),
            prog="cadgen step snapshot",
            as_json=False,
            stdout=stdout,
            stderr=stderr,
        )
        self.assertNotEqual(code, 0)
        self.assertFalse(self.target.exists(), "a failed run must leave nothing to read")


if __name__ == "__main__":
    unittest.main()
