# CAD kinematics and animation

Read this file when the user asks to articulate, pose, or animate a STEP
model, or when designing or reviewing mates, couplings, pose presets, posed
exports, or animation clips.

Three independent systems:

- **Geometry** is the model's constants and factory; changing it rebuilds the
  outputs. It is not live in the viewer.
- **Kinematics** is typed mates declared as data via `kinematics=`. It drives
  the viewer's pose sliders at render time and never moves the geometry a model
  writes.
- **Animation** is Python clips passed to `@step(animation=...)`, sampled into
  keyframes when the model builds. It targets occurrences directly and knows
  nothing about mates.

Both live in the STEP's sidecar (`<name>.step.json`); neither changes STEP bytes.

## Kinematics: typed mates

One `kinematics=` dict, closed keys `mates` / `couplings` / `poses`, on any of
`@step`/`@stl`/`@glb`/`@threemf`. Each decorator's declaration stands alone
(share a module-level dict).

```python
import cadgen
from cadgen import step
from cadgen import build123d as bd

KINEMATICS = {
    "mates": [
        cadgen.revolute("elbow", parent="#upper_arm", child="#forearm",
                        origin=(0, 0, 0), direction=(0, 0, 1), limits=(0, 150)),
        cadgen.revolute("wrist", parent="#forearm", child="#hand",
                        origin=(80, 0, 0), direction=(0, 0, 1), limits=(0, 90)),
    ],
    "couplings": [cadgen.couple("curl", {"elbow": 1, "wrist": 0.5}, limits=(0, 90))],
    "poses": {"straight": {"curl": 0}, "bent": {"curl": 60}},
}

@step(out="../STEP/arm.step", kinematics=KINEMATICS)
def arm():
    upper_arm = bd.Pos(-40, 0, 0) * bd.Box(80, 10, 10)
    forearm = bd.Pos(40, 0, 0) * bd.Box(80, 10, 10)
    hand = bd.Pos(90, 0, 0) * bd.Box(20, 10, 10)
    upper_arm.label, forearm.label, hand.label = "upper_arm", "forearm", "hand"
    return bd.Compound(children=[upper_arm, forearm, hand], label="arm")


if __name__ == "__main__":
    arm()
```

- **Mate kinds**: `revolute` (degrees about an axis), `slider` (model units
  along it), `cylindrical` (sub-DOFs `<name>.turn` and `<name>.travel` about
  one axis), `fastened` (0-DOF rigid attachment, needed exactly when
  occurrences are SIBLINGS in the instance tree, like a pin that must orbit
  with its carrier; instance-tree children ride for free).
- **Limits** are required for every DOF a mate declares, finite at both ends:
  `(lo, hi)` for `revolute` and `slider` (a free joint takes `(-180, 180)`), a
  pair for both sub-DOFs of a `cylindrical` mate
  (`limits={"turn": (0, 360), "travel": (0, 40)}`). A coupling without limits
  spans `(0, 1)`. A pose or `--kinematics` value outside a DOF's limits is
  refused.
- **`parent`/`child`** are `#`-prefixed labels or occurrence ids, and must name
  exactly one occurrence. A label resolves into linked children (a part labelled
  inside a sub-assembly you call resolves under the link), and may name a labelled
  group `Compound`, which carries every part beneath it. Targets may nest: the
  deepest mate naming a part moves it, and the enclosing group carries only what
  no deeper mate claimed.
- **`axis`** is a selector ref (`axis="#forearm.f2"`: a cylindrical face or
  circular edge gives its axis, a planar face its centre and normal) or literals
  (`origin=(x, y, z), direction=(x, y, z)`), resolved once at build into numbers.
- **Zero is the artifact as written**: every DOF's rest value is 0, the placement
  the author built. A presentation pose is a preset; a model that must be written
  at another configuration is authored at it.
- **`couple(name, {dof: ratio})`** declares a virtual DOF that gears real ones
  linearly and additively (above, `curl=x` adds `x` degrees to `elbow` and
  `0.5*x` to `wrist`). In the viewer, a DOF geared by exactly one coupling
  back-drives it: dragging that DOF's slider moves the coupling.
- **`poses`** are named `{dof: value}` presets. A declaration needs at least one
  mate or coupling.
- The mate graph is a tree: one parent mate per occurrence, no cycles. Closed
  loops (four-bars) need a solver and are out of scope; the viewer plays forward
  kinematics.

## Annotating a STEP you did not generate

`cadgen step build IN OUT` gives a document with no model script its kinematics
(`--kinematics`: the same `{mates, couplings, poses}` as inline JSON or a `.json`
path) and materials (`--materials`), re-emitting IN through the canonical writer
([re-emitting](step-generation.md#re-emitting-a-foreign-step-as-your-own)).
Clips need a model script: a thin wrapper that reads the foreign STEP.

```bash
cadgen step build vendor/hinge.step STEP/hinge.step \
  --kinematics '{"mates": [{"name": "swing", "kind": "revolute",
                            "parent": "#body", "child": "#lever",
                            "axis": "#lever.f2", "limits": [0, 90]}],
                 "poses": {"open": {"swing": 45}}}'
```

## Animation: clips baked to keyframes

A clip is a Python function, `update(t, m)`, that poses the model at `t`
seconds through `m`, the model handle. Declare it with `cadgen.clip` and pass a
dict of clip id → clip to `@step(animation=...)`:

```python
import cadgen
from cadgen import build123d as bd
from cadgen import step

SPINNER_X = 30.0  # where the spinner stands on the platter


def demo(t, m):
    turn = 90 * t  # degrees at t seconds: one platter turn every 4 s
    m.get("#spinner").rotate((0, 0, 1), 4 * turn, (SPINNER_X, 0, 0))  # about its own axis,
    m.get("#platter", "#spinner").rotate((0, 0, 1), turn)            # then the platter carries it


ANIMATION = {"demo": cadgen.clip(demo, duration=4, label="Demo")}


@step(out="../STEP/turntable.step", animation=ANIMATION)
def turntable():
    base = bd.Cylinder(50, 6)
    base.label = "base"
    platter = bd.Pos(0, 0, 5) * bd.Cylinder(45, 4)
    platter.label = "platter"
    spinner = bd.Pos(SPINNER_X, 0, 11) * bd.Box(10, 6, 8)
    spinner.label = "spinner"
    return bd.Compound(children=[base, platter, spinner], label="turntable")


if __name__ == "__main__":
    turntable()
```

The build samples each clip at `fps` from `t = 0` to `t = duration` into
keyframes in the sidecar; the viewer, snapshots and GLB export interpolate them,
and nothing runs a clip after the build.

- `cadgen.clip(update, *, duration, loop=True, label=None, fps=60)`: `duration`
  in seconds; `loop=False` holds the last pose; `label` is the name the viewer
  lists (the clip id when omitted). `fps` is the sampling rate, not a playback
  rate: raise it when the build reports a part turning more than 90 degrees
  between samples, or when an abrupt motion (an impact, a snap) looks rounded
  off. The viewer opens on the first clip in the dict.
- `update(t, m)` must be a pure function of `t`: every sample starts from rest,
  so no state between calls, no clock, no randomness.
- `m.get(*targets)` returns one handle on every occurrence its targets name. A
  target is `"#name"` (every part or group with that name; a group moves
  everything beneath it) or an occurrence id such as `"#o1.2"` (that occurrence's
  subtree). Targets resolve against the written document's tree, the names and
  ids the viewer shows and `read_scene` reports; `m.labels()` lists the names. An
  assembly's root is named after the file it is written to, so in `arm.step` the
  target `#arm` also names the root and moves the whole model.
- A handle's methods chain: `.rotate(axis, degrees, origin=(0, 0, 0))`,
  `.translate(vector)`, `.transform(matrix)` (a rigid 4x4, row-major,
  translation in the last column), `.opacity(value)` (0..1), `.visible(flag)`,
  and `.deform_tube(...)` for flexible swept bodies
  ([tube deformation](animation-deformation.md)).
- Transform calls premultiply: a later call acts in world space on the part as
  already moved. Above, the spinner turns about its own axis first and the
  platter's turn then carries it; in the other order the spin would pivot about
  the world point where the spinner started.
- A clip that cannot be baked fails the build, naming the clip and the time
  (`animation clip 'demo' at t=0 s: animation target '#spiner' names no part or
  group; names: #base, #platter, #spinner, #turntable`), as does an exception
  raised in `update`.
- A clip plays on top of the current pose, in world space, independently of
  mates. Animation is declared on `@step` alone: mesh-only models have no
  sidecar.

## Reviewing motion

The viewer plays motion interactively; a snapshot renders a pose, a clip frame
or a clip video. `--kinematics` takes `{dof: value}` JSON or the name of a
declared pose; `--animation` names a clip and `--time` the moment in seconds
(default 0), played on top of the `--kinematics` pose. Unknown poses and clips
fail with the ones the model has.

```bash
cadgen step snapshot STEP/arm.step tmp/bent.png --kinematics '{"curl": 60}'
cadgen step snapshot STEP/arm.step tmp/bent.png --kinematics bent
cadgen step snapshot STEP/turntable.step tmp/demo_t1.png --animation demo --time 1.0
```

In a JSON job the request is `"animation": {"clip": "demo", "time": 2.0}` beside
`"kinematics"` ([flags and job keys](snapshot-review.md#flags-and-job-keys)).

### Rendering the whole clip

`--video` renders a span of the clip into the `.mp4` or `.gif` OUT names, with
the same display settings, camera and size as a still:

```bash
cadgen step snapshot STEP/turntable.step tmp/demo.mp4 --animation demo --video '{"fps": 30}'
cadgen step snapshot STEP/turntable.step tmp/demo.gif --animation demo \
  --video '{"fps": 12, "seconds": 2, "start": 1, "quality": "draft"}'
```

| key | default | meaning |
| --- | --- | --- |
| `fps` | `30` | frames per second, a whole number 1..120 |
| `seconds` | what is left of the clip from `start` | how much of the clip to render |
| `start` | `0` | seconds into the clip where the video begins; must be inside it |
| `quality` | `review` | `draft`, `review`, or `high` |
| `loop` | `true` | GIF only; `"loop": false` on an `.mp4` is refused |

A looping clip defaults to one whole cycle, and a clip that stops to what is left
of it; an explicit `seconds` that overruns a clip that stops renders and warns.
`fps * seconds` is capped at 7200 frames. `--video` needs `--animation`, refuses
`--time`, and needs ffmpeg on `PATH` (or `CADGEN_FFMPEG`). The camera is fitted
once to everything the clip covers, so trimming a long clip with
`start`/`seconds` keeps the subject large. In a JSON job the request is a
`"video"` object beside `"animation"`, with exactly one output:

```json
{
  "input": "STEP/turntable.step",
  "animation": { "clip": "demo" },
  "video": { "fps": 24, "quality": "high" },
  "outputs": [{ "path": "tmp/demo.mp4", "camera": "iso" }]
}
```

### Exporting the clip INSIDE a GLB

`cadgen glb build --animation` writes the clip's own keyframes into the file as
glTF animation, so Blender, three.js or a browser's model preview plays what the
CAD Viewer plays. It needs an explicit OUT; STL and 3MF have no animation export.

```bash
cadgen glb build STEP/turntable.step GLB/animated/turntable.glb --animation demo
cadgen glb build STEP/turntable.step GLB/animated/turntable.glb \
  --animation '{"clip": "demo", "seconds": 8, "start": 0}'
```

| key | default | meaning |
| --- | --- | --- |
| `clip` | — | the clip to export; required |
| `seconds` | what is left of the clip from `start` | how much of the clip to export |
| `start` | `0` | seconds into the clip where the span begins; must be inside it |
| `drop` | `[]` | effects to bake static instead of refusing: `opacity`, `visible` |

A looping clip defaults to one cycle and repeats its keys to fill a longer span;
the exported animation starts at t = 0 whatever `start` is.

| clip effect | in the GLB |
| --- | --- |
| `.rotate()`, `.translate()`, `.transform()` | the parts hang under a pivot node whose translation and rotation channels carry the clip's keys (glTF `CUBICSPLINE`) |
| `.deform_tube()` | a glTF skin: joints along the tube's centerline, keyed `LINEAR` ([tube deformation](animation-deformation.md)) |
| `.opacity()` | **refused**: glTF has no animated opacity. `"drop": ["opacity"]` bakes the value at `start` as a material alpha, and warns |
| `.visible()` | **refused**, likewise. `"drop": ["visible"]` omits whatever is hidden at `start` (and its motion), and warns |

An effect the file cannot carry stops the export and names the occurrences; a
clip video carries them. An animated export writes one node per occurrence,
so it is bigger than a static one, and an edited clip re-exports once the model
is rebuilt.
