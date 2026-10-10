# Supported exports

Read this file when the user requests STL, 3MF, or native GLB output files from CAD geometry. A `.step` file comes from running the model script (see `step-generation.md`) — a mesh door writes mesh formats only. 2D DXF output belongs to the `$dxf` skill: a drawing is its own `<name>.py` declaring one `@dxf` function.

Native GLB exports are ordinary glTF 2.0 binary files for external tools: Y-up, with one material per distinct part/face color. The CAD Viewer does not render from them: it draws the model's result tree in the store (`~/.cache/cadgen`: content-addressed exact-geometry components plus links to child trees), which every build writes and a mesh door never does.

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

A model's outputs are whatever its decorators declare, and STEP is one output kind, not the primary. A function decorated with `@stl`, `@glb` or `@threemf` alone — no `@step` — is a full model: the same tree and record in the store, the same build, the same parallel children, the same no-op when nothing changed, the same composition (`spacer()` inside another model's body links its tree like any child). It writes its declared meshes and no `.step` (and no sidecar), which suits a print-only part or a render asset. Its format's snapshot door renders it (`cadgen stl snapshot STL/spacer.stl tmp/spacer.png`), and `cadgen store why spacer.py` explains its freshness exactly as for a STEP model.

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

Maintained draft/print variants can keep the model's stem in separate subfolders:

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

Export commands take saved STEP/STP documents, never scripts, so a source change
reaches an export only after the model runs. Omitting OUT writes one file beside
the input with the requested extension, whether the document is imported or
generated; declared variants come from running the model script. An explicit OUT
resolves against the working directory; absolute paths and `~` are supported.
For several formats:

```bash
cadgen stl build STEP/model.step
cadgen 3mf build STEP/model.step
cadgen glb build STEP/model.step
```

An unchanged export is reported `current`. `--force` re-exports the document;
it never rebuilds its source model. Missing cache data is compiled from the
document on demand. An explicit OUT chooses another destination, including for
imported files:

```bash
cadgen stl build path/to/imported.step meshes/imported.stl
```

A mesh door never writes a `.step` file. A generated model's STEP is the OUTPUT of `python <model>.py`; an imported model's STEP is already the file on disk.

`cadgen glb build --animation CLIP` writes one of the document's clips into the
GLB as glTF animation, and needs an explicit OUT; STL and 3MF have no animation
export. See [exporting the clip inside a GLB](kinematics.md#exporting-the-clip-inside-a-glb).

## Rendering a mesh file

Each mesh format also has a `snapshot` verb, with the same `TARGET [OUT]` grammar `cadgen step snapshot` uses:

```bash
cadgen stl snapshot STL/bracket.stl tmp/bracket_mesh.png
cadgen 3mf snapshot 3MF/bracket.3mf tmp/bracket_3mf.png
cadgen glb snapshot meshes/bracket.glb tmp/bracket_glb.png
```

A mesh carries no CAD topology. Its snapshot door accepts `--display solid`
(the default) and `--display render` for the photographic view. Inline JSON and
JSON files use the grouped display object (`camera`, `surfaces`, `lighting`,
`background`, `floor`, `grid`, `axes`). Omitted groups inherit the preset.
`edges`, `clip`, `exploded`, the `xray`, `hidden-line` and `wireframe` presets
and the `hidden`/`off` surface styles are STEP-only and are refused by name.
Mesh doors do not have
`--focus`/`--hide`, `--kinematics`, or `--animation`/`--time`, and reject
`--mode section`; meshes have no canonical CAD occurrences, kinematics,
or sidecar clips for those controls to act on. `cadgen step snapshot`
refuses a mesh input and names the door that takes it.

The picture is the scene the CAD Viewer draws for the same file, built by the same code:
an STL or a 3MF is its objects in their colours, and a GLB is its own glTF scene (nodes,
skins, morph targets and authored materials), so `--display render` shows the finish the
file authored. A GLB's clips play in the viewer; its snapshot is the file at rest.

## Mesh tolerance

Mesh exports write the same meshes the CAD Viewer draws: OCCT's mesh of each
component's exact surfaces, at the export's tolerances. Viewer detail can vary
with its level of detail settings; an export's tolerances are its own. Faces that
meet share their boundary vertices, and identical export inputs produce identical
bytes.

These flags set the mesh density:

```bash
--mesh-tolerance FLOAT           # chord tolerance RELATIVE to each component's
                                 # bounding diagonal (default 1.5e-3)
--mesh-angular-tolerance FLOAT   # max normal spread across a triangle edge,
                                 # radians (default 0.35)
```

On a document export command, these flags select the tolerances for that export;
omitting them uses the defaults above. The command does not inherit the source
model's mesh declarations. On a model-script run, the same flags temporarily
override its declared tolerances — every declaration's, including one that sets
its own (flag > declaration > `@step` > default): the declared meshes are re-cut
at the flag's values for that run, and the next run without the flags restores
them. `--json` results report the effective pair, the defaults included.

Linear tolerance is relative, not an absolute deflection in millimetres, and is
refused above `0.05` (a twentieth of the bounding diagonal — past that the mesh
no longer follows the part). For an absolute chord deviation of X mm on a part
whose bounding diagonal is D mm, pass X/D: 0.1 mm on a 200 mm part is `5e-4`.
Angular tolerance is refused above `1.5708` (π/2, a quarter turn between
neighbouring facets).

Neither may be finer than cadgen meshes: linear tolerance at least `5e-5`,
angular tolerance at least `0.05` radians. That is past any display or print
need, and finer settings take minutes per curved face rather than seconds. The
same bounds apply to `mesh_tolerance=` and `mesh_angular_tolerance=` on a
decorator, and a value outside them is refused before anything builds.

A face no mesher can cover (typically a sliver a boolean left, narrower than the
chord tolerance) never fails the export: the part is written without it, and the
result's `warnings` name it, for example `#o1.2 pin: 1 face (f3) could not be
meshed, so pin.stl has a hole in place of it: it is not watertight`. Repairing
the face in the model, or a finer `--mesh-tolerance`, closes the hole.
