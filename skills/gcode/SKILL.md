---
name: gcode
description: Generate, inspect, dry-run, and statically validate plain FDM `.gcode` from 3D mesh files by orchestrating real slicer CLIs. Use when Codex needs to slice `.stl`, `.obj`, unsliced `.3mf`, `.ply`, `.glb`, or `.gltf` into printer-profiled G-code, discover local slicer backends, inspect whether a mesh is slice-ready, or validate generated G-code before any printer-specific handoff.
---

# G-code

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill for plain `.gcode` generation from mesh files. It is printer-agnostic and never uploads, starts, or packages print jobs.

## Workflow

1. Confirm the input is a supported mesh: `.stl`, `.obj`, unsliced `.3mf`, `.ply`, `.glb`, or `.gltf`.
2. Require an explicit printer/profile wrapper JSON. Do not invent real-printer profiles.
3. Discover slicer backends when the backend is unknown:

```bash
python scripts/gcode_tool.py discover
```

4. Inspect the input:

```bash
python scripts/gcode_tool.py inspect --input path/to/model.stl --json
```

5. Dry-run the slicer command before executing:

```bash
python scripts/gcode_tool.py slice \
  --input path/to/model.stl \
  --output /tmp/model.gcode \
  --profile path/to/profile.json \
  --backend auto \
  --dry-run
```

6. Execute only after the dry-run command and profile are appropriate:

```bash
python scripts/gcode_tool.py slice \
  --input path/to/model.stl \
  --output /tmp/model.gcode \
  --profile path/to/profile.json \
  --backend auto \
  --execute
```

7. Validate the generated G-code:

```bash
python scripts/gcode_tool.py validate \
  --gcode /tmp/model.gcode \
  --profile path/to/profile.json \
  --json
```

## CAD Viewer Handoff

After completing G-code work that creates or modifies a plain `.gcode`, you must ALWAYS hand the explicit file path to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); the preview is diagnostic only and does not replace this skill's static validation. If `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Profile Contract

Every slice requires a wrapper profile JSON with an absolute native slicer profile path:

```json
{
  "backend": "orcaslicer",
  "native_config": "/absolute/path/to/native-slicer-profile",
  "machine": {
    "name": "Example Printer",
    "bed_size_mm": [180, 180],
    "z_height_mm": 180,
    "motion_bounds_mm": {
      "x": [0, 180],
      "y": [0, 180],
      "z": [0, 180]
    }
  },
  "filament": {
    "type": "PLA",
    "nozzle_temp_c": 220,
    "bed_temp_c": 65
  }
}
```

The wrapper supplies validation bounds and backend selection. `machine.motion_bounds_mm` is optional; omit it for the default `0..bed_size` and `0..z_height` bounds, or set it from a native printer profile when start/end G-code intentionally uses safe wipe/purge positions outside the printable area. The native slicer profile remains the source of detailed process, printer, and filament behavior.

For OrcaSlicer, use `native_settings` and `native_filaments` when the real profile is split across machine, process, and filament JSON files. Keep `native_config` as an absolute path to the primary native profile for compatibility:

```json
{
  "backend": "orcaslicer",
  "native_config": "/absolute/path/to/machine-or-process.json",
  "native_settings": [
    "/absolute/path/to/machine.json",
    "/absolute/path/to/process.json"
  ],
  "native_filaments": [
    "/absolute/path/to/filament.json"
  ],
  "machine": {
    "name": "Example Printer",
    "bed_size_mm": [180, 180],
    "z_height_mm": 180
  },
  "filament": {
    "type": "PLA",
    "nozzle_temp_c": 220,
    "bed_temp_c": 65
  }
}
```

## Backends And Inputs

Preferred slicer backend order is `orcaslicer`, `prusa-slicer`, then `curaengine`. Prefer installing OrcaSlicer when no preferred backend is available; on macOS use `brew install --cask orcaslicer` and then rerun `discover`. The helper checks both `PATH` and the usual `/Applications/OrcaSlicer.app` cask location. Bambu Studio may be reported by discovery as available but is not preferred because its CLI export path has shown macOS instability.

Pass `.stl`, `.obj`, and unsliced `.3mf` directly to the slicer. Convert `.ply`, `.glb`, and `.gltf` to temporary STL at execution time with optional `trimesh`; if `trimesh` is unavailable, ask the user to install it or provide `.stl`, `.obj`, or unsliced `.3mf`.

Reject `.step`, `.stp`, `.dxf`, `.svg`, `.urdf`, and `.sdf` in v1. Use the existing CAD/render workflows to convert those to a supported mesh format before using this skill.

Read `references/slicer-backends.md` when backend behavior, profile expectations, or source links matter.

## Validation

Always validate generated G-code before handing it to printer-specific workflows. The validator checks for non-empty content, temperature commands, movement commands, extrusion moves, XYZ bounds, and unknown command warnings.

Read `references/gcode-validation.md` when interpreting validation output or deciding whether a warning is acceptable.

## Bambu Boundary

This skill generates plain `.gcode` only. It does not create Bambu `.gcode.3mf` archives and does not contact printers. For Bambu upload/start workflows, hand off the validated plain `.gcode` to `$bambu-labs`. Let `$bambu-labs` choose the printer-specific LAN handoff, such as an A1 Mini template project or an explicitly enabled bambox project package.
