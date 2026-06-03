#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("skills/gcode/scripts")

import gcode_tool as gcode


def make_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


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
                self.assertEqual(Path(command[0]).name, executable)
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
