---
name: cad
description: Designs and edits 3D CAD - parametric parts, assemblies, mechanisms and 2D cut profiles, written as build123d Python and shown live in the text-to-cad viewer. Use for any request to model, change, measure, inspect, animate, export or convert a part or a CAD file (STEP, STL, 3MF, GLB, DXF, xbf), for references and Quick Edit prompts copied from the viewer, and to check whether a part can be machined, cut and bent, molded or printed. Not for robot descriptions, which the robot-simulation skill writes.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# CAD modeling and inspection

A model is a Python function that returns a build123d shape. Running its script builds it in
text-to-cad's server, which holds the result as a document: the page the person has open follows
every run, and every command (inspect, snapshot, export, check) acts on that document by its id.
Files are exports, written when asked.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| Create or edit a part or assembly | A model script ([below](#write-a-model-and-run-it)) | [Models](references/model-contract.md), [build123d](references/build123d-modeling.md), [positioning](references/positioning.md) |
| Let the person tune a number (a wall, a fit, a count) | `model.param(...)` at the script's top level; change a value by editing its number and running the script | [Parameters](references/model-contract.md#parameters-a-person-tunes) |
| Organize a project | Its existing layout | [Project layout](references/project-layout.md) |
| Export STEP, STL, 3MF, GLB or xbf | `cad model export <id> <file>` | [Exports](references/exports.md) |
| A 2D profile, flat pattern or DXF | A model that returns 2D geometry on z=0, exported as `.dxf` | [2D profiles and DXF](references/2d-profiles-and-dxf.md) |
| Use a vendor STEP, an xbf or a scan | `step.read`, `xbf.read` or `stl.read` in the body | [Inputs](references/model-contract.md#inputs) |
| Resolve a reference or a Quick Edit prompt | `cad model inspect <id> '<ref>'` | [References](references/inspection-and-validation.md#references) |
| Measure or check geometry | A check script that calls the model | [Inspection](references/inspection-and-validation.md) |
| See a model, a view or a pose | `cad model snapshot <id> out.png` | [Snapshots](references/snapshot-review.md) |
| Articulate a mechanism, find joint limits | build123d joints in the body; `cad model ranges <id>` | [Kinematics](references/kinematics.md) |
| Explode, reveal or showcase a model | `animation()` in the body | [Animation](references/animation.md) |
| Can it be machined, bent, molded or printed? | `cad model dfm <id> --process ...` | [Can it be made?](#can-it-be-made) |
| Open an existing CAD file | Show it | [Show the model](#show-the-model) |

Whether a part holds under load is the fea skill's; a robot description, the robot-simulation skill's.

## Setup

Written for `cad==0.11.17`. Before first use in a chat, run `cad --version`. If `cad` is missing or older than
0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.

If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
https://github.com/earthtojake/text-to-cad
A project written for an earlier version may need changes; the migration guides say what:
https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations

Every command goes through one server: start it once with `cad server start` (`status`, `stop`); a
command that finds none says so. `cad run script.py` is `uv run` with cad's library and the
integrations the script imports added, so a script header names only its own extra packages, never
cad ([environments](references/environments.md)). A
build outlives the shell's time limit: run the same command again and it joins the build in progress.
`cad <command> --help` is the complete, current interface. Paths are relative to the working
directory.

## Write a model and run it

`src/bracket.py`:

```python
import build123d as bd
from cad import model


def bracket_body(width, thickness, bore):
    body = bd.Box(width, 20, thickness) - bd.Cylinder(bore / 2, thickness)
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
  view: http://127.0.0.1:<port>/<id>?token=<token>
```

Each call prints how its model built, what it holds, its document's `id:` and its page, `view:`. The
id comes from the script's path and the function's name, so it is the same on every run: use it for
every command, and give the person the page once ([Show the model](#show-the-model)).

- **A model function takes no arguments.** Dimensions are arguments of a plain helper, and each
  configuration is a `@model` of its own. Calling one returns a handle: `.id`, `.url`, `.shape`, `.export(...)`.
- **Running the script is the rebuild**, and it writes no file. The server replays whatever an edit
  did not reach, so reruns are cheap; `@memo` marks a stage of seconds of kernel work, or a body several models share
  ([what a run runs](references/model-contract.md#what-a-run-runs)). Keep the calls under
  `if __name__ == "__main__":` so other scripts can import the models.
- **An assembly calls its parts**: its body takes each part's shape (`plate().shape`), places and
  labels it, and returns a `Compound`. Each part keeps its own document. After editing a part, run the
  assembly's script.
- **Use `import build123d as bd`, attribute-style.** The import is lazy, so the kernel loads in the
  server; `from build123d import Box` or a module-level `bd.Color(...)` loads it in the script.
- **Labels name parts** in every reference, check and export. Colours are sRGB hex
  (`part.color = "#4a6fa5"`); a material gives a part density and a look
  (`from bd_materials import metals`, `part.material = metals.aluminum()`:
  [colour and materials](references/build123d-modeling.md#colour-and-materials)).
- **A body is a function of its code and its inputs**: `step.read`, `xbf.read`, `stl.read` and any
  file it opens are tracked; the clock, environment variables and randomness are not. Compose project
  models by calling them, never by reading a file the project exported.
- Units are millimetres, +Z up.

## Commands

Each acts on the document as the last run left it. `$ID` is a model's id; a file takes the
operations its own type lists (`cad step|xbf|stl|threemf|glb|dxf --help`).

| Command | Gives |
| --- | --- |
| `cad model inspect "$ID" ['<ref>']` | The document's parts, bounds, volume, mass and joints; with a ref, one part, face or edge as JSON, with `made_by`: the function, file and line that made it |
| `cad model snapshot "$ID" out.png` | A picture, drawn as the viewer draws it: `--camera top`, `--display hidden-line`, `--pose open`, `--preview` (lit, for a person) |
| `cad model export "$ID" a.step b.stl c.glb` | Files, by suffix; nothing rebuilds ([exports](references/exports.md)) |
| `cad model interference "$ID" [--pose P]` | Every pair of parts that shares volume, exactly, as built and at each pose |
| `cad model dfm "$ID" --process ...` | A manufacturing check ([Can it be made?](#can-it-be-made)) |
| `cad model ranges "$ID"` | Each joint's stops, swept from the parts ([joint stops](references/kinematics.md#joint-stops)) |
| `cad step export vendor.step vendor.xbf` | A vendor STEP as an xbf, which `xbf.read` loads many times faster |

`--tolerance MM` and `--angle DEG` mesh an STL, a 3MF or a GLB finer (a print with fits, a close
render) and apply to nothing else: an export that takes them names only mesh files, and a STEP, xbf or
DXF beside them refuses the whole export.

```bash
cad model export "$ID" STEP/bracket.step GLB/bracket.glb
cad model export "$ID" STL/bracket.stl 3MF/bracket.3mf --tolerance 0.02
```

A reference such as `0dc50a92-...#bracket/face 7` is what the viewer copies when the person picks
something: a document, a part by its labels, then an element. Resolve it with `inspect`, then edit the
code `made_by` names. A Quick Edit prompt carries its document under `File:`, its picks under
`References:` and a snapshot packet, inline JSON (save it to a file) or a `.snapshot.json` path. Where
the person drew on the view, look at what they drew before editing:
`cad model snapshot "$ID" out.png --annotation packet.snapshot.json --camera authored`
([annotations](references/snapshot-review.md#annotations-and-quick-edit-views)).

## Check each change

Read each run's output first: a part count, bounds or joint count that contradicts the intent is the
first thing to fix. Then check the change the way it can be checked:

| The change | Check it with |
| --- | --- |
| A number the person gave (a size, a distance, a volume) | An assert in the model's body on what the geometry measures, or `cad model inspect` |
| A number the design implies (a clearance, a fit, a mass) | A check script that calls the model and measures what it returns ([inspection](references/inspection-and-validation.md)) |
| An assembly's parts or a joint's travel | `cad model interference "$ID"`, with a `--pose` for each mechanism state |
| Shape, placement, colour, a mechanism | The snapshots it takes to judge it, posed where it moves |
| A 2D profile or DXF | The export, which runs the drawing checks, then `cad dxf snapshot` of the file |
| A part made by a named process | Its manufacturing check ([below](#can-it-be-made)) |

- A snapshot shows arrangement and appearance; a number comes from the geometry, never from a picture.
- Review an assembly from the inside out: a part alone before it is placed, then the parts that move
  together, then a joint at both ends of its travel, and only then the whole, from behind as well as
  the front. A cover that half encloses what it covers is a few pixels of the whole model's picture
  and most of its own.
- A check that fails to run, or cannot decide, has shown nothing. Trust a check you wrote only once
  you have seen it fail on a planted fault of the kind it guards against. Boxes, mesh points and
  sampled distances pick the pairs worth measuring; the verdict is exact geometry.
- Say what a check cannot see beside what it passed: the poses it did not take, the pairs it could not
  measure, the path between two poses checked only at its ends.
- Dropping or shrinking a feature the person specified to get a build through is a different design:
  say so instead.
- A missing or conflicting dimension that changes the result is the person's to settle; a value
  chosen in its place is an assumption to report.

## Can it be made?

`cad model dfm` says whether a part can be made by a process and what to change where it cannot. Run
it when the request names or implies a process (machined, sheet metal or laser cut, injection molded,
3D printed, or a printer, resin, filament or cutting service named), or the person asks. A material
alone names no process, but a thickness with a metal ("2 mm steel") is sheet. With none, build what was asked: no check, and no draft, reliefs or tool radii
added.

| Process | Check | Reference |
| --- | --- | --- |
| CNC milling and turning | `--process cnc --material M` (`--axes`, `--turning`, `--tools`) | [CNC](references/manufacturing-cnc.md) |
| Sheet cutting and bending | `--process sheet --material M --thickness T` (`--bend-radius`, `--k-factor`); a cut file, `cad dxf dfm` | [Sheet metal](references/manufacturing-sheet-metal.md) |
| Injection molding | `--process molding --pull z --material M` (`--cavities`) | [Injection molding](references/manufacturing-injection-molding.md) |
| 3D printing | `--process printing --technology T` (`--material`, `--build-volume`, `--layer-height`) | [3D printing](references/manufacturing-printing.md) |

```bash
cad model dfm "$ID" --process cnc --material aluminum --tools 3,6,10
```

A named process is part of the design, not a review at the end:

1. Read the process reference's *Design it* before modelling, and build its limits in.
2. Record the process in the model, so every later check is the same one: the material with its
   process on each part (`part.material = metals.aluminum(process=machined())`, with `machined` from
   `bd_materials.processes`), and the shop's flags in the module docstring
   (`Check: cad model dfm "$ID" --tools 3,6,10`).
3. Run that check after every run. The last line and the exit status are the result: `OK` (0, though
   warnings may remain), `FAILED` (1: the part cannot be made as drawn), `NOT CHECKED` (3: something
   was not judged, never a pass) and 2 for a refused command. Fix errors from each finding's `refs`,
   `value` and `limit` (`--json`); fix a warning when that leaves the request intact, else report it.
4. In the hand-off, say the process, the material the check judged with, the findings left, and that
   the rules are general practice rather than a shop's own limits.

A STEP or mesh file is checked by its own type (`cad step dfm part.step --process ...`); a mesh, for
printing only. For a review, a shop's own limits or the result in full, read
[manufacturing review](references/manufacturing-review.md). A SendCutSend order is the sendcutsend
skill's; slicing a print, the print3d skill's.

## Show the model

Show the person each model you create or change as soon as its first run succeeds, and any model
or file they ask to see. A model's page is the `view:` line its run prints, and a file's is the `url`
that `cad viewer --json FILE [FILE ...]` prints for it (never guess the port). Show it with
the first of these you have:

1. `cad_show` among your tools (your host may prefix it): call it with the model's id or the file's
   absolute path; its description says the rest.
2. A tool that opens a page in the app's own browser pane, not in the person's own browser (in the
   Claude desktop app, the Browser pane's `preview_start` with the page's `url`, or its `navigate`):
   open the page there yourself, and give the person the link as well.
3. Neither: give the person the link, to open in their browser.

The page follows every run of the model. A file you export is a download: give its path. Showing is
for the person: to check your own work, review with `cad <type> snapshot`, never a screenshot
of the page. If it fails to launch, say so.

## Hand off

Say what was made or changed, the files written, the checks run and what they showed, what no check
covered, and every assumption or departure from the request.
