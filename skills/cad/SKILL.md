---
name: cad
description: Creates and edits parametric CAD parts and assemblies as Python build123d models that cadgen's engine builds and the CAD Viewer shows live; exports STEP, STL, 3MF, GLB and xbf files on request; resolves prompt references, measures geometry, and articulates or animates assemblies. Use for 3D CAD modeling, editing a model script (any change to a part's or assembly's `.py`), organizing a CAD project, exporting or converting CAD files, Quick Edit prompts, mechanisms, and explode or showcase animations. Opens and reviews existing XBF, STEP/STP, STL, 3MF and GLB files in the CAD Viewer.
license: MIT
---

# CAD modeling and inspection

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files for the current interface.

A model is a Python function; running its script rebuilds it in cadgen's warm engine, and the
page the person has open updates. Files are exports, made when asked.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **Create or edit a part or assembly** | The project's model script, or a new one ([below](#write-a-model-and-run-it)). | [Models](references/model-contract.md), [build123d](references/build123d-modeling.md), [positioning](references/positioning.md) |
| **Organize a CAD project** | The project's existing layout. | [Project layout](references/project-layout.md) |
| **Export STEP, STL, 3MF, GLB or xbf** | `cadgen export <id> <file>`. | [Exports](references/exports.md) |
| **Use a vendor STEP, an xbf or a scan in a model** | `read_step`, `read_xbf` or `read_mesh` in the body. | [Inputs](references/model-contract.md#inputs) |
| **Resolve a reference from a prompt** | `cadgen inspect <id> '<ref>'`. | [References](references/inspection-and-validation.md#references) |
| **Measure or check geometry** | A check script that calls the model. | [Inspection](references/inspection-and-validation.md) |
| **See a model, a view or a pose** | `cadgen snapshot <id> out.png`. | [Snapshots](references/snapshot-review.md) |
| **Articulate a mechanism** | build123d joints in the body, then `cadgen.ap242`. | [Kinematics](references/kinematics.md) |
| **Explode, reveal or showcase a model** | `cadgen.gltf`'s `animation()` in the body. | [Animation](references/animation.md) |
| **Open an existing XBF, STEP/STP, STL, 3MF or GLB** | Show it to the user. | [Show the model](#show-the-model) |

A project built with cadgen 0.7 may need migrating: see [migrations](references/migrations.md).

For 2D DXF drawings use `$dxf`; this skill owns any 3D part the drawing projects.
Use the corresponding robot-description skill for URDF, SRDF or SDF.

## Setup and paths

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

`cadgen doctor <skill-dir>` reports the installation in use, whether it is the one
this skill pins, whether the CAD kernel loads, and whether the engine is running, starting
it when none is. Each
command's `--help` lists its flags. The first launch downloads cadgen and may outlast a
host's server start timeout (Claude Code: 30 s by default, raised by setting `MCP_TIMEOUT` in
milliseconds; Codex: the plugin asks for 300 s); a restart resumes the download.

A project venv can put its own `cadgen` ahead of the launcher on PATH, even when
`~/.local/bin` is on PATH. Run `~/.local/bin/cadgen +0.8.1 doctor` to diagnose that
case and use that full launcher path for commands until PATH is corrected.

One engine serves the installation: the first run starts it, every run and every
command goes through it, and it serves the viewer. `cadgen status` lists its workers
and the documents it holds; `cadgen stop` stops it, and any older one left running.
A build cut off by the shell's time limit keeps running in the engine; run the same
command again and it waits for that build and replays it (`cadgen status` shows it).
Give a cold build of a large model the shell tool's longest timeout, or run it in the
background. A refused folder is another case: if a command ends with 'the system denies
cadgen's local engine', this shell's sandbox forbids the engine's folder itself: rerun it
with the sandbox's permission (in Codex, escalated permissions) rather than retrying.

Command-line paths, and the paths `read_step`, `read_xbf`, `read_mesh` and `export`
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
from cadgen import model


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
python src/bracket.py
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
within its namespace, the function's name by default, `name=` gives it another. In 0.8 the namespace
is the script's folder; two explicit names in it must differ.

- **Running the script is the rebuild.** It writes no file. The engine's warm worker for
  the script replays every operation an edit did not reach, so a comment re-runs nothing
  and a dimension edit re-runs what reads it
  ([what a run runs](references/model-contract.md#what-a-run-runs)). Decoration only
  declares: keep the calls under `if __name__ == "__main__":` so other scripts can import
  the models.
- **`@memo` marks stages, never parts.** The engine already replays every kernel call, so
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
- **Colours are sRGB**, as a person picks them: `part.color = "#4a6fa5"`, or 0-255
  integers. Import `metals` from `bd_materials`; assign a native material with
  `part.material = metals.aluminum()`
  ([colour and materials](references/build123d-modeling.md#colour-and-materials)).
- **Inputs** are `read_step`, `read_xbf` and `read_mesh` in the body, and any file its
  Python opens, each tracked by its bytes. The clock, environment variables and
  randomness are not seen: a body is a function of its code and its inputs. Compose
  project models by calling them, never by reading a file the project exported.
- **References** to faces, edges and parts come from `cadgen inspect <id> [ref]`, and the
  body picks the same element with build123d's selectors; verify with a snapshot when in
  doubt ([references](references/inspection-and-validation.md#references)).
- **A shape with no function** (a notebook cell, a REPL) is handed over:
  `model(shape, name="plate")` returns the same handle, and no command builds it again.
- **The engine never reruns code.** A restart reopens every document from the engine's
  cache, as last built. When the cache holds no file of one (deleted by hand, or never
  saved), the page, `cadgen inspect <id>` and `cad_show` print the command that brings it
  back (`cadgen run src/bracket.py`). Run it.
- Model units are millimetres, +Z up. `$step-parts` finds real vendor models of
  purchasable parts such as fasteners, bearings and servos.
- An image without a scale sets no fit dimension, and a drawing's units, projection and
  revision decide how its numbers read. A missing or conflicting dimension that changes
  the result is the person's to settle; a value chosen in its place is an assumption.

## Files, when asked

A file is an action on the document the engine holds, never part of the model: no code
change and no rebuild, written at once. It holds what the document held when it was
written, so a change made after it is in the file only once it is written again. Write one
when the person asks for it:

```bash
cadgen export "$ID" STEP/bracket.step STL/bracket.stl GLB/bracket.glb 3MF/bracket.3mf
```

A project with standing deliverables gets an `exports.py` that imports its models and
calls `export(x, path, ...)` on each (`x` a model call's handle); running it rewrites every deliverable
([exports](references/exports.md)). An export takes a document and its destinations,
and nothing else: a posed file is a model that returns the posed assembly
(`posed(arm(), "folded")`), and a part on its own is the part's own model.

The xbf, cadgen's own document, is Save As: export one only to share a model without its
code, or to compose it in another project with `read_xbf`. A restart needs none: the
engine's own cache reopens every document it built, as last built. A vendor STEP is
converted to an xbf once
(`cadgen export vendor/motor.step vendor/motor.xbf`) and read with `read_xbf`, many
times faster than parsing the STEP.

## Projects built around exported files

A project can instead revolve around its exported files, but only when the person asks to
iterate on the exported file itself or the project already does: an `exports.py`, a consumer
that reads the files (a robot description, a slicer, a drawing pipeline), or a 0.7-era
layout, whose runs wrote files. The loop is three steps. The script writes the file on each
run, by a file decorator in place of `@model` (`@step("../STEP/bracket.step")`, relative to
the script), or `exports.py` or `cadgen export` follows the run. Show the file's page, not
the model's: it follows the file on disk, updating when a run rewrites the file.
Verification reads the file: `cadgen snapshot` or `cadgen inspect` with its path, or
`read_step` in a check. The costs keep the default the default: each iteration pays the
file's translation and the page's re-read, a STEP parsed again; a file names no model, so a
ref picked on its page has no `made_by` and a Quick Edit from it no way back into the code;
and the model's page stays the better place to look while editing.
[Exports](references/exports.md#model-page-or-file-page) tables the triggers and costs.

## Pictures

After every run, read its line and the delta under it; a contradiction with what you
intended is fixed before anything else. A number the person gave is checked by an assert
inside the model's body on what the geometry measures, a bound, a distance or a volume, or by
`cadgen inspect`, never by restating the constant, and never by code after the call in the
model's script ([inspection](references/inspection-and-validation.md)). A derived number they
asked for is a check script; neither is ever read off a picture. A structural or appearance
change, new parts, placements, colours or a mechanism,
gets the snapshots it takes to judge it, usually one from the angle that shows the change,
more when a view leaves the question open, and a posed one for a mechanism state; never
several angles by habit. For a large assembly, isolate the parts the edit touched or hide
what covers them and frame them, instead of drawing the whole model. Resolve a reference with
`cadgen inspect` only when a prompt names one.

```bash
cadgen snapshot "$ID" tmp/review.png
cadgen snapshot "$ID" tmp/top.png --camera top --display hidden-line
cadgen snapshot "$ID" tmp/open.png --pose open
```

A snapshot draws the document as the viewer does, rendered by OCCT, and writes nothing
but the PNG. Its options say how the picture is drawn: camera (`--camera top`), display,
grid, pose (`--pose open`) and size. It shows arrangement and appearance, not dimensions
([snapshots](references/snapshot-review.md)).

## Prompt references and inspection

A reference such as `0dc50a92-a21f-5895-a245-ebdeb5352f3b#bracket/face 7` names geometry
in a document by the engine's own names: the document (a model's id, or a file's
absolute path), `#`, a part or an assembly by the labels on its way from the root
(`hand/finger.2` is the second component labelled `finger` in `hand`), then, after a
slash, one element by its name (`f:`, `e:`, `v:`) or its number (`face 7`). The CAD
viewer copies them. When a prompt names one, resolve it with `cadgen inspect`:

```bash
cadgen inspect "$ID" "bracket/face 7"
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
cadgen snapshot "$ID" tmp/quick_edit.png --annotation tmp/bracket.snapshot.json --camera authored
```

Inspect supplied annotations before editing. Without annotations, the captured view is
optional context; render it when useful to the request. After editing, run the script and
draw it again to check the change
([annotations and Quick Edit views](references/snapshot-review.md#annotations-and-quick-edit-views)).

A reference into a file that is not a document names what the viewer picked in it, in
that file's own terms (none is a ref `cadgen inspect` resolves):

| File | Reference | Means |
| --- | --- | --- |
| URDF, SRDF, SDF | `/work/arm/arm.urdf#upper_arm` | the link `upper_arm` |
| GLB | `/work/out/model.glb#n12` | the glTF node `nodes[12]` (0-based, the file's own index) |
| 3MF | `/work/out/plate.3mf#o2.1` | the 2nd `<build><item>`'s 1st `<component>` (1-based); `#o3` is the 3rd build item |
| STL | the file alone, on `File:` | one mesh: nothing in it is picked |

## Check the design

A check is a Python script that calls the model and measures what it returns, so it
tests the model as it is now. Write one only when the person asks for a dimension, a fit
or a mass, or when the change is numeric and the number matters ([Pictures](#pictures)):

Copy `world_parts` and `find_part` from
[Opening geometry](references/inspection-and-validation.md#opening-geometry) into the check
first. They accumulate parent placements; raw `.leaves` do not.

```python
from cadgen.geometry import closest_points

from assembly import assembly

kit = assembly().shape                       # rebuilt (replayed), returned as a tree
plate = find_part(kit, "plate")               # copied into world coordinates
post = find_part(kit, "standoff_left")        # refuses missing or repeated labels
print(plate.bounding_box().size)              # the envelope: not a hole's diameter or a wall's thickness
print(closest_points(plate, post).distance)   # 0: the standoff sits on the plate
```

- Measuring is what shows a request's dimensions and clearances. In an assembly, nothing
  interferes when `overlap_volume` is 0 for every pair of solids apart from fits named
  on purpose, and a part meant to rest on another touches it when their
  `closest_points` distance is 0. Both describe the parts as built, not a pose
  ([measurements](references/inspection-and-validation.md#measurements)).
- `cadgen inspect "$ID" <assembly label>` weighs an assembly (the label it was given, which
  is also the root name `inspect "$ID"` prints): each part's volume times its material's
  density, and the parts that have no material.
- A check that fails or cannot decide has shown nothing about the design.
- A retry that leaves out or shrinks a specified feature (a fillet skipped, a radius
  reduced) builds a different design from the one asked for.

## Hand off

The reply is the person's record of the work: the models made or changed, the files
written, the checks run and what they showed, the requirements no check covered, and
every assumption or departure from the request.

### Show the model

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

Exact selection and measurement need a model's document, an `.xbf` or a STEP; mesh viewers
measure approximately, on triangles.
