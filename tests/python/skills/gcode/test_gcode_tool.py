#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("skills/gcode/scripts")

import gcode_tool as gcode


def make_executable(path: Path) -> Path:
    """Create a fake backend that this platform will actually treat as executable.

    A shebang plus the exec bit is the POSIX answer and means nothing on Windows: there
    CreateProcess wants a real image, and shutil.which() only considers names carrying a
    PATHEXT extension -- so an extension-less `OrcaSlicer` is invisible to discovery and
    unrunnable if found. A .cmd is both, and is what an installed slicer looks like there.
    """
    if os.name == "nt":
        shim = path.with_suffix(".cmd")
        shim.write_text("@exit /b 0\r\n", encoding="utf-8")
        return shim
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def write_profile(tmp: Path, backend: str = "orcaslicer") -> Path:
    native_config = tmp / f"{backend}.ini"
    native_config.write_text("# slicer profile\n", encoding="utf-8")
    profile = tmp / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "backend": backend,
                "native_config": str(native_config),
                "machine": {
                    "name": "Test Printer",
                    "bed_size_mm": [180, 180],
                    "z_height_mm": 180,
                },
                "filament": {
                    "type": "PLA",
                    "nozzle_temp_c": 220,
                    "bed_temp_c": 65,
                },
            }
        ),
        encoding="utf-8",
    )
    return profile


def write_profile_with_motion_bounds(tmp: Path) -> Path:
    native_config = tmp / "orcaslicer.ini"
    native_config.write_text("# slicer profile\n", encoding="utf-8")
    profile = tmp / "profile_with_motion_bounds.json"
    profile.write_text(
        json.dumps(
            {
                "backend": "orcaslicer",
                "native_config": str(native_config),
                "machine": {
                    "name": "Test Printer",
                    "bed_size_mm": [180, 180],
                    "z_height_mm": 180,
                    "motion_bounds_mm": {
                        "x": [-14, 181],
                        "y": [-4, 185],
                        "z": [-1.1, 180],
                    },
                },
                "filament": {
                    "type": "PLA",
                    "nozzle_temp_c": 220,
                    "bed_temp_c": 65,
                },
            }
        ),
        encoding="utf-8",
    )
    return profile


class GCodeToolTests(unittest.TestCase):
    def test_discovers_fake_preferred_backend_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            make_executable(bin_dir / "OrcaSlicer")
            make_executable(bin_dir / "prusa-slicer")

            report = gcode.discovery_report(search_path=str(bin_dir))

        backends = {item["id"]: item for item in report["backends"]}
        self.assertTrue(backends["orcaslicer"]["available"])
        self.assertTrue(backends["prusa-slicer"]["available"])
        self.assertFalse(backends["curaengine"]["available"])
        self.assertEqual(report["preferred_order"], ["orcaslicer", "prusa-slicer", "curaengine"])

    def test_profile_validation_requires_backend_native_config_and_bed_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_backend = root / "missing_backend.json"
            missing_backend.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(gcode.GCodeToolError, "backend"):
                gcode.load_profile(missing_backend)

            missing_native = root / "missing_native.json"
            missing_native.write_text(
                json.dumps(
                    {
                        "backend": "orcaslicer",
                        "machine": {"name": "Printer", "bed_size_mm": [180, 180], "z_height_mm": 180},
                        "filament": {"type": "PLA", "nozzle_temp_c": 220, "bed_temp_c": 65},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(gcode.GCodeToolError, "native_config"):
                gcode.load_profile(missing_native)

            bad_bed = root / "bad_bed.json"
            native_config = root / "profile.ini"
            native_config.write_text("# config\n", encoding="utf-8")
            bad_bed.write_text(
                json.dumps(
                    {
                        "backend": "orcaslicer",
                        "native_config": str(native_config),
                        "machine": {"name": "Printer", "bed_size_mm": [180], "z_height_mm": 180},
                        "filament": {"type": "PLA", "nozzle_temp_c": 220, "bed_temp_c": 65},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(gcode.GCodeToolError, "bed_size_mm"):
                gcode.load_profile(bad_bed)

    def test_input_classification_for_supported_rejected_and_sliced_bambu_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stl = root / "part.stl"
            stl.write_text("solid part\nendsolid part\n", encoding="utf-8")
            stl_info = gcode.inspect_input(stl)
            self.assertTrue(stl_info.direct_to_slicer)
            self.assertFalse(stl_info.needs_stl_conversion)

            glb = root / "part.glb"
            glb.write_bytes(b"glTF")
            glb_info = gcode.inspect_input(glb)
            self.assertTrue(glb_info.needs_stl_conversion)

            sliced = root / "job.gcode.3mf"
            with zipfile.ZipFile(sliced, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("Metadata/plate_1.gcode", "G1 X1\n")
            sliced_info = gcode.inspect_input(sliced)
            self.assertTrue(sliced_info.already_sliced_bambu)
            self.assertEqual(sliced_info.status, "already_sliced_bambu_3mf")

            step = root / "part.step"
            step.write_text("ISO-10303-21;", encoding="utf-8")
            with self.assertRaisesRegex(gcode.GCodeToolError, "out of scope"):
                gcode.inspect_input(step)

    def test_rejected_inputs_name_the_conversion_skill_and_command(self) -> None:
        expected_skills = {
            ".step": "cad",
            ".stp": "cad",
            ".dxf": "cad",
            ".svg": "cad",
            ".urdf": "urdf",
            ".sdf": "sdf",
        }
        self.assertEqual(gcode.UNSUPPORTED_EXTENSIONS, set(expected_skills))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for extension, skill in expected_skills.items():
                with self.subTest(extension=extension):
                    rejected = root / f"part{extension}"
                    rejected.write_text("placeholder\n", encoding="utf-8")

                    with self.assertRaises(gcode.GCodeToolError) as caught:
                        gcode.inspect_input(rejected)
                    remediation = caught.exception.details["remediation"]
                    self.assertEqual(remediation["extension"], extension)
                    self.assertEqual(remediation["skill"], skill)
                    self.assertTrue(remediation["reason"])
                    self.assertIn(f"${skill}", remediation["next_step"])
                    self.assertIn(".stl", remediation["next_step"])

                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        code = gcode.main(["inspect", "--input", str(rejected), "--json"])
                    payload = json.loads(stdout.getvalue())
                    self.assertEqual(code, 2)
                    self.assertFalse(payload["ok"])
                    self.assertIn("out of scope", payload["error"])
                    self.assertEqual(payload["remediation"], remediation)

            profile = write_profile(root)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = gcode.main(
                    [
                        "slice",
                        "--input",
                        str(root / "part.step"),
                        "--output",
                        str(root / "part.gcode"),
                        "--profile",
                        str(profile),
                        "--dry-run",
                    ]
                )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(stdout.getvalue())["remediation"]["skill"], "cad")

    def test_dry_run_command_construction_for_each_backend(self) -> None:
        cases = [
            ("orcaslicer", "OrcaSlicer", ["--load-settings", "--outputdir", "--slice"]),
            ("prusa-slicer", "prusa-slicer", ["--load", "--export-gcode", "--output"]),
            ("curaengine", "CuraEngine", ["slice", "-j", "-l", "-o"]),
        ]
        for backend, executable, expected_parts in cases:
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                bin_dir = root / "bin"
                bin_dir.mkdir()
                make_executable(bin_dir / executable)
                profile = write_profile(root, backend)
                model = root / "part.obj"
                model.write_text("o part\n", encoding="utf-8")
                output = root / "part.gcode"
                args = gcode.build_parser().parse_args(
                    [
                        "slice",
                        "--input",
                        str(model),
                        "--output",
                        str(output),
                        "--profile",
                        str(profile),
                        "--backend",
                        "auto",
                        "--dry-run",
                    ]
                )

                plan = gcode.build_slice_plan(args, search_path=str(bin_dir))

                command = plan["command"]
                # stem on Windows: an executable IS its extension there, and which() hands
                # back the name as PATHEXT spells it -- "OrcaSlicer.CMD". What this asserts
                # is WHICH backend was selected, not how the filesystem writes it down.
                found = Path(command[0])
                self.assertEqual(found.stem if os.name == "nt" else found.name, executable)
                for part in expected_parts:
                    self.assertIn(part, command)
                self.assertEqual(plan["backend"], backend)
                self.assertFalse(plan["conversion"]["required"])

    def test_refuses_to_slice_already_sliced_bambu_3mf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            make_executable(bin_dir / "OrcaSlicer")
            profile = write_profile(root)
            sliced = root / "job.gcode.3mf"
            with zipfile.ZipFile(sliced, "w") as archive:
                archive.writestr("Metadata/plate_1.gcode", "G1 X1\n")
            args = gcode.build_parser().parse_args(
                [
                    "slice",
                    "--input",
                    str(sliced),
                    "--output",
                    str(root / "job.gcode"),
                    "--profile",
                    str(profile),
                    "--dry-run",
                ]
            )

            with self.assertRaisesRegex(gcode.GCodeToolError, "already a sliced Bambu"):
                gcode.build_slice_plan(args, search_path=str(bin_dir))

    def test_gcode_validation_passes_valid_simple_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = gcode.load_profile(write_profile(root))
            toolpath = root / "valid.gcode"
            toolpath.write_text(
                "\n".join(
                    [
                        "M104 S220",
                        "M140 S65",
                        "G90",
                        "G1 X10 Y10 Z0.2 F1800",
                        "G1 X20 Y10 E0.4 F1200",
                    ]
                ),
                encoding="utf-8",
            )

            result = gcode.validate_gcode_file(toolpath, profile)

        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])
        self.assertGreaterEqual(result["stats"]["extrusion_moves"], 1)

    def test_gcode_validation_does_not_count_retraction_as_extrusion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = gcode.load_profile(write_profile(root))
            toolpath = root / "retraction_only.gcode"
            toolpath.write_text(
                "\n".join(
                    [
                        "M104 S220",
                        "M140 S65",
                        "G90",
                        "M83",
                        "G1 X10 Y10 Z0.2 F1800",
                        "G1 X15 Y10 E0 F1200",
                        "G1 X20 Y10 E-1 F1200",
                    ]
                ),
                encoding="utf-8",
            )

            result = gcode.validate_gcode_file(toolpath, profile)

        self.assertFalse(result["ok"])
        self.assertEqual(result["stats"]["extrusion_moves"], 0)
        self.assertIn("No extrusion moves found.", result["errors"])

    def test_gcode_validation_tracks_extruder_position_and_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = gcode.load_profile(write_profile(root))
            toolpath = root / "mixed_extrusion_modes.gcode"
            toolpath.write_text(
                "\n".join(
                    [
                        "M104 S220",
                        "M140 S65",
                        "G92 E10",
                        "M83",
                        "G90",
                        "G1 X10 Y10 Z0.2 E9 F1800",
                        "G91",
                        "G1 X1 E-1 F1200",
                        "M82",
                        "G1 X1 E7.5 F1200",
                        "M83",
                        "G2 X1 Y1 I0.5 J0 E0.2 F1200",
                        "G1 X1 E0.1 F1200",
                    ]
                ),
                encoding="utf-8",
            )

            result = gcode.validate_gcode_file(toolpath, profile)

        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["stats"]["extrusion_moves"], 2)

    def test_gcode_validation_counts_forward_extrusion_for_each_motion_command(self) -> None:
        commands = {
            "G0": "G0 X10 E-9 F1200",
            "G1": "G1 X10 E-9 F1200",
            "G2": "G2 X10 Y10 I5 J0 E-9 F1200",
            "G3": "G3 X10 Y10 I5 J0 E-9 F1200",
        }
        for command, movement in commands.items():
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                profile = gcode.load_profile(write_profile(root))
                toolpath = root / f"{command.lower()}_extrusion.gcode"
                toolpath.write_text(
                    "\n".join(
                        [
                            "M104 S220",
                            "M140 S65",
                            "M82",
                            "G92 E-10",
                            movement,
                        ]
                    ),
                    encoding="utf-8",
                )

                result = gcode.validate_gcode_file(toolpath, profile)

            self.assertTrue(result["ok"])
            self.assertEqual(result["stats"]["extrusion_moves"], 1)

    def test_gcode_validation_does_not_treat_decimal_subcodes_as_positioning_modes(self) -> None:
        cases = {
            "relative_extrusion_after_g90_1": (
                ["G92 E10", "M83", "G90.1", "G2 X10 Y10 I5 J0 E0.2 F1200"],
                True,
                1,
            ),
            "absolute_retraction_after_g91_1": (
                ["G92 E10", "M82", "G91.1", "G2 X10 Y10 I5 J0 E9 F1200"],
                False,
                0,
            ),
        }
        for name, (commands, expected_ok, expected_extrusion_moves) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                profile = gcode.load_profile(write_profile(root))
                toolpath = root / f"{name}.gcode"
                toolpath.write_text("\n".join(["M104 S220", "M140 S65", *commands]), encoding="utf-8")

                result = gcode.validate_gcode_file(toolpath, profile)

                self.assertEqual(result["ok"], expected_ok)
                self.assertEqual(result["stats"]["extrusion_moves"], expected_extrusion_moves)

    def test_gcode_validation_reports_empty_no_extrusion_and_out_of_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = gcode.load_profile(write_profile(root))

            empty = root / "empty.gcode"
            empty.write_text("", encoding="utf-8")
            empty_result = gcode.validate_gcode_file(empty, profile)
            self.assertFalse(empty_result["ok"])
            self.assertIn("G-code file is empty.", empty_result["errors"])

            no_extrusion = root / "no_extrusion.gcode"
            no_extrusion.write_text("M104 S220\nG1 X10 Y10 Z0.2\n", encoding="utf-8")
            no_extrusion_result = gcode.validate_gcode_file(no_extrusion, profile)
            self.assertFalse(no_extrusion_result["ok"])
            self.assertIn("No extrusion moves found.", no_extrusion_result["errors"])

            out_of_bounds = root / "out_of_bounds.gcode"
            out_of_bounds.write_text("M104 S220\nG1 X999 Y10 Z0.2 E0.1\n", encoding="utf-8")
            out_of_bounds_result = gcode.validate_gcode_file(out_of_bounds, profile)
            self.assertFalse(out_of_bounds_result["ok"])
            self.assertTrue(any("X=999.0" in error for error in out_of_bounds_result["errors"]))

    def test_gcode_validation_uses_optional_motion_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = gcode.load_profile(write_profile_with_motion_bounds(root))
            toolpath = root / "native_start_positions.gcode"
            toolpath.write_text("M104 S220\nM140 S65\nG90\nG1 X-13.5 Y-4 Z-1 E0.1\n", encoding="utf-8")

            result = gcode.validate_gcode_file(toolpath, profile)

        self.assertTrue(result["ok"])

    def test_gcode_validation_warns_for_unknown_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = gcode.load_profile(write_profile(root))
            toolpath = root / "unknown.gcode"
            toolpath.write_text("M104 S220\nM999\nG1 X10 Y10 Z0.2 E0.1\n", encoding="utf-8")

            result = gcode.validate_gcode_file(toolpath, profile)

        self.assertTrue(result["ok"])
        self.assertTrue(any("M999" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
