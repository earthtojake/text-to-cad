# Supported exports

Read this file when the user requests STL, 3MF, or native GLB output files from CAD geometry. For a `.step` file, use `scripts/gen --write` (see `step-generation.md`) — `scripts/export` writes mesh formats only. For 2D DXF output, use the `$dxf` skill; DXF uses a separate `gen_dxf()` contract in a dedicated `<name>.dxf.py` drawing generator (never inside a `.step.py`).

## Policy

STL, 3MF, and native GLB are mesh exports, not substitutes for STEP. Validate the primary CAD geometry first, then export the requested formats. Do not treat exported mesh renders as CAD validation; inspect and snapshot the primary model per the standard workflow.

Native GLB exports are ordinary glTF 2.0 binary files for external tools: Y-up, meter-scaled, and free of the CAD Viewer `STEP_topology` extension. Do not confuse them with the CAD Viewer render artifact — the component-GLB package directory at `<folder>/__cadgen__/models/<name>.step/` (an `assembly.json` descriptor plus a `components/` dir of content-addressed GLBs) — which `scripts/gen` builds and `scripts/export` never writes.

## Tool

`scripts/export` takes one model target — a `gen_step()` Python source or an imported STEP/STP file — and one or more mesh format flags (`--stl`, `--3mf`, `--glb`). The model is built once per run (the generator runs once), so every requested format comes from identical geometry; exports can never be stale.

```bash
python scripts/export path/to/model.step.py --stl --3mf --glb
```

Each format flag takes an optional output path. Without a path, the file is written beside the model as `<name>.<ext>`. A relative path resolves beside the model; an absolute path is used as-is:

```bash
python scripts/export path/to/model.step.py \
  --stl meshes/model.stl \
  --3mf meshes/model.3mf \
  --glb meshes/model.glb
```

When a generator exists, export from the generator. Pass an imported STEP/STP file directly only when no generator exists or the user explicitly identifies that file as the target; its part/assembly kind is inferred automatically:

```bash
python scripts/export path/to/imported.step --stl --3mf
```

`scripts/export` never writes a `.step` file. A generated model's STEP comes from `scripts/gen <name>.step.py --write` in the generation run; an imported model's STEP is already the file on disk.

## Mesh tolerance

The default mesh density is `0.02` linear deflection and `0.05` angular deflection.

Use these flags when the default mesh density is wrong for the part:

```bash
--mesh-tolerance FLOAT
--mesh-angular-tolerance FLOAT
```

Use tighter tolerances for small curved parts or visual fidelity. Use looser tolerances for large simple geometry when file size matters.

## Workflow

1. Validate the model per the standard workflow (generate, inspect, snapshot).
2. Run `scripts/export` with the requested format flag(s).
3. Report the exported files.

Example — write the STEP during generation, then mesh exports from the same generator:

```bash
python scripts/gen models/bracket.step.py --write

python scripts/export models/bracket.step.py \
  --stl meshes/bracket.stl \
  --glb meshes/bracket.glb \
  --mesh-tolerance 0.2 \
  --mesh-angular-tolerance 0.2

python scripts/inspect refs models/bracket.step --facts --planes --positioning
```

## Reporting

```text
Files:
- STEP: /absolute/project/models/bracket.step
- STL: /absolute/project/models/meshes/bracket.stl
- GLB: /absolute/project/models/meshes/bracket.glb

Validation:
- CAD geometry validated; STL/3MF/native GLB written as requested exports.
- Primary STEP/STP snapshot packet run/skipped and why.
```
