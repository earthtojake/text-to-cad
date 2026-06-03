# Supported exports

Read this file when the user requests STL, 3MF, or native GLB output from CAD geometry. Read `dxf.md` for DXF output, because DXF uses a separate `gen_dxf()` source contract.

## Policy

STL, 3MF, and native GLB are mesh sidecars, not substitutes for STEP. Generate and validate STEP first, then export requested sidecars from the same `scripts/step` run. Do not treat sidecar renders as CAD validation; inspect the STEP, verify the primary STEP/STP with CAD `scripts/snapshot` when snapshot review applies, and return `$cad-viewer` viewer links for every generated or modified supported artifact.

Native GLB sidecars are ordinary glTF 2.0 binary files for external tools: Y-up, meter-scaled, and free of the CAD Viewer `STEP_topology` extension. Do not confuse them with the hidden `.<name>.step.glb` CAD Viewer topology artifact.

## Tool

Use `scripts/step` with a generated Python source:

```bash
python scripts/step path/to/model.py \
  --stl meshes/model.stl \
  --3mf meshes/model.3mf \
  --glb meshes/model.glb
```

When a generator exists, use the generator form. Use direct STEP/STP targets only when the generator is unavailable or the user explicitly identifies that file as the target:

```bash
python scripts/step --kind part path/to/model.step \
  --stl meshes/model.stl \
  --3mf meshes/model.3mf \
  --glb meshes/model.glb
```

Sidecar paths must be relative `.stl`, `.3mf`, or `.glb` paths and are resolved beside the STEP output.

## Mesh tolerance

The default mesh density is `0.02` linear deflection and `0.05` angular deflection.

Use these flags when the default mesh density is wrong for the part:

```bash
--mesh-tolerance FLOAT
--mesh-angular-tolerance FLOAT
```

Use tighter tolerances for small curved parts or visual fidelity. Use looser tolerances for large simple geometry when file size matters.

## Workflow

1. Generate STEP from `gen_step()` with the requested sidecar flag(s).
2. Run facts/planes/positioning inspection on the STEP.
3. Return the STEP, requested sidecar files, and `$cad-viewer` viewer links for every generated or modified supported artifact when available.

Example:

```bash
python scripts/step models/bracket.py \
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

CAD Viewer:
- STEP: http://127.0.0.1:4178/?dir=/absolute/project/models&file=bracket.step
- STL: http://127.0.0.1:4178/?dir=/absolute/project/models&file=meshes/bracket.stl
- GLB: http://127.0.0.1:4178/?dir=/absolute/project/models&file=meshes/bracket.glb

Validation:
- STEP geometry validated; STL/3MF/native GLB generated as requested sidecars.
- Primary STEP/STP snapshot packet run/skipped and why.
```
