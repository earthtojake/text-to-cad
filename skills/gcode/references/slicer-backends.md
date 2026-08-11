# Slicer Backends

Use real slicer CLIs for mesh-to-G-code work. Do not rely on Bambu Studio as the default backend for this skill.

## Backend Order

1. `orcaslicer`
2. `prusa-slicer`
3. `curaengine`

If no preferred backend is installed, install OrcaSlicer first instead of treating the missing slicer as a user-facing blocker. On macOS:

```bash
brew install --cask orcaslicer
```

After installation, rerun `scripts/gcode_tool.py discover`. The helper checks `PATH`, backend-specific environment variables, and common macOS app bundle locations such as `/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer`.

`scripts/gcode_tool.py discover` checks PATH and backend-specific environment variables:

- `ORCASLICER_BIN`
- `PRUSASLICER_BIN`
- `CURAENGINE_BIN`

Bambu Studio may also be reported as available but not preferred. It is intentionally excluded from default backend selection because the local Bambu CLI export path has previously crashed during `.gcode.3mf` generation.

## Profile Expectations

Every slice needs a wrapper profile JSON. The wrapper must include:

- `backend`: one of `orcaslicer`, `prusa-slicer`, or `curaengine`.
- `native_config`: absolute path to the primary native slicer config/profile file.
- `machine.bed_size_mm`: `[width, depth]` in millimeters.
- `machine.z_height_mm`: maximum Z travel in millimeters.
- `machine.motion_bounds_mm`: optional per-axis motion limits for native start/end G-code that intentionally moves outside the printable area.
- `filament.type`, `filament.nozzle_temp_c`, and `filament.bed_temp_c`.

The wrapper is not a complete slicer profile. The native config is authoritative for detailed printer, process, and filament settings.

For OrcaSlicer profiles split across native machine, process, and filament JSON files, add:

- `native_settings`: string or list of absolute paths passed to `--load-settings`.
- `native_filaments`: string or list of absolute paths passed to `--load-filaments`.

If `native_settings` is omitted, `native_config` is passed as the only setting file.

## Command Shapes

For OrcaSlicer:

```bash
OrcaSlicer --load-settings machine.json\;process.json --load-filaments filament.json --outputdir /tmp/out --slice 0 input.stl
```

For PrusaSlicer:

```bash
prusa-slicer --load profile.ini --export-gcode --output output.gcode input.stl
```

For CuraEngine:

```bash
CuraEngine slice -j profile.json -l input.stl -o output.gcode
```

Always run a dry-run first and inspect the emitted command before `--execute`.

## Input Handling

- `.stl`, `.obj`, and unsliced `.3mf` are passed directly to the selected slicer.
- `.ply`, `.glb`, and `.gltf` are converted to temporary STL with `trimesh` during `--execute`.
- Sliced Bambu 3MF files containing `Metadata/plate_N.gcode` are already print jobs; do not re-slice them.
- `.step`, `.stp`, `.dxf`, `.svg`, `.urdf`, and `.sdf` are out of scope for this skill. `inspect_input` rejects them with a `remediation` object (`skill`, `reason`, `next_step`) that names the owning skill and the exact conversion command; both `inspect` and `slice` surface it in their JSON error payload.
  - `.step`, `.stp`: export an STL sidecar with `$cad` (`python scripts/step --kind part <input> --stl <output>.stl`).
  - `.dxf`, `.svg`: no 2D-to-mesh path exists; model the solid in `$cad`, or use `$sendcutsend` when the part is a flat cut rather than a print.
  - `.urdf`, `.sdf`: slice the per-link meshes the description references, regenerating them from CAD with `$cad` when stale.

## Source Links

- FullControl procedural G-code context: https://github.com/FullControlXYZ/fullcontrol
- bambox Bambu packaging reference only: https://pypi.org/project/bambox/
- trimesh mesh format support: https://trimesh.org/formats.html
- CuraEngine slicing background: https://github.com/Ultimaker/CuraEngine/wiki/Slicing
