# Animation: a GLB's own channels

Read this file when the user asks for an explode, a reveal, a showcase, a turntable, a
part that appears or disappears, or any movement that is not the mechanism's own. For
joints, mechanism states, couplings and configuration sequences, read
[Kinematics](kinematics.md) first.

## Contents

- [Motion or animation](#motion-or-animation)
- [Authoring](#authoring)
- [Naming parts](#naming-parts)
- [What fails the run](#what-fails-the-run)
- [Reviewing](#reviewing)

## Motion or animation

Two layers, each true to its format:

- **A configuration sequence** (`cadgen.ap242`'s `configuration_sequence`, a motion on
  the page) is the mechanism's: joint values over time, kept in the document as STEP
  AP242's configuration sequence. Every GLB of the model carries it as a clip, and the
  page's Motion tool plays it. A robot's gait, a door's opening, an engine's running
  belong here.
- **An animation** (`cadgen.gltf`'s `animation`) is the GLB's: glTF channels
  (translation, rotation, scale) on the parts a GLB places, and the mechanism's forward
  kinematics at given times. It is no part of the mechanism: the viewer's page and a
  STEP show nothing of it, and an exported `.xbf` only records its compiled tracks for a
  GLB. It is baked into every GLB exported from the model. An explode, a reveal, a
  showcase or a hidden cover belongs here.

The rules:

- **Prefer a motion where the mechanism says it**, and waypoints in it.
- **No helper joints to fake an explode.** A joint per part only to slide it out is an
  animation's job, and the Position panel would show a slider for each.
- **Animations are GLB-only.** `cadgen export "$ID" model.glb`,
  `export(model(), "model.glb")` and `cadgen export model.xbf model.glb` from an xbf the
  model exported all bake them, the same bytes. `read_xbf` imports a part's geometry
  without them.
- **`.hide` is a scale trick.** glTF has no visibility channel, so a hidden part is
  scaled to 0. Use `.scale(parts, to=1, start=t, end=t, interpolation="STEP")` to bring
  it back.
- **The GLB stores lines.** Every channel but a `STEP` one is written as glTF `LINEAR`
  keys within 0.1 mm and 0.1° of its curve, so `interpolation` says how a part moves, not
  which sampler the file holds.

## Authoring

```python
# src/hinged_box.py
import build123d as bd
from cadgen import model
from cadgen.ap242 import configuration_sequence, mechanism_state
from cadgen.gltf import animation


@model
def hinged_box_showcase():
    ...                                                            # a body, a hinged lid, a latch, two feet
    mechanism_state(box, "open", hinge=100)
    configuration_sequence(box, "open_close", [(0, "shut"), (1.5, "open"), (3, "shut")])   # every GLB's clip

    show = animation(box, "showcase", duration=4)                  # a GLB's alone
    show.pose(at={0: "shut", 1.5: "open", 3.5: "shut"})            # the hinge, through forward kinematics
    show.stagger("feet/*", by=(0, 0, -20), step=0.5, start=0.5)   # each foot drops in turn
    show.rotation("latch", axis=(0, 0, 1), turns=2, start=1, end=3, interpolation="LINEAR")
    show.translation("latch", by=(30, 0, 0), start=1, end=3)
    show.hide("latch", at=3)
    return box
```

```bash
python src/hinged_box.py                             # prints the model's id
cadgen export "$ID" GLB/hinged_box_showcase.glb
```

`animation(assembly, name, duration=)` returns a builder; every call returns it, so calls
chain. `duration` is the animation's length, in seconds.

- **`.channel(parts, path=, keys=[(t, value), ...], interpolation="CUBICSPLINE")`** is
  glTF's channel itself. `path` is `translation` (a key's value an offset from as built,
  mm), `rotation` (a unit quaternion `(x, y, z, w)`, the turn about `about=`, default the
  parts' centre) or `scale` (a uniform factor, 1 as built, each part about its own
  origin). `interpolation` is `CUBICSPLINE` (eased in and out at every key), `LINEAR`
  (constant speed) or `STEP` (each key held until the next). A channel does nothing
  before its first key and holds its last.
- **`.translation(parts, by=|to=, start=, end=, interpolation=)`**: by a vector, or until
  the parts' centre reaches a point.
- **`.rotation(parts, axis=, turns=|by=|to=, about=, start=, end=, interpolation=)`**:
  whole turns, degrees, or degrees from as built about `axis`; any size of turn is kept.
- **`.scale(parts, to=, start=, end=, interpolation=)`**: from the scale it has at
  `start`.

Helpers compile to channels:

- **`.explode(parts, direction=|radial=, distance=, start=, end=)`**: along a direction,
  each part by `distance` times its rank along it (the first stays); or `radial=` a point
  (or `True`, the middle of the parts), each part `distance` away from it.
- **`.stagger(parts, by=, step=, start=, each=)`**: each part in turn moved `by`, `step`
  seconds apart.
- **`.hide(parts, at=)`**: a `STEP` scale to 0.
- **`.pose(at={t: mechanism state or joint values}, interpolation=)`**: the mechanism
  driven inside the animation, its links placed by forward kinematics, the joint values
  eased between the keys. It stands at its first pose before its first time.

`start` defaults to 0 and `end` to the duration. With `STEP`, a channel jumps at `end`.

## Naming parts

Parts are named as a ref's owner names them, from the assembly the animation is on: a
label (`latch`), a path (`feet/foot_1`, `hand/finger.2`), or a glob (`feet/*`,
`wheel?`). A glob takes its outermost matches, each a part or an assembly of its own.
Each name or match moves as one body: an assembly's parts together, about its centre.

Channels compose as a scene graph does. One part's translations add, after its
rotations. A part inside an assembly moves with the assembly's channels too, the
assembly's outermost. All of them act after `.pose`, so an explode moves a posed part.

## What fails the run

Each of these fails the run, by name:

- a part no occurrence is (the error lists the nearest names) or a glob matching nothing;
- a mechanism state or joint the mechanism lacks, in `.pose`;
- two channels of one path on one part overlapping in time, or two `.pose` calls
  overlapping;
- a part whose translation, rotation or scale would be `STEP` by one channel and eased
  by another;
- a time outside `0` to `duration`;
- an animation with a configuration sequence's name.

## Reviewing

Export the GLB and open it in the CAD Viewer ([Show the model](../SKILL.md#show-the-model)):
its Animation section lists the motions and the animations, and plays, pauses, scrubs
and loops them, at a chosen speed. While one plays, it owns the parts' places; putting
it down puts them back at rest. A snapshot shows the model as built: it never plays an
animation.
