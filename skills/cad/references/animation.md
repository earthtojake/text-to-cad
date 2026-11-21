# Animation: a GLB's own channels

Read this file when the user asks for an explode, a reveal, a showcase, a turntable, a
part that appears or disappears, or any movement that is not the mechanism's own. For
joints, mechanism states, couplings and configuration sequences, read
[Kinematics](kinematics.md) first.

## Contents

- [Motion or animation](#motion-or-animation)
- [Authoring](#authoring)
- [Naming parts](#naming-parts)
- [Reviewing](#reviewing)

## Motion or animation

- **A configuration sequence** (a motion on the page) is the mechanism's: joint values
  over time, kept in the document. A robot's gait, a door's opening, an engine's running
  belong there ([kinematics](kinematics.md#configuration-sequences)). Prefer one where
  the mechanism says the movement.
- **An animation** (`cad.build123d`'s `animation`) is the GLB's: glTF channels
  (translation, rotation, scale) on the parts a GLB places, and the mechanism's forward
  kinematics at given times. An explode, a reveal, a showcase or a hidden cover belongs
  here. It is baked into every GLB exported from the model and is no part of the
  mechanism: the model's page, a snapshot and a STEP show nothing of it.

## Authoring

```python
# src/hinged_box.py
import build123d as bd
from cad import model
from cad.build123d import animation, configuration_sequence, mechanism_state


@model
def hinged_box_showcase():
    ...                                                            # a body, a hinged lid, a latch, two feet
    mechanism_state(box, "shut", hinge=0)
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
cad run src/hinged_box.py                             # prints the model's id
cad model export "$ID" GLB/hinged_box_showcase.glb
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
- **`.hide(parts, at=)`**: a `STEP` scale to 0, since glTF has no visibility channel.
  `.scale(parts, to=1, start=t, end=t, interpolation="STEP")` brings the part back.
- **`.pose(at={t: mechanism state or joint values}, interpolation=)`**: the mechanism
  driven inside the animation, its links placed by forward kinematics, the joint values
  eased between the keys. It stands at its first pose before its first time.

`start` defaults to 0 and `end` to the duration. With `STEP`, a channel jumps at `end`.
The GLB stores every channel but a `STEP` one as glTF `LINEAR` keys within 0.1 mm and
0.1° of its curve, so `interpolation` says how a part moves, not which sampler the file
holds.

## Naming parts

Parts are named as a ref's owner names them
([references](inspection-and-validation.md#references)), from the assembly the animation
is on: a label (`latch`), a path (`feet/foot_1`, `hand/finger.2`), or a glob (`feet/*`,
`wheel?`). A glob matches a label, a numbered segment, or a path written with either
(`*/screw` is every `screw` one level down), and takes its outermost matches, each a part
or an assembly of its own. A name an assembly shares with a part inside it (`stem`
holding a part `stem`) is the assembly, and the part is `stem/stem`. Each name or match
moves as one body: an assembly's parts together, about its centre.

Channels compose as a scene graph does. One part's translations add, after its
rotations. A part inside an assembly moves with the assembly's channels too, the
assembly's outermost. All of them act after `.pose`, so an explode moves a posed part.
Two channels of one path on one part may not overlap in time, nor two `.pose` calls; a
part's path may not be `STEP` in one channel and eased in another; and an animation may
not take a configuration sequence's name. Each fails the run by name.

## Reviewing

A run checks an animation's names, times and overlaps, and nothing draws it but a GLB's
player: a snapshot shows the model as built. Export the GLB and give the person its
path; when they ask to see it, open the file in the viewer
([Show the model](../SKILL.md#show-the-model)), which plays its motions and animations.
