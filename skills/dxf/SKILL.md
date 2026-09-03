---
name: dxf
description: Generate, regenerate, and validate 2D DXF drawings from Python build123d sources. Use for DXF files, `.py` generators, @dxf model scripts, 2D profiles, outlines, templates, gaskets, panels, flat patterns, laser/plasma/waterjet cut layouts, and 2D drawing exports of CAD geometry.
---

# DXF generation and validation

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## Setup

This skill's commands are thin entrypoints over the `cadgen` distribution, which
carries the Python build runtime and the JavaScript it executes. Install it once:

```bash
python -m pip install -r requirements.txt
```

Drawings are build123d geometry, so a drawing build loads the CAD kernel like a
STEP build does (~2.5s cold; the warm daemon absorbs it on re-runs). Only
`cadgen dxf snapshot` additionally needs **Node 20 or newer on `PATH`** — it
meshes the flat pattern on demand through a bundled Node one-shot; a missing
`node` is reported at render time.

## Purpose

Create or modify 2D DXF drawings from natural-language requirements or from CAD
geometry, generate validated drawing artifacts, and return checked outputs. A
DXF drawing's source of truth is a Python file named `<name>.py` defining a
`@dxf` model function.

The build product IS the `.dxf` file: **every run writes the sibling
`<name>.dxf`** (the same contract a `@step` model has: source in, exchange file
out; `-o` renames it). There is no drawing package —
the CAD Viewer parses and meshes the `.dxf` itself, so the file you hand a
cutting service and the file the viewer renders are one and the same. The only
thing kept in the user-level cache is a small record that makes an unchanged
source a no-op. `--force` overrides it.

## The contract

**A `@dxf` function returns build123d 2D geometry. The engine writes the DXF.**
You never construct a document, name a file, or place an entity — the same
division of labor `@step` has.

```python
from cadgen import build123d as bd
from cadgen import dxf


@dxf
def gasket(hole_d: float = 4.5):
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
        bd.Circle(hole_d / 2, mode=bd.Mode.SUBTRACT)
    return cut.sketch          # bare shape -> the CUT layer


if __name__ == "__main__":
    gasket()
```

- **Bare shape** → one `CUT` layer. That is the whole contract for most drawings.
- **`{layer: shape}`** → named layers, when the drawing genuinely has more than
  one CAM operation (`CUT` / `ENGRAVE` / `SCORE`). A `Compound` whose children
  are all labelled means the same thing.
- **Text** is `bd.Text(...)` engraved OUTLINES on a marking layer, never a DXF
  `TEXT` entity: cut and marking toolchains consume geometry, and font rendering
  inside CAM is unreliable.
- **Geometry must lie in the XY plane.** A face taken from a solid sits at that
  solid's height; relocate it (`flatten.flatten_face(face)`, or
  `bd.Location((0, 0, -z)) * face`). The engine REFUSES off-plane geometry rather
  than silently writing its XY shadow.
- **Output bytes are a function of the geometry.** Layers are sorted by name and
  entities by geometric content, so an unchanged drawing rebuilds to an identical
  file, cold or warm, on any machine.

## The three DXF workflows

Copy the full generator template for the applicable workflow from
`references/generator-templates.md` when creating a new drawing.

1. **Drafted from scratch** (gaskets, panels, templates, cut layouts with no 3D
   model behind them): a `<name>.py` that builds sketches and returns them.

2. **Flat pattern of a generated STEP part**: a drawing script beside the model
   it derives from, with its OWN stem (one model per file — `bracket_drawing.py`
   beside `bracket.py`). Import the model and call it: inside a build, a
   decorated model returns its shape, and importing never builds:

   ```python
   from cadgen import dxf, flatten
   from bracket import bracket        # closure-tracked; importing never builds

   @dxf
   def bracket_drawing(kerf: float = 0.15):
       return flatten.flat_pattern(bracket(), coordinate=3.0, kerf=kerf)


   if __name__ == "__main__":
       bracket_drawing()
   ```

   The imported module and its own imports are recorded in the drawing's source
   closure, so editing the 3D part invalidates the drawing.

3. **Flat pattern of an imported STEP** (a `.step`/`.stp` with no Python source):
   read it with `cadgen.read_step`, not `build123d.import_step`. It records the
   file's content hash as a build INPUT, so replacing the vendor STEP makes the
   drawing stale on its own, with no `--force`; read it through build123d and the
   drawing stays "current" against a file that changed underneath it.

   ```python
   from pathlib import Path

   from cadgen import dxf, flatten, read_step

   _HERE = Path(__file__).resolve().parent

   @dxf
   def panel_flat(kerf: float = 0.15):
       panel = read_step(_HERE / "imported" / "vendor_panel.step")   # recorded input
       return flatten.flat_pattern(panel, coordinate=3.0, kerf=kerf)


   if __name__ == "__main__":
       panel_flat()
   ```

   **Never read a STEP this project generates.** Reading the `.step` a `@step`
   model writes is not a loop, it is a drawing whose input changes on every run of
   the model: the freshness gate can never say "current", every build is a full
   rebuild, and the flat pattern depends on what the last run left on disk. Keep
   source STEPs in an `imported/` directory beside the drawing, committed like any
   other input — input path and output path being different files is the whole
   rule. For a STEP this project DOES generate, use workflow 2 instead: import the
   model script and call it, which is traced properly and never touches an artifact.

One model per file: a source declaring both a `@step` and a `@dxf` model is
rejected — a drawing gets its own script. The viewer catalog is artifacts-only:
scripts never list; the `.dxf` the run writes is the entry the viewer renders.

## Use this skill when

Use this skill when the user asks for DXF files, 2D drawings, profiles, outlines,
templates, gaskets, panels, flat patterns, or cut layouts for laser, plasma,
waterjet, or CNC routing.

Use `$cad` for the 3D part or assembly a DXF derives from. Use `$sendcutsend` for
SendCutSend-specific upload preflight.

## Defaults

Use these defaults unless the user specifies otherwise:

- Units: millimeters. The engine sets them; a drawing never declares units.
- Geometry lives at 1:1 scale in the XY plane.
- Cut profiles close. Open contours belong on bend/engrave/reference layers —
  generation validation enforces this (see Validation).
- For CAD-backed parts, derive contours from the real topology with
  `cadgen.flatten` rather than redrawing them: `planar_faces` selects,
  `flatten_face` lays a face into XY exactly, `union_faces` fuses, and
  `flat_pattern` does all of it in one call. Hand-drawn parametric outlines only
  when there is no reliable 3D topology.
- Kerf / tool-radius compensation is `flatten.offset_profile(shape, amount)` or
  `flat_pattern(..., kerf=...)`; never hand-offset coordinates.
- **Curves stay curves.** The union and the offset are exact OCC operations, so a
  filleted corner exports as an `ARC` and a hole as a `CIRCLE`, kerf included. A
  profile that comes out as hundreds of short `LINE`s means something fell back
  to the sampled path — investigate rather than accept it.
- Layers carry intent: keep cut geometry and bend/fold lines on separate layers,
  and include "bend" in bend-layer names so downstream tools classify them as
  bends rather than cuts.
- DXF layers are drawing structure, not STEP part/assembly structure.

## Tool

```bash
python <drawing>.py [flags]      # its __main__ calls the @dxf model, which writes the sibling .dxf
cadgen dxf snapshot <drawing.dxf> <file.png>   # render it
```

**Running the script (its `__main__` call) is the only door.** There is no `cadgen dxf build`: a
`.dxf` has no derived state a command must materialize — the file IS the
product, the CAD Viewer parses it directly, and `dxf snapshot` meshes it on
demand. The script's own gate makes a rebuild cheap: an unchanged source whose
recorded `.dxf` still verifies is a no-op, and `--force` rebuilds anyway. The
bytes are a function of the drawing's GEOMETRY, so a cold run and a warm daemon
worker write the same file.

An imported `.dxf` needs nothing at all — hand it straight to snapshot or the
Viewer.

Use the active project Python interpreter; treat `python` as an interpreter
placeholder, and use `--help` for the full interface. Target paths resolve from
the command's current working directory; run from the workspace that owns the
artifacts with cwd-relative target paths. Keep a drawing generator in the same
directory as the geometry it derives from, named `<name>.py`.

Flags (a model script runs itself; there is no generation CLI):

- `-o`/`--output PATH` — write the drawing somewhere other than its declared target.
- `--force` — regenerate even when the recorded output is current.
- `--verbose`, `--json`, `--lock-timeout SECONDS`.

One script, one drawing: run each script you want built. Do not put output paths
in the `@dxf` function's return value; `out=` on the decorator is the only
place a drawing names its destination.

`cadgen dxf snapshot` renders a drawing's 3D flat pattern to a PNG still:

```bash
cadgen dxf snapshot path/to/imported.dxf review.png
cadgen dxf snapshot path/to/drawing.dxf review.png --camera top
```

It takes the `.dxf` document only — a model script is refused by name (run
`python <drawing>.py`, then snapshot the drawing it wrote). The command meshes
the flat pattern on demand through the bundled Node one-shot and
renders it through the shared snapshot CLI (`cadgen.snapshot_cli`) and the same
headless browser runtime every rendering skill uses — so geometry and materials
render identically to the CAD Viewer; the default `snapshot` theme differs from the
viewport only by dropping the grid, origin axis and shadows.

OUT — the second positional — is written exactly as given, with a relative path resolved against the
current working directory. The target is deleted before the render starts and the
finished image is written atomically, so: reuse one name while iterating (every read
is provably the render you just ran), name the iterations when you genuinely need to
compare two, and treat a missing file as the failure signal — there is never an older
image at the path to mistake for output. A directory (`tmp/` as OUT) is the
don't-care case and gets a generated timestamped name inside it, printed on the
`saved snapshot:` line.

Grammar: `cadgen dxf snapshot TARGET [OUT] [flags]`. Flags: `--mode view|list`,
`--camera`, `--theme`, `--size-profile`, `--width`/`--height`, `--job`,
`--view-labels`, `--debug`, `--json`. Theme settings live under one `--theme`,
mirroring the viewer's Theme tab; the default theme is `snapshot`, Workbench Light
without the ground grid, origin axis or shadows. The command has no `--display`,
and no selector, kinematics, section or exploded options at all — they are absent
from `--help` rather than refused at runtime, because a drawing carries no CAD
topology and display settings are CAD topology settings.

No CLI inspects an existing `.dxf`. For entity/layer checks read it with `ezdxf`
directly (it arrives with build123d), and `validate_dxf_file` for the drawing checks;
review geometry visually with `$cad-viewer`.

## Workflow

1. Convert the request into a short brief: outline dimensions, holes and slots, layers, units, output path, and validation targets.
2. Pick the workflow: drafted from scratch, flat pattern of a generated model (create and validate the 3D geometry with `$cad` first), or flat pattern of an imported STEP.
3. Write or edit the `<name>.py` source with meaningful dimensions as named parameters, reusing the model's geometry helpers instead of duplicating formulas.
4. Run each drawing script directly (`python <drawing>.py`); do not sweep directories.

```bash
python path/to/source.py
python path/to/source.py -o path/to/output.dxf
python path/to/source.py --force
```

5. Validate the generated DXF deterministically, then hand off and report.

## Viewer integration

The CAD Viewer catalogs `.dxf` files only (artifacts, never scripts) and is a static
visualization tool: it renders the `.dxf` that exists on disk (parsing and meshing it
itself — 2D line work for dimensioned drawings, a fold-able 3D flat pattern for cut
layouts) and never runs a script. A drawing with no `.dxf` yet simply does not appear
until its script has been run; regenerating after edits is likewise the script's job.
There is no in-viewer export. An imported `.dxf` renders directly with no artifact
management.

## Validation

Validation happens IN generation, not after: every `@dxf` build runs the drawing
checks on the document the engine just serialized, before anything is written, and
a build with error findings fails. The checks: cut-layer profiles must close
(polylines, circles, or chained line/arc loops), zero-length/degenerate entities are
rejected, exact duplicate geometry (double-cut risk) is rejected, explicitly unitless
documents are rejected, and an empty modelspace is rejected. Open geometry is allowed
only on bend/engrave/reference-intent layers (matched by name).

The same checks run post-hoc on any existing `.dxf` file — including one that
never came from a generator — through `cadgen.drawing_checks`:

```python
from cadgen.drawing_checks import validate_dxf_file

for finding in validate_dxf_file("path/to/file.dxf"):
    print(finding.render())
```

Beyond the built-in checks, verify requested dimensions with targeted `ezdxf` reads
(entity counts by layer, drawing extents, every dimension the user specified) against
the generated sibling `.dxf` (or the custom output path when one was requested), and
review geometry visually in the CAD Viewer:

```python
import ezdxf

doc = ezdxf.readfile("path/to/source.dxf")
msp = doc.modelspace()
cut = msp.query('*[layer=="CUT"]')
holes = msp.query('CIRCLE[layer=="CUT"]')
```

Report only checks that actually ran.

## Handoff

After creating or modifying DXF drawings, you must ALWAYS hand the explicit `.dxf`
file path(s) to `$cad-viewer` when that skill is installed and include its live
viewer link(s) in the final response. If `$cad-viewer` is unavailable or startup fails, report
that and rely on `ezdxf` checks instead of silently omitting the handoff.

Final responses should include generated files, returned viewer links, validation
actually run, and assumptions.
