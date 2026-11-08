---
name: cad
description: Creates and edits parametric CAD parts, assemblies and 2D profiles as Python build123d models that text-to-cad's server builds and the CAD Viewer shows live; exports STEP, STL, 3MF, GLB, DXF and xbf files on request; resolves prompt references, measures geometry, checks whether a part can be machined, cut and bent, molded or printed, and articulates or animates assemblies. Use for 3D CAD modeling, editing a model script (any change to a part's or assembly's `.py`), organizing a CAD project, exporting or converting CAD files, DXF files, flat patterns, gaskets and laser or waterjet cut layouts, Quick Edit prompts, mechanisms, and explode or showcase animations. Opens and reviews existing XBF, STEP/STP, STL, 3MF, GLB and DXF files in the CAD Viewer. Not for the robot and world descriptions the robot-simulation skill writes.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# CAD modeling and inspection

A model is a Python function; running its script rebuilds it in text-to-cad's warm server, and
the page the person has open updates. Files are exports, made when asked.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **Create or edit a part or assembly** | The project's model script, or a new one ([below](#write-a-model-and-run-it)); a part the request says how to make is designed for that process from the first line ([Design for the process](#design-for-the-process)). | [Models](references/model-contract.md), [build123d](references/build123d-modeling.md), [positioning](references/positioning.md) |
| **Organize a CAD project** | The project's existing layout. | [Project layout](references/project-layout.md) |
| **Export STEP, STL, 3MF, GLB or xbf** | `cad model export <id> <file>`. | [Exports](references/exports.md) |
| **Make a 2D profile, flat pattern or DXF** | A model that returns 2D geometry on z=0, then `cad model export <id> part.dxf`. | [2D profiles and DXF](references/2d-profiles-and-dxf.md) |
| **Use a vendor STEP, an xbf or a scan in a model** | `step.read`, `xbf.read` or `stl.read` in the body. | [Inputs](references/model-contract.md#inputs) |
| **Resolve a reference from a prompt** | `cad model inspect <id> '<ref>'`. | [References](references/inspection-and-validation.md#references) |
| **Measure or check geometry** | A check script that calls the model. | [Inspection](references/inspection-and-validation.md) |
| **See a model, a view or a pose** | `cad model snapshot <id> out.png`. | [Snapshots](references/snapshot-review.md) |
| **Articulate a mechanism** | build123d joints in the body, then `cad.build123d`. | [Kinematics](references/kinematics.md) |
| **Explode, reveal or showcase a model** | `cad.build123d`'s `animation()` in the body. | [Animation](references/animation.md) |
| **Open an existing XBF, STEP/STP, STL, 3MF, GLB or DXF** | Show it to the user. | [Show the model](#show-the-model) |
| **Can it be machined, cut and bent, molded or printed?** | The part's model or file, its material and its process. | [Can it be made?](#can-it-be-made) |

## Setup and paths

Run the `cad` command (`~/.local/bin/cad` where it is not on your PATH; `cad.exe` on Windows). If
it is missing, install text-to-cad, outside a sandbox or with its permission:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. If the CAD app was
only just added, its server may still be starting: try again for up to a minute first. `cad doctor
--check` explains any other failure, changing nothing; `cad doctor` repairs what it reports.

One server runs for the installation: the first run starts it, every run and every
command goes through it, and it serves the viewer. `cad status` lists its workers
and the documents it holds; `cad stop` stops it.
A build cut off by the shell's time limit keeps running in the server; run the same
command again and it waits for that build and replays it (`cad status` shows it).
Give a cold build of a large model the shell tool's longest timeout, or run it in the
background.

Build every model with `cad run`, exactly like `uv run`: the same options and the same script
header, with nothing to set up. cad is pinned to this computer's release and its integrations come
from the script's imports (`import build123d` is the build123d integration), so a header names only
the script's own packages, never a version of cad:

```python
# /// script
# dependencies = ["pandas>=2"]
# ///
```

A one-off dependency is `--with`; a script inside a Python project runs with the project's
dependencies and lock. A run that stops on an import or a requirement says what to change in one
line. [Environments](references/environments.md) has the details: `--with`, projects and their locks,
private indexes and the network.

Command-line paths, and the paths `step.read`, `xbf.read`, `stl.read` and a type's `export`
take, are relative to the working directory, as are a model's own file reads. Anchor
them on `__file__` in code that must run from any folder.

## Write a model and run it

A part or an assembly is a function with no parameters, decorated `@model` (or with its
file decorators, never both), that returns a build123d shape. Its dimensions are the
arguments of a plain helper function, and each configuration is a `@model` of its own, with
its own id and page; constants several models share live in a module they import. A call
builds it and returns its document: a handle with `.id`, `.url`, `.shape` (the built shape)
and `.export(...)`. For example, `src/bracket.py`:

```python
import build123d as bd
from cad import model


def bracket_body(width, thickness, bore):
    body = bd.Box(width, 20, thickness)
    hole = bd.Cylinder(bore / 2, thickness)
    body = body - hole
    body.label = "bracket"
    body.color = "#4a6fa5"
    return body


@model
def bracket():
    return bracket_body(40, 6, 8)


@model
def bracket_wide():
    return bracket_body(60, 6, 8)


if __name__ == "__main__":
    bracket()
    bracket_wide()
```

```bash
cad run src/bracket.py
```

```text
built src/bracket.py::bracket cold in 2.61s: bodies 1 run; 6 misses, 0 hits; body 0.01s, names 0.00s, document 0.00s
  parts 1 · bounds 40 × 20 × 6 mm · joints 0 · sequences 0
  id: 0dc50a92-a21f-5895-a245-ebdeb5352f3b
  view: http://127.0.0.1:54360/0dc50a92-a21f-5895-a245-ebdeb5352f3b?token=...
built src/bracket.py::bracket_wide warm in 0.01s: bodies 1 run; 6 misses, 0 hits; body 0.01s, names 0.00s, document 0.00s
  parts 1 · bounds 60 × 20 × 6 mm · joints 0 · sequences 0
  id: 966d03a5-7b43-5bed-b75c-eb67d56c72d2
  view: http://127.0.0.1:54360/966d03a5-7b43-5bed-b75c-eb67d56c72d2?token=...
```

Each call the script's `__main__` makes prints how its model built, the delta under it
(parts, bounds, joints and sequences), its document's `id:` and its page, `view:` (the
handle's `.id` and `.url`). An unchanged rerun prints `took ... nothing ran` instead. Give the
user the page once ([Show the model](#show-the-model)) and use the id for every command
after it. The id comes from the
script's path and the function's name, or the script's folder and an explicit `@model(name="...")`,
so it is the same run after run, and the open page follows every run. A model's name is its identity
within its namespace, the function's name by default, `name=` gives it another. The namespace
is the script's folder; two explicit names in it must differ.

- **Running the script is the rebuild.** It writes no file. The server's warm worker for
  the script replays every operation an edit did not reach, so a comment re-runs nothing
  and a dimension edit re-runs what reads it
  ([what a run runs](references/model-contract.md#what-a-run-runs)). Decoration only
  declares: keep the calls under `if __name__ == "__main__":` so other scripts can import
  the models.
- **`@memo` marks stages, never parts.** The server already replays every kernel call, so
  mark only a function holding seconds of kernel work that an edit elsewhere leaves
  alone, such as a whole sub-assembly stage; never a part, never a helper called many
  times ([`@memo`](references/model-contract.md#memo-marks-stages)).
- **An assembly calls its parts.** Its body calls each part model and composes its shape
  (`plate().shape`), places and labels it, and returns a `Compound`. Each child builds in
  the same run and keeps its own document and id. Running a child's script alone leaves the assemblies that
  use it as they were: run the assembly.
- **`import build123d as bd`, and use it attribute-style** (`bd.Box`). The import is lazy:
  the kernel loads on first use, in the worker. `from build123d import Box`, or a
  module-level `bd.Color(...)` or `bd.Align` default, loads it at that line instead.
- **Colours are sRGB**, as a person picks them: `part.color = "#4a6fa5"` (`"#4a6fa5cc"` with
  alpha). `part.color` is build123d's: it takes no 0-255 integers (OCCT's `Color out`), which
  `paint` does. Import `metals` from `bd_materials`; assign a native material with
  `part.material = metals.aluminum()`
  ([colour and materials](references/build123d-modeling.md#colour-and-materials)).
- **Inputs** are `step.read`, `xbf.read` and `stl.read` in the body, and any file its
  Python opens, each tracked by its bytes. The clock, environment variables and
  randomness are not seen: a body is a function of its code and its inputs. Compose
  project models by calling them, never by reading a file the project exported.
- **References** to faces, edges and parts come from `cad model inspect <id> [ref]`, and the
  body picks the same element with build123d's selectors; verify with a snapshot when in
  doubt ([references](references/inspection-and-validation.md#references)).
- **A shape with no function** (a notebook cell, a REPL) is handed over:
  `model(shape, name="plate")` returns the same handle, and no command builds it again.
- **The server never reruns code.** A restart reopens every document from the server's
  cache, as last built. When the cache holds no file of one (deleted by hand, or never
  saved), the page, `cad model inspect <id>` and `cad_show` print the command that brings it
  back (`cad run src/bracket.py`). Run it.
- Model units are millimetres, +Z up.
- An image without a scale sets no fit dimension, and a drawing's units, projection and
  revision decide how its numbers read. A missing or conflicting dimension that changes
  the result is the person's to settle; a value chosen in its place is an assumption.

## Files, when asked

A file is an action on the document the server holds, never part of the model: no code
change and no rebuild, written at once. It holds what the document held when it was
written, so a change made after it is in the file only once it is written again. Write one
when the person asks for it:

```bash
cad model export "$ID" STEP/bracket.step STL/bracket.stl GLB/bracket.glb 3MF/bracket.3mf
```

A project with standing deliverables gets an `exports.py` that imports its models and
calls `model.export(x, path, ...)` on each (`from cad import model`; `x` a model call's handle); running it rewrites every deliverable
([exports](references/exports.md)). An export takes a document and its destinations,
and nothing else: a posed file is a model that returns the posed assembly
(`posed(arm(), "folded")`), and a part on its own is the part's own model. A DXF is the export of a
model that returns 2D geometry, a profile or a flat pattern, and a solid is refused
([2D profiles and DXF](references/2d-profiles-and-dxf.md)). An STL or 3MF for printing a part with fits takes
`--tolerance MM`, about a tenth of its smallest clearance ([print tolerance](references/exports.md#print-tolerance)).

The xbf, text-to-cad's own document, is Save As: export one only to share a model without its
code, or to compose it in another project with `xbf.read`. A restart needs none: the
server's own cache reopens every document it built, as last built. A vendor STEP is
converted to an xbf once
(`cad step export vendor/motor.step vendor/motor.xbf`) and read with `xbf.read`, many
times faster than parsing the STEP.

## Projects built around exported files

A project can instead revolve around its exported files, but only when the person asks to
iterate on the exported file itself or the project already does: an `exports.py`, a consumer
that reads the files (a robot description, a slicer, a drawing pipeline), or a 0.7-era
layout, whose runs wrote files. The loop is three steps. The script writes the file on each
run, by a file decorator in place of `@model` (`@step("../STEP/bracket.step")`, relative to
the script), or `exports.py` or `cad <type> export` follows the run. Show the file's page, not
the model's: it follows the file on disk, updating when a run rewrites the file.
Verification reads the file: `cad <type> snapshot` or `cad <type> inspect` with its path, or
`step.read` in a check. The costs keep the default the default: each iteration pays the
file's translation and the page's re-read, a STEP parsed again; a file names no model, so a
ref picked on its page has no `made_by` and a Quick Edit from it no way back into the code;
and the model's page stays the better place to look while editing.
[Exports](references/exports.md#model-page-or-file-page) tables the triggers and costs.

## Prompt references and inspection

A reference such as `0dc50a92-a21f-5895-a245-ebdeb5352f3b#bracket/face 7` names geometry
in a document by the server's own names: the document (a model's id, or a file's
absolute path), `#`, a part or an assembly by the labels on its way from the root
(`hand/finger.2` is the second component labelled `finger` in `hand`), then, after a
slash, one element by its name (`f:`, `e:`, `v:`) or its number (`face 7`). The CAD
viewer copies them. When a prompt names one, resolve it with `cad <type> inspect`:

```bash
cad model inspect "$ID" "bracket/face 7"
```

It answers in JSON what the ref names, placed where its occurrence stands: an element's
canonical `ref`, `kind`, `ordinal` and `name`, the kernel's facts (a face's `area`,
`centroid`, `surface`, `box`, `radius`; an edge's length and endpoints) and `made_by`,
the function, file and line of the code that made it; a part's or an assembly's volume
and mass. Edit the code `made_by` names, or pick the element in the body with
build123d's selectors (`body.faces().sort_by(bd.Axis.Z)[-1]`) matching those facts. A
ref resolves in the document as the latest run left it; one that names nothing, or
several things where it names one, is refused with what it could mean. The grammar is
in [references](references/inspection-and-validation.md#references).

A Quick Edit prompt names its document under `File:` (a path or an id), selected
entities under `References:`, and a snapshot packet as inline JSON or a `.snapshot.json`
path. Save inline JSON to a temporary `.snapshot.json`, and draw the view the person
drew their ink in, ink included:

```bash
cad model snapshot "$ID" tmp/quick_edit.png --annotation tmp/bracket.snapshot.json --camera authored
```

Inspect supplied annotations before editing. Without annotations, the captured view is
optional context; render it when useful to the request. After editing, run the script and
draw it again to check the change
([annotations and Quick Edit views](references/snapshot-review.md#annotations-and-quick-edit-views)).

A reference into a file that is not a document names what the viewer picked in it, in
that file's own terms (none is a ref `cad <type> inspect` resolves):

| File | Reference | Means |
| --- | --- | --- |
| URDF, SRDF, SDF | `/work/arm/arm.urdf#upper_arm` | the link `upper_arm` |
| GLB | `/work/out/model.glb#n12` | the glTF node `nodes[12]` (0-based, the file's own index) |
| 3MF | `/work/out/plate.3mf#o2.1` | the 2nd `<build><item>`'s 1st `<component>` (1-based); `#o3` is the 3rd build item |
| STL | the file alone, on `File:` | one mesh: nothing in it is picked |
| DXF | `/work/DXF/panel.dxf#h2F` | the modelspace entity whose handle is `2F`; what a block reference draws is named by its INSERT |

## Check each change

After every run, read its line and the delta under it (parts, bounds, joints, sequences): a
contradiction with what you intended is fixed before anything else. Then check the change the way it
can be checked:

| The change | Check it with |
| --- | --- |
| A number the person gave: a bound, a distance, a volume | An assert inside the model's body on what the geometry measures, or `cad model inspect`; never by restating the constant, never by code after the call in the script |
| A number the design implies: a clearance, a fit, a mass | A check script that calls the model ([below](#check-scripts)) |
| New parts, placements, colours, a mechanism | The snapshots it takes to judge it: usually one from the angle that shows the change, more only when a view leaves the question open, a posed one for a mechanism state |
| A reference the prompt names | `cad model inspect "$ID" '<ref>'` ([Prompt references](#prompt-references-and-inspection)) |
| A 2D profile or DXF | `cad model export` (it runs the drawing checks), then an `ezdxf` read and `cad dxf snapshot` of the file ([check a drawing](references/2d-profiles-and-dxf.md#check-a-drawing)) |
| Any change to the geometry of a part whose process is known | Its process's check, with the same flags as before: the script's `Check:` line (`cad model dfm "$ID" ...`, [Design for the process](#design-for-the-process)); an error is fixed before anything else, a new warning fixed or reported |

```bash
cad model snapshot "$ID" tmp/review.png
cad model snapshot "$ID" tmp/top.png --camera top --display hidden-line
cad model snapshot "$ID" tmp/open.png --pose open
```

A snapshot draws the document as the viewer does, rendered by OCCT, and writes nothing but the PNG.
Its options say how the picture is drawn: camera (`--camera top`), display, grid, pose and size
([snapshots](references/snapshot-review.md)). For a large assembly, isolate the parts the edit
touched or hide what covers them, instead of drawing the whole model.

- A number is never read off a picture: a snapshot shows arrangement and appearance, not dimensions.
- A check that fails or cannot decide has shown nothing about the design.
- A retry that leaves out or shrinks a specified feature (a fillet skipped, a radius reduced) builds a
  different design from the one asked for.

### Check scripts

A check is a Python script that calls the model and measures what it returns, so it tests the model
as it is now. Write one when the person asks for a dimension, a fit or a mass, or when the change is
numeric and the number matters.

Copy `world_parts` and `find_part` from
[Opening geometry](references/inspection-and-validation.md#opening-geometry) into the check
first. They accumulate parent placements; raw `.leaves` do not.

```python
from cad.build123d import closest_points

from assembly import assembly

kit = assembly().shape                       # rebuilt (replayed), returned as a tree
plate = find_part(kit, "plate")               # copied into world coordinates
post = find_part(kit, "standoff_left")        # refuses missing or repeated labels
print(plate.bounding_box().size)              # the envelope: not a hole's diameter or a wall's thickness
print(closest_points(plate, post).distance)   # 0: the standoff sits on the plate
```

- In an assembly, nothing interferes when `overlap_volume` is 0 for every pair of solids apart from
  fits named on purpose, and a part meant to rest on another touches it when their `closest_points`
  distance is 0. Both describe the parts as built, not a pose
  ([measurements](references/inspection-and-validation.md#measurements)).
- `cad model inspect "$ID" <assembly label>` weighs an assembly (the label it was given, which is also
  the root name `inspect "$ID"` prints): each part's volume times its material's density, and the
  parts that have no material.

## Can it be made?

Check that a part can be machined, cut and bent, molded or printed, and say what to change where it
cannot. A part whose process the request names is designed for it ([below](#design-for-the-process));
a review picks the process, reads its reference and runs its check, and when the person is choosing
between processes checks each one the same way:

| Process | Reference | Check with |
| --- | --- | --- |
| CNC milling and turning | [CNC machining](references/manufacturing-cnc.md) | `--process cnc --material M`, with `--axes`, `--turning`, `--tools` |
| Sheet cutting and bending | [Sheet metal](references/manufacturing-sheet-metal.md) | `--process sheet --material M --thickness T`, with `--bend-radius`, `--k-factor`; a cut file `cad dxf dfm` |
| Injection molding | [Injection molding](references/manufacturing-injection-molding.md) | `--process molding --pull z --material M`, with `--cavities` |
| 3D printing: FDM, SLS, SLA/DLP, MJF, metal PBF | [3D printing](references/manufacturing-printing.md) | `--process printing --technology T`, with `--material`, `--build-volume`, `--layer-height` |

```bash
cad model dfm "$ID" --process cnc --material aluminum --tools 3,6,10
```

`cad model dfm` checks a model's document by its id; `cad step dfm` (and `xbf`, `stl`, `threemf`,
`glb`) a file. A mesh is checked for molding and printing only: CNC and sheet need the STEP. A STEP
needs `--process`, a model or an xbf takes the one its parts declare, and `cad dxf dfm` checks a cut
file as sheet. A SendCutSend order is the sendcutsend skill's; slicing a print, the print3d skill's.

### Design for the process

A request that says how the part is made -- machined, milled or turned; sheet metal, bent, folded,
laser- or waterjet-cut; injection molded; 3D printed, or a printer, a resin, a filament or a cutting
service named -- makes the process part of the design, not a review at the end. A material alone names
none (6061 is machined, cast or bent); a thickness with a metal ("2 mm steel") is sheet.

1. **Before the first line**, read the process reference's *Design it* and build its limits in (walls
   drafted along the pull, a bend's inside radius, a pocket's corner radii, walls at the material's
   minimum), so the first check passes or nearly.
2. **Record the process in the model**: each part's material with its process (`part.material =
   metals.aluminum(process=machined())`), so `cad model dfm "$ID"` alone checks it for what it says it
   is, and the shop's flags in the module docstring, so every edit and the next session run the same
   check:

   ```python
   """A motor mount, CNC milled from 6061 on 3 axes.

   Check: cad model dfm "$ID" --tools 3,6,10
   """
   ```

3. **After every run**, that check, on the part's own id. An error (a limit the part breaks as drawn)
   is fixed before anything else: its hint says what to change, its ref where. A warning is fixed when
   the fix leaves what was asked for as it was (a corner radius, a draft angle, a bend relief), else
   reported with its number. A retry that drops or shrinks a feature the person specified builds another
   design: say so instead. Repeat until no error remains.
4. **At the hand-off**, say the process, that the rules are general practice (no shop's limits), the
   material the check judged with, the findings left and the rules not evaluated. With no process
   named, build what was asked and never add draft, reliefs or tool radii to it: say which process the
   design suits if one is evident, and offer the check.

### Evidence and a shop's limits

Check the exact file the shop gets, or the model's document it was exported from, never a script or a
render alone. Never infer alloy, resin, strength or stock thickness from a render's colour: pass what
the person gave, and report the check's own assumption when they gave none. Never invent a
measurement. The checks are general practice, no shop's: for a named shop, compare
`measurements.<family>` with its published limits, citing its page, or use its skill (the sendcutsend
skill for SendCutSend). What the person knows of their shop goes in as options, and a specification
they supply overrides every rule.

### Read the result

- **Exit 1**: a finding is an error, or a family was not measured (`measurement_failed`: the rest is
  still reported; never read it as "no findings"). **Exit 0** is not an approval: warnings remain, and
  a rule `not_evaluated` is never a pass. **Exit 2**: the command itself was refused; fix the command,
  not the part.
- **Count by rule, never by findings**: several failures at one ref are one finding, and a rule shows at
  most eight refs. The counts are the last line's digest (`FAILED <id>: ... failed: molding.draft_min x10,
  ...`: errors only) and, for each rule in `measurements.rules.failed`, its outcome's `failures`.
- Resolve a finding's ref with `cad model inspect "$ID" '<ref>'` or `cad step inspect part.step '<ref>'`.
- `--candidates` ranks pulls or orientations and judges nothing: check again with the one chosen.
- **A redesign** gets the same check with the same flags on the new revision: compare
  `measurements.rules.failed` before and after, matching failures by position (`xyz`), since face
  numbers change with an edit; check the exported file the shop takes, never the model alone.
- For a review, or the result in full beyond these lines (every code and field, the report, a
  redesign), read [references/manufacturing-review.md](references/manufacturing-review.md).

## Hand off

The reply is the person's record of the work: the models made or changed, the files
written, the checks run and what they showed (for a part made by a named process, the process
and the material its check judged with, and the findings left), the requirements no check covered,
and every assumption or departure from the request.

### Show the model

Show the person each model you create or change, and any model or file they ask to see. If your
tools include `cad_show` (your host may prefix it), call it with the model's id or the file's
absolute path; its description says the rest. Otherwise give the person the page's link once: a
model's page is the `view:` line its run prints, and a file's is the `url` that
`cad viewer --json FILE [FILE ...]` prints for it (never guess the port). A file you export is a
download: give its path. Never screenshot the viewer to check your own work; review with
`cad <type> snapshot`. If it fails to launch, say so.

Exact selection and measurement need a model's document, an `.xbf` or a STEP; mesh viewers
measure approximately, on triangles.
