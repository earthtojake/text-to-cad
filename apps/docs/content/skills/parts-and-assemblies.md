---
title: Parts and assemblies
description: The cad skill writes parts, assemblies, mechanisms and DXF profiles as build123d scripts, builds them live in the viewer and exports files on request.
---

The `cad` skill turns a request for a part or an assembly into a Python script written with build123d, a Python library for B-rep CAD (solid models described by their faces and edges). The server builds it into a model you see live in the viewer, and writes files when you ask.

## What it makes

- **Model scripts you own**, usually under `src/`, that you keep editing as plain text.
- **A live model page** in the [viewer](/docs/viewer), updated on every run.
- **Mechanisms** you can pose and play in the viewer.
- **DXF profiles, gaskets and flat patterns** for laser, plasma, waterjet and routing shops.
- **STEP, STL, 3MF, GLB and DXF files**, only on request, in folders a project normally keeps out of git.

## How it works

A model is a function with no parameters, decorated with `@model`, that returns a build123d shape. Its dimensions are the arguments of a plain helper, and each configuration is a `@model` of its own, with its own id and page. Units are millimetres and +Z is up.

```python
import build123d as bd
from cad import model


def bracket_body(width, thickness, bore):
    body = bd.Box(width, 20, thickness)
    body = body - bd.Cylinder(bore / 2, thickness)
    body.label = "bracket"
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

`cad run` works like `uv run`, so the script needs no setup:

```bash
cad run src/bracket.py
```

Each call in `__main__` prints how its model built, its `id:` and its `view:` page. The id comes from the script's path and the function's name, so it is the same on every run and the open page follows it. A warm worker in the server keeps every kernel operation the script ran: a comment re-runs nothing, and a changed dimension re-runs only what reads it. Your agent checks each change with `cad model snapshot "$ID" tmp/review.png` and an `assert` on the dimensions you gave, and resolves a face you picked in the viewer with `cad model inspect`.

An assembly's body calls each part model, places it, labels it and returns a `Compound`. Each part keeps its own document and id, and the labels name each placement in the viewer's tree, in references and in exports.

```python
@model
def assembly():   # plate and standoff_m3 are models imported from their scripts
    base = plate().shape
    post = standoff_m3().shape
    left = bd.Pos(-15, 0, 8) * post
    right = bd.Pos(15, 0, 8) * post
    left.label, right.label = "standoff_left", "standoff_right"
    return bd.Compound(children=[base, left, right], label="assembly")
```

Running a child's script alone leaves its assemblies as they were, so the assembly's own script is run to update them.

Exports are written from the document the server holds, so no code changes and nothing rebuilds:

```bash
cad model export "$ID" STEP/bracket.step STL/bracket.stl GLB/bracket.glb 3MF/bracket.3mf
```

| Format | What it carries |
| --- | --- |
| STEP (AP242) | Names, colours and materials; not the mechanism |
| STL | Binary, in millimetres |
| 3MF | An object per part, a build item per placement |
| GLB | glTF 2.0, Y up, in metres, the assembly as a node tree |

An STL or 3MF for a print with tight fits takes `--tolerance MM`, about a tenth of the smallest clearance.

## Mechanisms and animation

A mechanism is an assembly whose parts move relative to each other: a hinge, a slide, a gripper, a robot arm. Its joints are build123d's (`RevoluteJoint`, `LinearJoint`, `CylindricalJoint`, `BallJoint`, `RigidJoint`), joined with `connect_to`. The value a joint is connected at is the as-built pose, the one every exported file shows, and `angular_range` or `linear_range` set its limits, in degrees and millimetres. From `cad.build123d`, a mechanism state is a named pose and a configuration sequence is joint values over time:

```python
mechanism_state(assembly, "closed", elbow=0)
mechanism_state(assembly, "open", elbow=90)
return configuration_sequence(assembly, "cycle", [(0, "closed"), (2, "open"), (5, "closed")])
```

Couplings (`gear_pair`, `rack_and_pinion_pair`, `screw_pair`) make joints move together by a ratio.

`cad model ranges "$ID"` finds joint stops: it turns or slides each joint alone, a degree or a millimetre at a time, until its parts meet, and names the two parts. It writes nothing; your agent writes the stops into the joint's range. `cad model interference "$ID"` answers exactly, on the parts' own solids, which pairs share volume, at the poses it is given:

```bash
cad model interference "$ID" --pose open --pose cycle@2.5
cad model interference "$ID" --fit pin base
```

`--fit` names a pair meant to overlap, such as a pin in a bore. Exit 0 is clear, 1 means a pair shares volume, and 3 means a pair could not be measured, which is not a pass.

An explode, a reveal or a showcase is `animation()`, a set of glTF channels on parts and no part of the mechanism. The viewer's Position panel poses the joints, with your states as presets, and a playbar plays the sequences. In a GLB every configuration sequence becomes a named animation clip and every `animation()` is baked in, for Blender, three.js and the viewer to play. STEP, STL and 3MF carry placements only.

## DXF profiles and flat patterns

A DXF is the 2D file that laser, plasma, waterjet and routing shops cut from. A drawing is a `@model` that returns build123d 2D geometry on z=0, and one returned shape is one layer, `CUT`:

```python
HOLE_D = 4.5


@model
def gasket():
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
        bd.Circle(HOLE_D / 2, mode=bd.Mode.SUBTRACT)
    return cut.sketch
```

A drawing with more than one CAM operation returns a `Compound` whose children's labels are their layers (`CUT`, `ENGRAVE`). From a 3D part, the drawing script calls the model and uses `flat_pattern(shape, coordinate=, kerf=)`; a vendor STEP is read with `step.read` first. Kerf is added with `offset_profile` or `kerf=`, never by hand-offsetting coordinates.

`cad model export "$ID" DXF/gasket.dxf` runs the drawing checks and refuses the file if one fails: units are set, nothing is drawn twice, no entity has zero length, every cut profile closes, and something is drawn. The file is in millimetres, arcs stay arcs and holes stay circles, and an unchanged drawing exports an identical file on any machine. `cad dxf snapshot` draws the file itself, and the viewer opens it as a read-only 2D drawing with its layers.

For sheet work, a cut-file check reads every entity on a cut layer as a cutter would:

```bash
cad dxf dfm part.dxf --process sheet --material aluminum --thickness 3 --kerf 0.2
```

It reports open contours, curves cut twice, crossing contours, pieces that fall out of a hole, and holes, webs and gaps small against the thickness. A file with no units is `NOT CHECKED` until `--units mm` states them. A folded STEP or model is unfolded with a K-factor; without the shop's `--k-factor` one is read from a chart, and the flat is not a production blank. The verdicts are those of the [manufacturing checks](/docs/skills/manufacturing-checks).

## Ask for it

- "Make a 60 by 40 mm mounting plate, 4 mm thick, with four 4.5 mm holes 6 mm in from the corners."
- "Add a hinge to the lid of the enclosure, 0 to 110 degrees, and name two poses, shut and open."
- "Make a 4 second explode animation of the hinged box and export it as a GLB."
- "Make the flat pattern of this plate as a DXF for a laser. It is 3 mm 5052 aluminium and I want 0.15 mm kerf compensation."

## Limits

- A model takes no parameters. A variant is another `@model` calling the same helper.
- A file is a detached copy, changed only when it is written again.
- A mesh (STL, 3MF, GLB) never becomes a STEP or a model, because it has no B-rep.
- A snapshot shows arrangement and appearance, not measurements.
- A linkage that closes a loop (a four-bar, a slider-crank) is kept but not posed: there is no solver.
- `ranges` does not sweep a cylindrical or spherical joint, and interference checks only the poses it is given.
- This is kinematics, not dynamics. Simulating a robot is [robotics and simulation](/docs/skills/robotics-and-simulation).
- `flat_pattern` lays out a flat plate, not a folded part.
- The drawing checks show a well-formed cut layout, not that a shop can cut it ([SendCutSend](/docs/skills/fabrication-services#sendcutsend)).

## The skill

This is the `cad` skill ([SKILL.md](repo:skills/cad/SKILL.md)). Its most useful references:

- [Models](repo:skills/cad/references/model-contract.md) and [build123d patterns](repo:skills/cad/references/build123d-modeling.md)
- [Exports](repo:skills/cad/references/exports.md) and [inspection](repo:skills/cad/references/inspection-and-validation.md)
- [Kinematics](repo:skills/cad/references/kinematics.md) and [animation](repo:skills/cad/references/animation.md)
- [2D profiles and DXF](repo:skills/cad/references/2d-profiles-and-dxf.md) and [sheet metal cut files](repo:skills/cad/references/manufacturing-sheet-metal.md#cut-files-dxf)

Related pages: the [viewer](/docs/viewer), [manufacturing checks](/docs/skills/manufacturing-checks), the document types [model](/docs/document-types/model), [STEP](/docs/document-types/step), [STL](/docs/document-types/stl), [3MF](/docs/document-types/threemf), [GLB](/docs/document-types/glb) and [DXF](/docs/document-types/dxf), and the [build123d](/docs/integrations/build123d) integration.
