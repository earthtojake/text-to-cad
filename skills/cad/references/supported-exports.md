# Supported exports

Read this file when the user requests STL, 3MF, or native GLB output files from CAD geometry. For a `.step` file, run the model script (see `step-generation.md`) — a mesh door writes mesh formats only. For 2D DXF output, use the `$dxf` skill: a drawing is its own `<name>.py` declaring one `@dxf` function — one model per file, so a drawing never shares a script with a `@step` model.

## Policy

Validate the requested geometry and outputs. When a STEP is declared, inspect
that saved document; for a mesh-only model, check the returned native geometry
and review its mesh. A mesh image does not establish exact dimensions or topology.

Native GLB exports are ordinary glTF 2.0 binary files for external tools: Y-up, with one material per distinct part/face color. Do not confuse them with what the CAD Viewer renders from — the model's result tree in the store (`~/.cache/cadgen`: content-addressed exact-geometry components plus links to child trees), which every build writes and a mesh door never does.

## Declare the exports the model always has

Stack `@stl`, `@glb` or `@threemf` on the model for maintained mesh outputs.
For example, a project-root `bracket.py` can declare:

```python
from cadgen import build123d as bd
from cadgen import glb, step, stl


@step(out="STEP/bracket.step")
@stl(out="STL/bracket.stl")
@glb(out="GLB/bracket.glb")
def bracket():
    return bd.Box(40, 20, 6)


if __name__ == "__main__":
    bracket()
```

Running the script writes the STEP and declared meshes, and restores declared
outputs that were deleted or edited. Declarations live in the model's store
record. Export commands read saved documents and their appearance annotations,
never the model's output declarations. Mesh declarations alone create no sidecar.

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

For maintained draft/print variants, keep the model's stem in separate subfolders:

```python
@stl(out="STL/draft/bracket.stl", mesh_tolerance=8e-3)
@stl(out="STL/print/bracket.stl", mesh_tolerance=4e-4)
```

## Tool

One door per format — `cadgen stl build`, `cadgen 3mf build`, `cadgen glb build` — each taking a STEP/STP **document** and an optional output path:

```bash
cadgen stl build STEP/model.step                     # writes STEP/model.stl
cadgen stl build STEP/model.step meshes/model.stl    # one ad-hoc export
```

Export commands take saved STEP/STP documents, never scripts. Omitting OUT
writes one file beside the input with the requested extension, whether the
document is imported or generated. To build declared variants, run the model
script instead. An explicit OUT resolves against the working directory;
absolute paths and `~` are supported. For several formats:

```bash
cadgen stl build STEP/model.step
cadgen 3mf build STEP/model.step
cadgen glb build STEP/model.step
```

An unchanged export is reported `current`. `--force` re-exports the document;
it never rebuilds its source model. Missing cache data is compiled from the
document on demand. Rerun the model first if its source has changed.

Use an explicit OUT to choose another destination, including for imported files:

```bash
cadgen stl build path/to/imported.step meshes/imported.stl
```

A mesh door never writes a `.step` file. A generated model's STEP is the OUTPUT of `python <model>.py`; an imported model's STEP is already the file on disk.

### Carrying a clip into the GLB

GLB is the one mesh format with somewhere to put motion. `--animation` bakes a clip from the document sidecar's embedded animation into the file as glTF node animation, so an external viewer plays it:

```bash
cadgen glb build STEP/model.step meshes/model.glb --animation demo
cadgen glb build STEP/model.step meshes/model.glb \
  --animation '{"clip": "demo", "fps": 30, "seconds": 24, "start": 0}'
```

`fps` controls keyframe sampling. Translation and rotation are supported;
visibility and opacity tracks are rejected unless explicitly dropped.
Deforming tubes need the explicit morph-target option. Animated GLB requires
an explicit OUT so the clip does not overwrite the default static export.
STL and 3MF have no animation export. See [kinematics](kinematics.md) for clip
requests and supported channels, or [tube deformation](animation-deformation.md)
for morph export options.

## Rendering a mesh file

Each mesh format also has a `snapshot` verb, with the same `TARGET [OUT]` grammar `cadgen step snapshot` uses:

```bash
cadgen stl snapshot STL/bracket.stl tmp/bracket_mesh.png
cadgen 3mf snapshot 3MF/bracket.3mf tmp/bracket_3mf.png
cadgen glb snapshot meshes/bracket.glb tmp/bracket_glb.png
```

A mesh carries no CAD topology. Its snapshot door accepts `--display` for the
format-neutral `shaded`, `wireframe`, `transparent`, and `unshaded` modes, and
accepts `--render` for the photographic view. The two settings are separate:
`--display` cannot be combined with `--render`. Mesh doors do not have
`--focus`/`--hide`, `--kinematics`, or `--animation`/`--time`, and reject
`--mode section`; meshes have no canonical CAD occurrences, edges, kinematics,
or render-module clips for those controls to act on. `cadgen step snapshot`
refuses a mesh input and names the door that takes it.

For a mesh-only model, this is its required visual review. When a STEP is also
produced, review that document and render the mesh when tessellation or external
tool output is the question. Pure format conversion with unchanged geometry
follows the skip cases in [snapshot review](snapshot-review.md).

## Mesh tolerance

Mesh exports use the CAD Viewer's watertight tessellator on each component's
exact surfaces. Viewer detail can vary with its level of detail settings;
choose export tolerances for the output's requirements. Boundary vertices lie
on the STEP edge curves, and identical export inputs produce identical bytes.

Use these flags when the default mesh density is wrong for the part:

```bash
--mesh-tolerance FLOAT           # chord tolerance RELATIVE to each component's
                                 # bounding diagonal (default 1.5e-3)
--mesh-angular-tolerance FLOAT   # max normal spread across a triangle edge,
                                 # radians (default 0.35)
```

On a document export command, these flags select the tolerances for that export;
omitting them uses the defaults above. The command does not inherit the source
model's mesh declarations. On a model-script run, the same flags temporarily
override its declared tolerances. Use tighter values for curved-surface fidelity
and looser values when a coarser mesh meets the requirements. Linear tolerance
is relative, not an absolute deflection in millimetres.

## Workflow

1. For maintained outputs, declare the mesh decorators and run the model script.
2. For one-off exports, run the format command against the saved document.
3. Check the requested geometry and output quality; report the files and checks.

Example — the model declares its STL, and a coarse GLB is requested for review:

```bash
python bracket.py

cadgen glb build STEP/bracket.step tmp/bracket.glb \
  --mesh-tolerance 5e-3 \
  --mesh-angular-tolerance 0.5

python tmp/check_bracket.py  # check the saved STEP with read_scene
```

Report the actual output paths and checks performed, including the snapshot
review or its documented skip reason. Do not imply exact geometry was verified
from a mesh image alone.
