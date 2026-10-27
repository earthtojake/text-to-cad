---
name: dxf
description: Generates, regenerates and validates 2D DXF drawings from Python build123d models, exported by cadgen. Use for DXF files, `.py` drawing scripts, 2D profiles, outlines, templates, gaskets, panels, flat patterns, laser/plasma/waterjet cut layouts, and 2D drawing exports of CAD geometry. Opens and visually reviews existing DXF files in the CAD Viewer.
license: MIT
---

# DXF generation and validation

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

## Setup

Run cadgen through the `cadgen` command its installation writes, so this skill's commands
share one installation, and its engine server, with the CAD app's:

- `cadgen` below means `cadgen +0.8.1` (`~/.local/bin/cadgen +0.8.1` where `~/.local/bin` is not on your PATH)
- `python` below means `cadgen +0.8.1 run`

If `cadgen` is not on your PATH, or it says 0.8.1 is not installed, run
`uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.1 cadgen doctor` once,
outside any sandbox or with its permission: it installs cadgen, registers it, writes the
`cadgen` command and starts the engine. With the CAD app's server running, nothing else
needs the sandbox's permission: it starts the engine and holds it. Without it, a sandboxed
shell cannot start the engine; when a command says no engine is running, run `cadgen server`
outside the sandbox once.

`cadgen doctor <skill-dir>` reports the installation in use and checks that it is
the one this skill pins, that the CAD kernel loads, and whether the engine every
build runs in is running, starting it when none is; use it for installation or kernel load errors.

Drawings are build123d geometry, so a drawing builds in the engine's warm worker
like any model: the first run of a script loads the CAD kernel (a few seconds),
and later runs reuse it.

## Purpose

Create or modify 2D DXF drawings from natural-language requirements or from CAD
geometry, export validated DXF files, and return checked outputs. A drawing's source
of truth is a Python file named `<name>.py` defining a parameterless `@model` function
that returns planar geometry.

**A drawing is a model.** It builds as any `$cad` model does: `python <name>.py`
rebuilds it in the engine, prints its document's `id:` and page, and writes nothing.
The DXF is exported from that document, by build123d's own exporter, once the drawing
checks pass: `cadgen export <id> drawing.dxf`. A drawing that calls a part model
(`bracket()` in its body) builds that part in the same run. The CAD Viewer and
`cadgen snapshot` read the `.dxf` itself, so the file you hand a cutting service,
the file the viewer draws and the file a snapshot renders are one and the same.

## The contract

**A drawing is a `@model` function that takes no parameters and returns build123d 2D
geometry on z=0: a sketch, a face, wires or edges. `cadgen export` writes the DXF.**
You never construct a document, name an entity, or write a file from the model.

```python
import build123d as bd
from cadgen import model

HOLE_D = 4.5


@model
def gasket():
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
        bd.Circle(HOLE_D / 2, mode=bd.Mode.SUBTRACT)
    return cut.sketch          # one shape: the CUT layer


if __name__ == "__main__":
    gasket()                   # decoration only declares: this call builds it
```

```bash
python src/gasket.py                       # prints id: and view:
cadgen export "$ID" DXF/gasket.dxf         # ID: the id: line it printed
```

- **One shape** is one layer, `CUT`. That is the whole contract for most drawings.
- **A layer per part** when the drawing genuinely has more than one CAM operation:
  return a `Compound` of labelled children, each label its layer
  (`profile.label, marks.label = "CUT", "ENGRAVE"`). Children sharing a label share
  a layer, and several shapes make one part of a layer as
  `bd.Compound([a, b], label="ENGRAVE")`. A layer name may not be empty or hold any
  of `<>/\":;?*|=` and a backtick.
- **Planar means 2D, on z=0.** The export refuses a document holding a solid
  (`bracket is 3D: a DXF is drawn from 2D geometry a model returns`) and an edge with
  any point more than 1e-6 mm off z=0, by its element name. A face taken from a solid
  sits at that solid's height; relocate it (`flatten.flatten_face(face)`, or
  `bd.Location((0, 0, -z)) * face`).
- **No parameters.** Dimensions are module constants (`HOLE_D = 4.5`) or constants
  imported from the part the drawing derives from; a different drawing is a
  different `@model` function.
- **Text** is `bd.Text(...)` engraved OUTLINES on a marking layer, never a DXF
  `TEXT` entity: cut and marking toolchains consume geometry, and font rendering
  inside CAM is unreliable.
- **Output bytes are a function of the geometry.** Layers are written in name order
  and entities in an order of their content, so an unchanged drawing exports an
  identical file, on any machine, and the file is replaced only when its bytes
  change.
- **Drawings delivered after every change** go in an `exports.py` beside them that
  imports each drawing and calls `export(drawing, path)` (the model function itself,
  or the handle its call returns):

  ```python
  # src/exports.py
  from pathlib import Path

  from cadgen import export

  from gasket import gasket

  ROOT = Path(__file__).resolve().parent.parent

  if __name__ == "__main__":
      export(gasket, ROOT / "DXF/gasket.dxf")
  ```

## The three DXF workflows

Copy the full template for the applicable workflow from
`references/generator-templates.md` when creating a new drawing.

1. **Drafted from scratch** (gaskets, panels, templates, cut layouts with no 3D
   model behind them): a `<name>.py` that builds sketches and returns them.

2. **Flat pattern of a part this project models**: a drawing script beside the
   model it derives from, with its OWN stem (`bracket_drawing.py` beside
   `bracket.py`). Import the model and call it, exactly as an assembly composes a
   child: importing never builds, and inside the drawing's run the call builds the
   part in the same run and returns its geometry.

   ```python
   from cadgen import flatten, model

   from bracket import bracket        # the model: importing builds nothing

   KERF = 0.15


   @model
   def bracket_drawing():
       return flatten.flat_pattern(bracket().shape, coordinate=3.0, kerf=KERF)   # the top face's height


   if __name__ == "__main__":
       bracket_drawing()
   ```

   An edit to the part re-runs the drawing's body on its next run; an edit the
   part's body does not reach (a comment, another model) re-runs nothing.

3. **Flat pattern of an imported STEP** (a `.step`/`.stp` with no Python source):
   read it with `read_step`, or convert it once (`cadgen export vendor_panel.step
   vendor_panel.xbf`) and read the xbf with `read_xbf`, which is faster. Like every
   file a run reads, it is an input: replacing the vendor file re-runs the drawing.

   ```python
   from pathlib import Path

   from cadgen import flatten, model, read_step

   HERE = Path(__file__).resolve().parent

   KERF = 0.15


   @model
   def panel_flat():
       panel = read_step(HERE / "vendor" / "vendor_panel.step")   # an input, by its bytes
       return flatten.flat_pattern(panel, coordinate=3.0, kerf=KERF)


   if __name__ == "__main__":
       panel_flat()
   ```

   **Never read a file this project exports.** Keep source STEPs in a `vendor/`
   directory beside the drawing, committed like any other input. For a part this
   project models, use workflow 2: import the model and call it.

One model per file is the recommendation, and a drawing gets its own script. A
file MAY declare several models (two drawings, or a drawing beside a part's
`@model`): `python <file>.py` builds every one its `__main__` block calls, each with
its own id. A drawing composes models, never the reverse.

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
- Cut profiles close. Open contours belong on bend/engrave/reference layers:
  the drawing checks enforce this (see Validation).
- For CAD-backed parts, derive contours from the real topology with
  `cadgen.flatten` rather than redrawing them: `planar_faces` selects,
  `flatten_face` lays a face into XY exactly, `union_faces` fuses, and
  `flat_pattern` does all of it in one call. Hand-drawn parametric outlines only
  when there is no reliable 3D topology.
- Kerf / tool-radius compensation is `flatten.offset_profile(shape, amount)` or
  `flat_pattern(..., kerf=...)`; never hand-offset coordinates.
- **Curves stay curves.** The union and the offset are exact OCC operations, and
  each edge is written as one entity, so a filleted corner exports as an `ARC` and a
  hole as a `CIRCLE`, kerf included. A profile that comes out as hundreds of short
  `LINE`s means something fell back to the sampled path: investigate rather than
  accept it.
- Layers carry intent: keep cut geometry and bend/fold lines on separate layers,
  and name bend layers with `bend` or `fold` so downstream tools classify them as
  bends rather than cuts.
- DXF layers are drawing structure, not STEP part/assembly structure.

## Tool

```bash
python path/to/drawing.py                                   # builds every model its __main__ calls
cadgen export "$ID" path/to/drawing.dxf                     # writes the DXF, running the drawing checks
cadgen snapshot path/to/drawing.dxf review.png              # draws it
cadgen snapshot path/to/drawing.dxf review.png --display '{"appearance": "dark"}'
```

**Running the script is the only way to build a drawing, and exporting it the only
way to write its DXF.** `python <drawing>.py` takes no options and writes nothing; it
prints each model's report (`built src/gasket.py::gasket cold in 2.29s: ...`), its
`id:` and its page, and exits 1 when a body raises. `cadgen export` exits 2 when the
export refuses the drawing (3D, off the plane, a failed drawing check), naming which.
An imported `.dxf` needs nothing at all: hand it straight to a snapshot or the viewer.

Paths on the command line, and those `export` takes from Python, resolve from the
working directory; anchor them on `__file__` in an `exports.py`. Keep a drawing
script in the same directory as the geometry it derives from, named `<name>.py`.

`cadgen snapshot` draws a drawing the way the CAD Viewer's drawing pane does: whole,
from above, fitted with a margin, in the pens the file declares (an entity with no
pen of its own takes the paper's ink), on light paper or, with
`--display '{"appearance": "dark"}'`, dark. `--size-profile`, `--width` and
`--height` size it; `--camera` takes a plan view (below), `--annotation` ink on the
sheet and `--measurements` dimensions; every other flag is refused by name, and what
it does not draw (points, hatch patterns, images) is named in a warning. OUT is
written exactly as given and must be a `.png`; check the exit status before reading
it, since a refused or failed snapshot writes nothing.

A Quick Edit prompt from a drawing carries a packet (inline JSON or a
`.snapshot.json` path; save inline JSON to a file first) whose views are plan-view
`camera` windows (`{"position": [x, y, d], "target": [x, y, 0], "up": [0, 1, 0],
"orthographicHalfHeight": h}`, looking straight down) and whose `annotation` marks
are in drawing coordinates, on the sheet. Draw what the person saw, each window with
their ink and dimensions on it, before editing:

```bash
cadgen snapshot --job tmp/panel.snapshot.json                     # every view, into the paths its jobs name
cadgen snapshot panel.dxf tmp/view.png --annotation tmp/panel.snapshot.json --camera authored
```

No CLI inspects an existing `.dxf`. For entity/layer checks read it with `ezdxf`
directly (it arrives with build123d), and `validate_dxf_file` for the drawing
checks; review geometry visually (see [Show the model](#show-the-model)).

## Workflow

1. Convert the request into a short brief: outline dimensions, holes and slots, layers, units, output path, and validation targets.
2. Pick the workflow: drafted from scratch, flat pattern of a modelled part (create and validate the 3D geometry with `$cad` first), or flat pattern of an imported STEP.
3. Write or edit the `<name>.py` source with meaningful dimensions as named constants, reusing the model's geometry helpers instead of duplicating formulas.
4. Run each drawing script directly (`python <drawing>.py`); do not sweep directories. Then export each drawing to its DXF:

```bash
python path/to/source.py
cadgen export "$ID" path/to/drawing.dxf
```

5. Validate the exported DXF deterministically, then hand off and report.

## Show the model

Show the user each model you create or change, and any model or file they ask to see.
A file you export is a download: give its path, do not open it.
Snapshots and validation don't replace this. Never screenshot the viewer to confirm your
own work; review with `cadgen snapshot`.

- If your tools include `cad_show` (your host may prefix it), call it with the model's id
  or the file's absolute path, and follow its description for when to call it again.
  The other tools depend on the host. A host that draws CAD cards or tabs (Claude
  Desktop, the Codex app) also has `cad_view`, which reads what the user selected, and
  `cad_screenshot`, which shows you what they see, both of a card or tab that is open, for
  when they ask about it. A text host (Claude Code in a terminal, `codex exec`) draws
  nothing: its `cad_show` opens the model's page in the user's browser and answers with
  the URL to give them, and it has no view to read. `cad_inspect`, `cad_snapshot` and
  `cad_export` are on every host. Call only the tools you have, and never say a card
  shows a model when your host drew none.
- Otherwise give the user the page's link once: a model's page is the `view:` line its
  run prints. For a file, run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --json FILE [FILE ...]
  ```

  The command ensures this installation's engine, registers each file and prints
  its page, `/<id>`, then exits. Read each file's `url` from `documents` in its one
  JSON line (never guess the port); the URL carries its token query. A page follows
  every later run of its model and every rewrite of its file, so share it once.
  Return that link to the user. If it fails to launch, say so.

A drawing script's model has a page, but it shows a flat face in the 3D viewer, with no
pens, layers or entity refs. The drawing a person wants is the exported `.dxf`, which the
viewer opens as a read-only 2D drawing with its layers (it never runs drawing scripts):
show the `.dxf` when they ask to see the drawing, and give its path otherwise. Drag to pan, wheel/pinch to zoom, double-click to fit. Its
Select, Pencil, Shapes and Measure feed Quick Edit, whose prompt names what the person
picked as references into the drawing by entity HANDLE: `panel.dxf#h2F` is the
modelspace entity whose handle is `2F` (`doc.entitydb["2F"]` in ezdxf); anything a
block reference draws is named by its INSERT, and a dimension is one entity. The
prompt's chip reads it as the entity's type and layer ("Circle on CUT"). Measurements
are in the unit `$INSUNITS` declares ("units" when it declares none).

## Validation

Validation happens IN the export, not after: every DXF export runs the drawing
checks on the document it is about to write, and an error refuses the file, naming
the check (`[error] open_cut_profile: cut layer 'CUT' has segment endpoints that do
not close a loop ...`). The checks: units are set, nothing is drawn twice (an exact
duplicate is a double cut), no entity has zero length, every cut profile closes
(polylines, circles, and chains of lines, arcs and splines), and something is drawn.
Open geometry is allowed only on a layer whose name's words make it a bend (`bend`,
`fold`), engraving (`engrave`, `etch`) or reference layer (`ref`, `note`,
`construction`, `dim`, `center`, `hidden` and the like).

The same checks run on any existing `.dxf` file, including one that never came
from a model:

```python
from cadgen.engine.export.dxf import validate_dxf_file

for finding in validate_dxf_file("path/to/file.dxf"):
    print(finding.render())
```

Beyond the built-in checks, verify requested dimensions with targeted `ezdxf` reads
(entity counts by layer, drawing extents, every dimension the user specified)
against the exported `.dxf`, and review geometry visually in the CAD Viewer:

```python
import ezdxf

doc = ezdxf.readfile("path/to/drawing.dxf")
msp = doc.modelspace()
cut = msp.query('*[layer=="CUT"]')
holes = msp.query('CIRCLE[layer=="CUT"]')
```

Report only checks that actually ran.

## Handoff

Give the path of every `.dxf` you created or changed, and show it when the person asks to
see the drawing ([Show the model](#show-the-model)).
Report any failure explicitly.

Final responses should include generated files, returned viewer links, validation
actually run, and assumptions.
