# Animations

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A **configuration sequence** (a motion) is the mechanism's and an **animation** is the GLB's. A
sequence moves pair values over time (**Configuration sequences**): the document keeps it, every
GLB of the document bakes it, and STEP, STL and 3MF carry nothing of it. An animation moves the
nodes a GLB places, in glTF's own terms -- translation, rotation and scale channels, and the
mechanism's forward kinematics at given times -- for what a mechanism does not say: an explode, a
reveal, a showcase, a part hidden. It is baked into every GLB the model declares, when that GLB is
written (law 10), from the build's tree in memory.

The xbf is the model's Save As and holds what its build declared, so it carries the compiled
tracks too: a **build record** on its main label after the closure, as the closure is kept (a
`TDataStd_AsciiString`, `document.ANIMATIONS_GUID`), holding `animations.record` -- each
animation's name, duration and tracks (path, interpolation, keys, the occurrence paths of its
parts, what it says beyond its keys, its label and its order), the build's JSON
(`animations.to_json`), no code. A document with no animation holds no record. It is no part of the
mechanism subtree, which stays AP242's alone (law 12), and only a GLB reads it:
`document.Loaded.animations`, and so `Source.read`, give the tracks back as the harvest made them,
so a GLB exported from the xbf (`cad xbf export model.xbf model.glb`), from a held document by its
id (**Document lifetime**) and by the build's own worker are byte for byte one GLB, and a model
taken from the cache after a restart (**Build closure**) writes that GLB too. Every other reader
ignores it: `xbf.read` imports a part, never a child's record (a parent's GLB bakes its own
animations alone), the viewer's page shows the document's structure, and STEP is AP242 with nothing
of ours. For now a model with an animation declares its GLB beside its xbf, the two decorators
stacked on one function: the xbf records the animation, the GLB bakes it.

```python
import build123d as bd
from cad import glb, xbf
from cad.build123d import configuration_sequence, mechanism_state
from cad.build123d import animation

@xbf("XBF/box.xbf")
@glb("XBF/box.glb")
def box():
    ...                                                              # a hinged lid, a latch, feet
    mechanism_state(box, "open", hinge=100)
    configuration_sequence(box, "open_close", [(0, {"hinge": 0}), (1.5, "open"), (3, {"hinge": 0})])  # every GLB's
    show = animation(box, "showcase", duration=4)                    # this GLB's alone
    show.pose(at={0: {}, 1.5: "open", 3.5: {}})                     # the mechanism, by its FK
    show.stagger("feet/*", by=(0, 0, -20), step=0.5, start=0.5)
    show.rotation("latch", axis=(0, 0, 1), turns=2, start=1, end=3, interpolation="LINEAR")
    show.channel("latch", path="translation", keys=[(1, (0, 0, 0)), (3, (30, 0, 0))])
    show.hide("latch", at=3)
    return box
```

`animation(assembly, name, duration=)` returns a builder whose calls chain (`animations.py`). Its
primitive is glTF's channel, `.channel(parts, path=, keys=[(t, value), ...], interpolation=)`:
`path` is `translation` (a key an offset from as built, mm), `rotation` (a unit quaternion
`(x, y, z, w)`, the turn about `about=`, default the reference's centre) or `scale` (a uniform
factor, each part about its own origin, as glTF scales a node); `interpolation` is `CUBICSPLINE`
(the default, eased in and out at every key), `LINEAR` or `STEP`, as a sampler spells them.
`.translation(parts, by=|to=)`, `.rotation(parts, axis=, turns=|by=|to=, about=)` and
`.scale(parts, to=)` are channels from `start` (0) to `end` (the duration). The helpers compile to
channels: `.explode(parts, direction=|radial=, distance=)` a translation per reference (along a
direction by its rank, or away from a point), `.stagger(parts, by=, step=)` one per reference in
turn, `.hide(parts, at=)` a `STEP` scale to 0 (glTF has no visibility channel), and
`.pose(at={t: mechanism state or values})` translations and rotations of every part the mechanism
moves, its joint values eased between the keys. The duration is the animation's length, in its
`extras.cad.duration` as a motion's is (glTF has no field for it), beside `"kind": "animation"`.

Parts are named as a ref's owner names them (**References**: a label, `feet/foot_1`, a path from
the assembly the animation is on) or by a glob (`feet/*`, `wheel?`), its outermost matches each a
reference of its own; a reference's parts move as one body. A reference's translations add, after
its rotations; a part's place is every reference holding it, the largest outermost (a scene
graph's order), after the pose. The build fails by name on a part no occurrence is, a
configuration or joint the mechanism lacks, two channels of one path on one reference overlapping
in time, two poses overlapping, a part one glTF channel would interpolate by `STEP` and by
another interpolation, a time outside the duration, and an animation named as a motion is.

**The bake** (`export/animation.py`). A GLB holds the document's motions, then each animation,
one glTF animation per name, its samplers keyed from 0 to the duration. Each part a channel moves
gets a channel per path it changes, its true place at `t` composed as above; a path's
interpolation is its channels': `STEP` keys at each jump, `LINEAR` and `CUBICSPLINE` keys from the
channels' own key times, each step halved while glTF's interpolation strays from the true place by
more than a motion's tolerance (1e-3 of the model's size in an origin, 1e-3 radian, 1e-3 in a
scale), and two keys never more than 120 degrees apart. A CUBICSPLINE key's tangents are the
true curve's one-sided derivatives there, as a motion's are and as the 0.7 clip baker's central
differences were in the limit. Against that baker, on a hinge eased through 100 degrees, a slide
eased 60 mm and a constant spin (a 127 mm model), the two curves agree within 0.1 mm at every
corner of each part, each within its own tolerance of the motion, the new one in 5 to 7 keys a
path where the old one wrote 6 to 11. The parts of one reference move as one body, so their
channels' keys are the same bytes and share one sampler, as a motion's do. The GLB writes every
channel but a STEP one as LINEAR keys within a tenth of a millimetre and of a degree of this bake
(**GLB keys**).
