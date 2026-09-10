# Supported exports

Read this file when the user requests STL, 3MF, or native GLB output files from CAD geometry. For a `.step` file, run the model script (see `step-generation.md`) — a mesh door writes mesh formats only. For 2D DXF output, use the `$dxf` skill: a drawing is its own `<name>.py` declaring one `@dxf` function — one model per file, so a drawing never shares a script with a `@step` model.

## Policy

STL, 3MF, and native GLB are mesh exports, not substitutes for STEP. Validate the primary CAD geometry first, then export the requested formats. Do not treat exported mesh renders as CAD validation; inspect and snapshot the primary model per the standard workflow.

Native GLB exports are ordinary glTF 2.0 binary files for external tools: Y-up, with one material per distinct part/face color. Do not confuse them with what the CAD Viewer renders from — the model's result tree in the store (`~/.cache/cadgen`: content-addressed exact-geometry components plus links to child trees), which every build writes and a mesh door never does.

## Declare the exports the model always has

A mesh output that belongs to the model belongs in the model. Stack `@stl`, `@glb` or `@threemf` on the `@step` function and every build produces them:

```python
from cadgen import build123d as bd
from cadgen import glb, step, stl


@step(out="STEP/bracket.step")
@stl(out="STL/bracket.stl")
@glb
def bracket():
    return bd.Box(40, 20, 6)


if __name__ == "__main__":
    bracket()
```

`python models/bracket.py` then writes the STEP **and** the declared meshes, and rewrites any of them that were deleted or edited — no separate export step (a declared output is part of the model's freshness gate). The declarations are recorded in the document's sidecar, which is where the mesh doors read them from.

## A model with no STEP

A model's outputs are whatever its decorators declare, and STEP is one output kind, not the primary. A function decorated with `@stl`, `@glb` or `@threemf` alone — no `@step` — is a full model: the same tree and record in the store, the same build, the same parallel children, the same no-op when nothing changed, the same composition (`spacer()` inside another model's body links its tree like any child). It writes its declared meshes and no `.step` (and no sidecar). Use it for a print-only part or a render asset; there is no requirement to write a STEP. Review it with its format's snapshot door (`cadgen stl snapshot STL/spacer.stl tmp/spacer.png`); `cadgen store why spacer.py` explains its freshness exactly as for a STEP model.

```python
from cadgen import build123d as bd
from cadgen import stl


@stl(out="STL/spacer.stl", mesh_tolerance=4e-4)
def spacer():
    return bd.Cylinder(6, 3) - bd.Cylinder(2.5, 3)


if __name__ == "__main__":
    spacer()
```

Stacking order stays neutral: add `@step` above or below later and the same declarations ride along; the `.step` then joins the outputs.

A decorator `out=` is the one intentional exception to native path semantics: on `@stl`, `@glb` and `@threemf` — exactly as on `@step` — a relative `out=` resolves relative to the SCRIPT, not the working directory. That is what makes a project relocatable: the declaration travels with the model and produces the same layout whatever directory the script is run from. Ad-hoc OUT arguments on the doors are cwd-relative instead, because they are one-shot and never persisted.

Declare the same format more than once at distinct targets for draft/print variants:

```python
@stl(out="STL/bracket_draft.stl", mesh_tolerance=8e-3)
@stl(out="STL/bracket_print.stl", mesh_tolerance=4e-4)
```

## Tool

One door per format — `cadgen stl build`, `cadgen 3mf build`, `cadgen glb build` — each taking a STEP/STP **document** and an optional output path:

```bash
cadgen stl build STEP/model.step                     # every declared @stl variant
cadgen stl build STEP/model.step meshes/model.stl    # one ad-hoc export
```

Doors take documents, never scripts: `python model.py` is the one source door, and a door handed a `.py` says so. Omitting the output is the normal form: it produces exactly what the model declared, read from the document's sidecar. A document that declares no variants of that format has nothing to produce — declare `@stl` on the model and rerun the script, or name an explicit OUT. An explicit OUT takes the same native path semantics as every other door: a relative path resolves against the current working directory, an absolute path is used as given, and `~` expands. Ask for several formats by running several doors — each writes only its own format:

```bash
cadgen stl build STEP/model.step
cadgen 3mf build STEP/model.step
cadgen glb build STEP/model.step
```

An output the model already has at the requested tolerances is reported `current` and not rewritten. `--force` re-exports it anyway; it never rebuilds the model itself — rerun `python <script>` for that. The door reads the document's tree by the file's content hash and compiles one from the bytes if the store has none; whether the document is behind its script is not the door's question (`cadgen store why`), so no document is ever refused.

An imported STEP/STP file declares nothing, so give it an explicit OUT; its part/assembly kind is inferred automatically:

```bash
cadgen stl build path/to/imported.step meshes/imported.stl
```

A mesh door never writes a `.step` file. A generated model's STEP is the OUTPUT of `python <model>.py`; an imported model's STEP is already the file on disk.

## Rendering a mesh file

Each mesh format also has a `snapshot` verb, with the same `TARGET [OUT]` grammar `cadgen step snapshot` uses:

```bash
cadgen stl snapshot STL/bracket.stl tmp/bracket_mesh.png
cadgen 3mf snapshot 3MF/bracket.3mf tmp/bracket_3mf.png
cadgen glb snapshot meshes/bracket.glb tmp/bracket_glb.png
```

A mesh carries no CAD topology, so these render shaded solid and do not HAVE `--focus`/`--hide`, `--display`, `--kinematics`, `--animation`/`--time`, or `--mode section` — a mesh has no occurrences, CAD edges, kinematics, or clips for those to act on, so they are absent from the command rather than refused by it. `cadgen step snapshot` refuses a mesh input and names the door that takes it.

This is a review of the EXPORT, not of the model. Snapshot validation of the primary STEP is still what the required workflow means; render the mesh when the question is about the mesh (tessellation density, a tolerance change, what an external tool will receive).

## Mesh tolerance

Mesh exports tessellate each component's exact surfaces with the same watertight tessellator the CAD Viewer renders with, at the same default tolerances — an export matches what renders, boundary vertices lie on the exact STEP edge curves, and repeated exports are byte-identical.

Use these flags when the default mesh density is wrong for the part:

```bash
--mesh-tolerance FLOAT           # chord tolerance RELATIVE to each component's
                                 # bounding diagonal (default 1.5e-3)
--mesh-angular-tolerance FLOAT   # max normal spread across a triangle edge,
                                 # radians (default 0.35)
```

Either flag overrides what the declaration and the model set, for that run only. Use tighter tolerances for visual fidelity on curved parts; use looser tolerances for large simple geometry when file size matters. The linear tolerance is relative (scale-free), not an absolute deflection in millimetres.

## Workflow

1. Validate the model per the standard workflow (build, inspect, snapshot).
2. Declare the exports the model should always have; run the model script.
3. For anything ad hoc, run the format door for each requested format.
4. Report the exported files.

Example — the model declares its STL, and a one-off coarse GLB is requested beside it:

```bash
python models/bracket.py

cadgen glb build models/bracket.step meshes/bracket_preview.glb \
  --mesh-tolerance 5e-3 \
  --mesh-angular-tolerance 0.5

cadgen step inspect refs models/bracket.step --facts --planes --positioning
```

## Reporting

```text
Files:
- STEP: /absolute/project/models/bracket.step
- STL: /absolute/project/models/STL/bracket.stl
- GLB: /absolute/project/models/meshes/bracket_preview.glb

Validation:
- CAD geometry validated; STL/3MF/native GLB written as requested exports.
- Primary STEP/STP snapshot packet run/skipped and why.
```
