#!/usr/bin/env python3
"""Dry-run-first helpers for generating and validating plain FDM G-code."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DIRECT_MESH_EXTENSIONS = {".stl", ".obj", ".3mf"}
CONVERT_TO_STL_EXTENSIONS = {".ply", ".glb", ".gltf"}

_STEP_REMEDIATION = {
    "skill": "cad",
    "reason": "STEP/STP is boundary-representation CAD, not a mesh.",
    "next_step": (
        "Export an STL sidecar with $cad: `python scripts/step --kind part <input> --stl <output>.stl`. "
        "When a Python generator exists, target it instead: `python scripts/step <model>.step.py --stl <output>.stl`. "
        "Then slice the exported .stl with this skill."
    ),
}
_FLAT_2D_REMEDIATION = {
    "skill": "cad",
    "reason": "This is a 2D drawing, not a printable solid, and this toolchain has no 2D-to-mesh conversion.",
    "next_step": (
        "For an FDM print, model the 3D solid in $cad with `gen_step()` and export an STL sidecar "
        "(`python scripts/step <model>.step.py --stl <output>.stl`), then slice that .stl here. "
        "If the part is a flat cut rather than a print, use $sendcutsend instead of this skill."
    ),
}


def _robot_description_remediation(skill: str, label: str) -> dict[str, str]:
    return {
        "skill": skill,
        "reason": f"{label} is a robot description that references per-link mesh files; it is not itself a mesh.",
        "next_step": (
            f"Slice the per-link .stl/.obj meshes the {label} references, one mesh at a time. "
            f"If those meshes are missing or stale, regenerate them from the owning CAD source with $cad "
            "(`python scripts/step <model>.step.py --stl <output>.stl`), then slice the exported mesh here. "
            f"Use ${skill} for the robot description itself."
        ),
    }


UNSUPPORTED_INPUT_REMEDIATION = {
    ".step": _STEP_REMEDIATION,
    ".stp": _STEP_REMEDIATION,
    ".dxf": _FLAT_2D_REMEDIATION,
    ".svg": _FLAT_2D_REMEDIATION,
    ".urdf": _robot_description_remediation("urdf", "URDF"),
    ".sdf": _robot_description_remediation("sdf", "SDF"),
}
UNSUPPORTED_EXTENSIONS = set(UNSUPPORTED_INPUT_REMEDIATION)
SLICED_BAMBU_PLATE_RE = re.compile(r"^Metadata/plate_(\d+)\.gcode$")

PREFERRED_BACKEND_ORDER = ["orcaslicer", "prusa-slicer", "curaengine"]
BACKEND_EXECUTABLES = {
    "orcaslicer": ["OrcaSlicer", "orca-slicer", "orcaslicer"],
    "prusa-slicer": ["prusa-slicer", "PrusaSlicer", "prusa-slicer-console"],
    "curaengine": ["CuraEngine", "curaengine"],
}
BACKEND_APP_GLOBS = {
    "orcaslicer": ["OrcaSlicer*.app/Contents/MacOS/OrcaSlicer"],
    "prusa-slicer": ["PrusaSlicer*.app/Contents/MacOS/PrusaSlicer"],
}
BACKEND_ENV_VARS = {
    "orcaslicer": "ORCASLICER_BIN",
    "prusa-slicer": "PRUSASLICER_BIN",
    "curaengine": "CURAENGINE_BIN",
}
BAMBU_EXECUTABLES = ["bambu-studio", "BambuStudio"]
SUPPORTED_GCODE_COMMANDS = {
    "G0",
    "G1",
    "G2",
    "G3",
    "G4",
    "G21",
    "G28",
    "G29",
    "G90",
    "G91",
    "G92",
    "M18",
    "M73",
    "M82",
    "M83",
    "M84",
    "M104",
    "M106",
    "M107",
    "M109",
    "M117",
    "M118",
    "M140",
    "M190",
    "M201",
    "M203",
    "M204",
    "M205",
    "M220",
    "M221",
    "M400",
    "M500",
    "M501",
    "M900",
}


class GCodeToolError(RuntimeError):
    """Raised for expected user-facing workflow errors."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class BackendDiscovery:
    id: str
    available: bool
    path: str | None
    preferred: bool
    reason: str = ""


@dataclass(frozen=True)
class GCodeProfile:
    backend: str
    native_config: str
    native_settings: tuple[str, ...]
    native_filaments: tuple[str, ...]
    machine_name: str
    bed_size_mm: tuple[float, float]
    z_height_mm: float
    motion_bounds_mm: dict[str, tuple[float, float]]
    filament_type: str
    nozzle_temp_c: float
    bed_temp_c: float


@dataclass(frozen=True)
class InputInspection:
    path: str
    extension: str
    size_bytes: int
    supported: bool
    direct_to_slicer: bool
    needs_stl_conversion: bool
    already_sliced_bambu: bool
    status: str


def tail_text(value: str, *, max_lines: int = 80) -> str:
    lines = value.splitlines()
    if len(lines) <= max_lines:
        return value
    return "\n".join(lines[-max_lines:])


def find_executable(names: list[str], *, search_path: str | None = None) -> str | None:
    for name in names:
        found = shutil.which(name, path=search_path)
        if found:
            return found
    return None


def find_app_executable(backend: str) -> str | None:
    applications = Path("/Applications")
    if not applications.exists():
        return None
    for pattern in BACKEND_APP_GLOBS.get(backend, []):
        for path in sorted(applications.glob(pattern)):
            if path.is_file():
                return str(path)
    return None


def find_backend_executable(backend: str, *, search_path: str | None = None) -> str | None:
    env_value = os.environ.get(BACKEND_ENV_VARS[backend], "").strip()
    if env_value:
        return env_value
    return find_executable(BACKEND_EXECUTABLES[backend], search_path=search_path) or find_app_executable(backend)


def discover_backends(*, search_path: str | None = None) -> list[BackendDiscovery]:
    discoveries: list[BackendDiscovery] = []
    for backend_id in PREFERRED_BACKEND_ORDER:
        path = find_backend_executable(backend_id, search_path=search_path)
        discoveries.append(
            BackendDiscovery(
                id=backend_id,
                available=bool(path),
                path=path or None,
                preferred=True,
            )
        )
    return discoveries


def discover_bambu_studio(*, search_path: str | None = None) -> list[BackendDiscovery]:
    paths: list[str] = []
    env_value = os.environ.get("BAMBU_STUDIO_BIN", "").strip()
    if env_value:
        paths.append(env_value)
    which_value = find_executable(BAMBU_EXECUTABLES, search_path=search_path)
    if which_value:
        paths.append(which_value)
    applications = Path("/Applications")
    if applications.exists():
        for pattern in ("BambuStudio*.app/Contents/MacOS/BambuStudio", "Bambu Studio*.app/Contents/MacOS/BambuStudio"):
            paths.extend(str(path) for path in applications.glob(pattern))

    unique_paths = sorted(dict.fromkeys(paths))
    if not unique_paths:
        return [
            BackendDiscovery(
                id="bambu-studio",
                available=False,
                path=None,
                preferred=False,
                reason="not preferred because Bambu Studio CLI has shown macOS export instability",
            )
        ]
    return [
        BackendDiscovery(
            id="bambu-studio",
            available=True,
            path=path,
            preferred=False,
            reason="available but not preferred because Bambu Studio CLI has shown macOS export instability",
        )
        for path in unique_paths
    ]


def discovery_report(*, search_path: str | None = None) -> dict[str, Any]:
    backends = discover_backends(search_path=search_path)
    not_preferred = discover_bambu_studio(search_path=search_path)
    return {
        "preferred_order": PREFERRED_BACKEND_ORDER,
        "backends": [asdict(item) for item in backends],
        "not_preferred": [asdict(item) for item in not_preferred],
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise GCodeToolError(f"Profile does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GCodeToolError(f"Profile is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GCodeToolError("Profile JSON must be an object.")
    return data


def require_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise GCodeToolError(f"Profile field {label} must be a number.")
    number = float(value)
    if number <= 0:
        raise GCodeToolError(f"Profile field {label} must be greater than zero.")
    return number


def require_absolute_file(path_value: str, label: str) -> str:
    profile_path = Path(path_value).expanduser()
    if not profile_path.is_absolute():
        raise GCodeToolError(f"Profile field {label} must be an absolute path.")
    if not profile_path.is_file():
        raise GCodeToolError(f"Profile {label} does not exist: {profile_path}")
    return str(profile_path)


def optional_path_list(data: dict[str, Any], field: str) -> tuple[str, ...]:
    value = data.get(field)
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        values = value
    else:
        raise GCodeToolError(f"Profile field {field} must be a string path or list of string paths.")
    paths = [item.strip() for item in values if item.strip()]
    if not paths:
        raise GCodeToolError(f"Profile field {field} cannot be empty when provided.")
    return tuple(require_absolute_file(path, field) for path in paths)


def parse_axis_bounds(value: Any, label: str) -> tuple[float, float]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value)
    ):
        raise GCodeToolError(f"Profile field {label} must be [min, max].")
    lower = float(value[0])
    upper = float(value[1])
    if lower >= upper:
        raise GCodeToolError(f"Profile field {label} must have min less than max.")
    return lower, upper


def load_profile(path: Path) -> GCodeProfile:
    data = load_json(path)
    backend = str(data.get("backend") or "").strip().lower()
    if backend not in PREFERRED_BACKEND_ORDER:
        raise GCodeToolError(f"Profile backend must be one of: {', '.join(PREFERRED_BACKEND_ORDER)}.")

    native_config = str(data.get("native_config") or "").strip()
    if not native_config:
        raise GCodeToolError("Profile field native_config is required.")
    native_config = require_absolute_file(native_config, "native_config")
    native_settings = optional_path_list(data, "native_settings") or (native_config,)
    native_filaments = optional_path_list(data, "native_filaments")

    machine = data.get("machine")
    if not isinstance(machine, dict):
        raise GCodeToolError("Profile field machine must be an object.")
    machine_name = str(machine.get("name") or "").strip()
    if not machine_name:
        raise GCodeToolError("Profile field machine.name is required.")
    bed_size = machine.get("bed_size_mm")
    if (
        not isinstance(bed_size, list)
        or len(bed_size) != 2
        or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in bed_size)
    ):
        raise GCodeToolError("Profile field machine.bed_size_mm must be [width, depth].")
    bed_x = require_number(bed_size[0], "machine.bed_size_mm[0]")
    bed_y = require_number(bed_size[1], "machine.bed_size_mm[1]")
    z_height = require_number(machine.get("z_height_mm"), "machine.z_height_mm")
    motion_bounds = {
        "x": (0.0, bed_x),
        "y": (0.0, bed_y),
        "z": (0.0, z_height),
    }
    if "motion_bounds_mm" in machine:
        raw_bounds = machine.get("motion_bounds_mm")
        if not isinstance(raw_bounds, dict):
            raise GCodeToolError("Profile field machine.motion_bounds_mm must be an object.")
        for axis in ("x", "y", "z"):
            if axis in raw_bounds:
                motion_bounds[axis] = parse_axis_bounds(raw_bounds[axis], f"machine.motion_bounds_mm.{axis}")

    filament = data.get("filament")
    if not isinstance(filament, dict):
        raise GCodeToolError("Profile field filament must be an object.")
    filament_type = str(filament.get("type") or "").strip()
    if not filament_type:
        raise GCodeToolError("Profile field filament.type is required.")
    nozzle_temp = require_number(filament.get("nozzle_temp_c"), "filament.nozzle_temp_c")
    bed_temp = require_number(filament.get("bed_temp_c"), "filament.bed_temp_c")

    return GCodeProfile(
        backend=backend,
        native_config=native_config,
        native_settings=native_settings,
        native_filaments=native_filaments,
        machine_name=machine_name,
        bed_size_mm=(bed_x, bed_y),
        z_height_mm=z_height,
        motion_bounds_mm=motion_bounds,
        filament_type=filament_type,
        nozzle_temp_c=nozzle_temp,
        bed_temp_c=bed_temp,
    )


def is_sliced_bambu_3mf(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(SLICED_BAMBU_PLATE_RE.match(info.filename) for info in archive.infolist())
    except zipfile.BadZipFile:
        return False


def inspect_input(path: Path) -> InputInspection:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise GCodeToolError(f"Input file does not exist: {resolved}")

    extension = resolved.suffix.lower()
    remediation = UNSUPPORTED_INPUT_REMEDIATION.get(extension)
    if remediation is not None:
        supported = ", ".join(sorted(DIRECT_MESH_EXTENSIONS | CONVERT_TO_STL_EXTENSIONS))
        raise GCodeToolError(
            f"{extension} is out of scope for this skill. Supported v1 mesh inputs: {supported}. "
            f"{remediation['reason']} {remediation['next_step']}",
            details={"remediation": {"extension": extension, **remediation}},
        )
    if extension not in DIRECT_MESH_EXTENSIONS | CONVERT_TO_STL_EXTENSIONS:
        supported = ", ".join(sorted(DIRECT_MESH_EXTENSIONS | CONVERT_TO_STL_EXTENSIONS))
        raise GCodeToolError(f"Unsupported input extension {extension or '<none>'}. Supported v1 mesh inputs: {supported}.")

    already_sliced = extension == ".3mf" and is_sliced_bambu_3mf(resolved)
    if already_sliced:
        status = "already_sliced_bambu_3mf"
    elif extension in DIRECT_MESH_EXTENSIONS:
        status = "direct_to_slicer"
    else:
        status = "requires_stl_conversion"

    return InputInspection(
        path=str(resolved),
        extension=extension,
        size_bytes=resolved.stat().st_size,
        supported=True,
        direct_to_slicer=extension in DIRECT_MESH_EXTENSIONS and not already_sliced,
        needs_stl_conversion=extension in CONVERT_TO_STL_EXTENSIONS,
        already_sliced_bambu=already_sliced,
        status=status,
    )


def backend_path(backend: str, *, search_path: str | None = None) -> str:
    path = find_backend_executable(backend, search_path=search_path)
    if not path:
        names = ", ".join(BACKEND_EXECUTABLES[backend])
        raise GCodeToolError(f"Backend {backend} is not installed or not on PATH. Checked: {names}.")
    return path


def build_backend_command(
    *,
    backend: str,
    executable: str,
    slicer_input: Path,
    output: Path,
    profile: GCodeProfile,
) -> list[str]:
    if backend == "orcaslicer":
        command = [
            executable,
            "--load-settings",
            ";".join(profile.native_settings),
        ]
        if profile.native_filaments:
            command.extend(["--load-filaments", ";".join(profile.native_filaments)])
        command.extend(
            [
                "--outputdir",
                str(output.parent),
                "--slice",
                "0",
                str(slicer_input),
            ]
        )
        return command
    if backend == "prusa-slicer":
        return [
            executable,
            "--load",
            profile.native_config,
            "--export-gcode",
            "--output",
            str(output),
            str(slicer_input),
        ]
    if backend == "curaengine":
        return [
            executable,
            "slice",
            "-j",
            profile.native_config,
            "-l",
            str(slicer_input),
            "-o",
            str(output),
        ]
    raise GCodeToolError(f"Unsupported backend: {backend}")


def generated_gcode_candidate(output: Path, slicer_input: Path, existing_gcodes: set[Path]) -> Path | None:
    expected_by_input = output.parent / f"{slicer_input.stem}.gcode"
    if expected_by_input.is_file() and expected_by_input.resolve() != output.resolve():
        return expected_by_input
    generated = [
        path
        for path in output.parent.glob("*.gcode")
        if path.resolve() not in existing_gcodes and path.resolve() != output.resolve()
    ]
    if len(generated) == 1:
        return generated[0]
    return None


def build_slice_plan(args: argparse.Namespace, *, search_path: str | None = None, converted_input: Path | None = None) -> dict[str, Any]:
    profile = load_profile(Path(args.profile).expanduser())
    inspection = inspect_input(Path(args.input))
    if inspection.already_sliced_bambu:
        raise GCodeToolError("Input is already a sliced Bambu .gcode.3mf. Refusing to re-slice it.")

    backend = profile.backend if args.backend == "auto" else args.backend
    if backend not in PREFERRED_BACKEND_ORDER:
        raise GCodeToolError(f"Backend must be auto or one of: {', '.join(PREFERRED_BACKEND_ORDER)}.")
    executable = backend_path(backend, search_path=search_path)

    input_path = Path(inspection.path)
    slicer_input = converted_input or input_path
    if inspection.needs_stl_conversion and converted_input is None:
        slicer_input = Path(tempfile.gettempdir()) / f"{input_path.stem}.converted.stl"
    output = Path(args.output).expanduser().resolve()
    command = build_backend_command(
        backend=backend,
        executable=executable,
        slicer_input=slicer_input,
        output=output,
        profile=profile,
    )

    return {
        "dry_run": not args.execute,
        "backend": backend,
        "executable": executable,
        "command": command,
        "input": asdict(inspection),
        "output": str(output),
        "profile": asdict(profile),
        "conversion": {
            "required": inspection.needs_stl_conversion,
            "slicer_input": str(slicer_input),
            "note": "Requires trimesh at execution time." if inspection.needs_stl_conversion else "",
        },
    }


def convert_mesh_to_stl(input_path: Path, output_path: Path) -> None:
    try:
        import trimesh  # type: ignore
    except ImportError as exc:
        raise GCodeToolError(
            "trimesh is required to convert .ply/.glb/.gltf inputs to temporary STL. "
            "Install it in the active Python environment or provide .stl/.obj/.3mf directly."
        ) from exc

    loaded = trimesh.load(str(input_path))
    if getattr(loaded, "is_empty", False):
        raise GCodeToolError(f"Input mesh appears empty: {input_path}")
    if hasattr(loaded, "dump"):
        mesh = loaded.dump(concatenate=True)
    else:
        mesh = loaded
    if getattr(mesh, "is_empty", False):
        raise GCodeToolError(f"Input mesh appears empty after scene conversion: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(str(output_path), file_type="stl")


def execute_slice(args: argparse.Namespace, *, search_path: str | None = None) -> tuple[int, dict[str, Any]]:
    input_inspection = inspect_input(Path(args.input))
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gcode-slice-") as tmp:
        converted_input = None
        if input_inspection.needs_stl_conversion:
            converted_input = Path(tmp) / f"{Path(input_inspection.path).stem}.stl"
            convert_mesh_to_stl(Path(input_inspection.path), converted_input)
        plan = build_slice_plan(args, search_path=search_path, converted_input=converted_input)
        slicer_input = Path(plan["conversion"]["slicer_input"])
        existing_gcodes = {path.resolve() for path in output.parent.glob("*.gcode")}
        result = subprocess.run(plan["command"], check=False, capture_output=True, text=True)

    plan["returncode"] = result.returncode
    if result.stdout:
        plan["stdout_tail"] = tail_text(result.stdout)
    if result.stderr:
        plan["stderr_tail"] = tail_text(result.stderr)
    if result.returncode != 0:
        return result.returncode, plan
    if not output.is_file():
        candidate = generated_gcode_candidate(output, slicer_input, existing_gcodes)
        if candidate is None:
            plan["error"] = "Slicer exited successfully but did not create the requested output file."
            return 1, plan
        candidate.replace(output)
        plan["renamed_output_from"] = str(candidate)
    plan["generated"] = {"path": str(output), "size_bytes": output.stat().st_size}
    return 0, plan


def strip_gcode_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def parse_command(line: str) -> str:
    stripped = strip_gcode_comment(line)
    if not stripped:
        return ""
    first = stripped.split(None, 1)[0].upper()
    if re.fullmatch(r"[GMT]\d+(?:\.\d+)?", first):
        if "." in first:
            first = first.split(".", 1)[0]
        return first
    return first


def parse_numeric_tokens(line: str) -> dict[str, float]:
    stripped = strip_gcode_comment(line).upper()
    tokens: dict[str, float] = {}
    for key, value in re.findall(r"([A-Z])([-+]?(?:\d+(?:\.\d*)?|\.\d+))", stripped):
        try:
            tokens[key] = float(value)
        except ValueError:
            continue
    return tokens


def validate_gcode_file(path: Path, profile: GCodeProfile) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise GCodeToolError(f"G-code file does not exist: {resolved}")
    text = resolved.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    errors: list[str] = []
    warnings: list[str] = []
    unknown_commands: dict[str, int] = {}
    stats = {
        "lines": len(lines),
        "non_comment_lines": 0,
        "movement_commands": 0,
        "extrusion_moves": 0,
        "temperature_commands": 0,
    }

    if not text.strip():
        errors.append("G-code file is empty.")

    absolute_positioning = True
    x_min, x_max = profile.motion_bounds_mm["x"]
    y_min, y_max = profile.motion_bounds_mm["y"]
    z_min, z_max = profile.motion_bounds_mm["z"]
    for line_number, line in enumerate(lines, start=1):
        command = parse_command(line)
        if not command:
            continue
        stats["non_comment_lines"] += 1
        tokens = parse_numeric_tokens(line)

        if command not in SUPPORTED_GCODE_COMMANDS and not re.fullmatch(r"T\d+", command):
            unknown_commands.setdefault(command, line_number)

        if command == "G90":
            absolute_positioning = True
        elif command == "G91":
            absolute_positioning = False
            if "Relative positioning found; XYZ bounds validation is skipped while relative mode is active." not in warnings:
                warnings.append("Relative positioning found; XYZ bounds validation is skipped while relative mode is active.")

        if command in {"G0", "G1", "G2", "G3"}:
            stats["movement_commands"] += 1
            if command == "G1" and "E" in tokens:
                stats["extrusion_moves"] += 1
            if absolute_positioning:
                if "X" in tokens and not x_min <= tokens["X"] <= x_max:
                    errors.append(f"Line {line_number}: X={tokens['X']} is outside X motion range {x_min}..{x_max} mm.")
                if "Y" in tokens and not y_min <= tokens["Y"] <= y_max:
                    errors.append(f"Line {line_number}: Y={tokens['Y']} is outside Y motion range {y_min}..{y_max} mm.")
                if "Z" in tokens and not z_min <= tokens["Z"] <= z_max:
                    errors.append(f"Line {line_number}: Z={tokens['Z']} is outside Z motion range {z_min}..{z_max} mm.")
        if command in {"M104", "M109", "M140", "M190"}:
            stats["temperature_commands"] += 1

    if stats["movement_commands"] == 0:
        errors.append("No G0/G1/G2/G3 movement commands found.")
    if stats["extrusion_moves"] == 0:
        errors.append("No extrusion moves found.")
    if stats["temperature_commands"] == 0:
        errors.append("No nozzle or bed temperature commands found.")
    if unknown_commands:
        sample = ", ".join(f"{cmd} line {line}" for cmd, line in sorted(unknown_commands.items())[:12])
        warnings.append(f"Unknown or unsupported commands were left unchanged: {sample}.")

    return {
        "ok": not errors,
        "path": str(resolved),
        "profile": asdict(profile),
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def discover_main(args: argparse.Namespace) -> int:
    print_json(discovery_report(search_path=args.search_path))
    return 0


def inspect_main(args: argparse.Namespace) -> int:
    inspection = inspect_input(Path(args.input))
    payload = asdict(inspection)
    if args.json:
        print_json(payload)
    else:
        print(f"{payload['status']}: {payload['path']}")
    return 0


def slice_main(args: argparse.Namespace) -> int:
    if args.execute and args.dry_run:
        raise GCodeToolError("--execute and --dry-run cannot be used together.")
    if not args.execute:
        plan = build_slice_plan(args, search_path=args.search_path)
        plan["dry_run"] = True
        print_json(plan)
        return 0

    code, result = execute_slice(args, search_path=args.search_path)
    result["dry_run"] = False
    print_json(result)
    return code


def validate_main(args: argparse.Namespace) -> int:
    profile = load_profile(Path(args.profile).expanduser())
    result = validate_gcode_file(Path(args.gcode), profile)
    if args.json:
        print_json(result)
    else:
        status = "ok" if result["ok"] else "failed"
        print(f"Validation {status}: {result['path']}")
        for error in result["errors"]:
            print(f"error: {error}")
        for warning in result["warnings"]:
            print(f"warning: {warning}")
    return 0 if result["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Report installed slicer backends.")
    discover.add_argument("--search-path", help=argparse.SUPPRESS)
    discover.set_defaults(func=discover_main)

    inspect = subparsers.add_parser("inspect", help="Classify a mesh input before slicing.")
    inspect.add_argument("--input", required=True)
    inspect.add_argument("--json", action="store_true")
    inspect.set_defaults(func=inspect_main)

    slice_parser = subparsers.add_parser("slice", help="Build or run a slicer CLI command.")
    slice_parser.add_argument("--input", required=True)
    slice_parser.add_argument("--output", required=True)
    slice_parser.add_argument("--profile", required=True)
    slice_parser.add_argument("--backend", default="auto", choices=["auto", *PREFERRED_BACKEND_ORDER])
    slice_parser.add_argument("--dry-run", action="store_true", help="Print the planned slicer command without running it.")
    slice_parser.add_argument("--execute", action="store_true", help="Run the slicer command and write local .gcode.")
    slice_parser.add_argument("--search-path", help=argparse.SUPPRESS)
    slice_parser.set_defaults(func=slice_main)

    validate = subparsers.add_parser("validate", help="Statically validate generated G-code.")
    validate.add_argument("--gcode", required=True)
    validate.add_argument("--profile", required=True)
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(func=validate_main)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except GCodeToolError as exc:
        payload: dict[str, Any] = {"ok": False, "error": str(exc)}
        payload.update(exc.details)
        print_json(payload)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
