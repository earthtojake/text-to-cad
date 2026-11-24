# Configuration sequences

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A configuration sequence -- AP242's `interpolated_configuration_sequence`, a **motion** in the
structure and the viewer -- is a definition in the model's code, beside its mechanism states:

```python
from cad.build123d import configuration_sequence, mechanism_state

mechanism_state(arm, "folded", shoulder=0, elbow=0)
mechanism_state(arm, "reach", shoulder=45, elbow=90)
configuration_sequence(arm, "cycle", [(0, "folded"), (2, "reach"), (5, "folded")])  # waypoints, eased
configuration_sequence(arm, "wave", [(0, {"wrist": -30}), (1, {"wrist": 30}), (2, {"wrist": -30})], ease="linear")
configuration_sequence(arm, "nod", lambda t: {"elbow": 45 + 20 * math.sin(t)}, duration=6)  # a function of time
```

`configuration_sequence(assembly, name, waypoints_or_fn=None, *, sweep=None, duration=None,
ease="cubic")` takes one of: waypoints `[(t, pose), ...]` (seconds from 0, increasing; `pose` a
mechanism state's name or `{joint: value}`, the rest as built; the last time is the duration), a sweep
`{joint: (from, to)}` with `duration` (two waypoints), or a callable `t -> {joint: value}` with
`duration`. `ease` is `cubic` (each step eased in and out, every pair arriving together at every
waypoint: AP242's `synchronous_interpolation_type`) or `linear` (constant speed:
`linear_interpolation_type`). A sequence is a finite clip, and a player repeats it: one that
comes back says its way back as waypoints. `loop=` and the `spline` ease are refused by name. A
sequence never moves the build. The viewer plays an `.xbf`'s sequences from its Motion section, each frame the
values the GLB baker keys at that time, posed by the page's forward kinematics.

The document keeps the definition (**Kinematics**), never frames. A callable is stored as its
samples, interpolated linearly: eight equal steps over its duration, each step split while the
samples' line strays from the function by more than half the tolerance at any eighth of it --
the tolerance 1e-3 radian for an angle, 1e-3 of the model's size (its bounding box's diagonal,
from the B-rep's geometry) for a distance -- at most 4,097 samples. A step is split where it
strays most: a kink, where two straight runs meet, is the error's peak between two checks, so
the samples close in on it, and the half tolerance at the checks keeps the line within the whole
one between them (a zigzag with kinks off the grid is held within 0.55 of it, `sin` within 0.44,
where the quarter checks and middle splits let a kink stray to 1.06). The same code
samples at the same times, so the file is a function of the code. A sequence naming a
mechanism state or a joint its assembly lacks fails the build by name; one setting a value its
pair cannot take, or moving a pair that closes a loop, is left out and warned.
A warm build that changes only a sequence rewrites the mechanism's subtree and converts no
prototype; the file is the cold build's bytes.

Every build whose body ran samples its functions again; one that replayed it reuses the samples
its run's harvest made (**Body retention**). The files a function opens while it is
sampled are heard as a body's reads are (`kernel/memo.py`, `listened`), held to their bytes, and
are the model's inputs (**Build closure**): a document is not taken from memory or its file
once one changed, and a replayed body's harvest is not reused. A function reading what is no
regular file, or reading past the engine's readers, leaves the model's closure with no key, as a
body that does, and is sampled on every build.
