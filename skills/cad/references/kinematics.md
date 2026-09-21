# CAD kinematics and animation

Read this file when the user asks to articulate, pose, or animate a STEP
model, or when designing or reviewing mates, couplings, pose presets, posed
exports, or animation clips.

There are THREE systems with different lifecycles, deliberately independent:

- **Geometry** is the module's constants and the factory the parameterless
  model calls with them (`WIDTH = 10.0` … `return _bracket(WIDTH)`). Changing
  one re-runs Python and rebuilds the outputs. They are not live in the viewer.
- **Kinematics** is typed mates declared as PURE DATA via `kinematics=` on
  the export decorators. It drives the viewer's pose sliders — no rebuild, no
  Python at render time — and never moves the geometry a model writes. It
  lives in the model's sidecar (`<name>.step.json`, written beside the
  artifact), alongside any intrinsic material appearance.
- **Animation** is choreography declared as a self-contained JavaScript ES
  module string via `animation=` on `@step`. The build embeds it in
  `<name>.step.json`; the viewer, snapshot door, and animated GLB export read
  that document-bound copy. Animated GLB export hashes the source with the clip
  request, so an animation edit invalidates that export. Animation targets
  occurrences directly and knows nothing about mates. Like materials and
  kinematics, it never changes STEP geometry or bytes.

## Kinematics: typed mates

Kinematics is one sidecar section, independent of intrinsic material appearance.
It never moves saved geometry: the declaration describes how the written tree
articulates, and the viewer poses it at render time. A STEP model with no
kinematics, intrinsic material finishes or animation has no sidecar.

One `kinematics=` dict, closed keys `mates` / `couplings` / `poses`, on any of
`@step`/`@stl`/`@glb`/`@threemf`. Each decorator's declaration stands alone
(share a module-level dict; there is no cross-decorator inheritance).

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
  one axis), `fastened` (0-DOF rigid attachment — needed exactly when
  occurrences are SIBLINGS in the instance tree, like a pin that must orbit
  with its carrier; instance-tree children ride for free).
- **`parent`/`child`** are occurrence refs: `#`-prefixed labels (canonical —
  label parts with `cadgen.label_shape`) or occurrence ids. They must resolve
  at build or the build fails; `read_scene(path).leaves()` lists saved geometry occurrences.
  A label resolves **into linked children**: a part labelled inside a
  sub-assembly you call (`#shoulder_yaw_servo` living in `base_link()`'s
  tree) resolves to its occurrence under the link (`o1.1.1`), so an assembly
  can mate parts of a sub-assembly it links without owning their geometry.
  A ref may name a SUBASSEMBLY as well as a part — a labelled group `Compound`
  is an occurrence in the instance tree, and mating it carries every part
  beneath it. That is how a rocker-bogie chain is three mates instead of three
  hundred. `scene.roots` and `occurrence.children` expose those groups. Targets may NEST — a part inside a mated group may carry its
  own mate to a sibling (a servo's output horn bolted to the jaw it drives):
  the DEEPEST mate naming a part owns it and moves it exactly once, and the
  enclosing group carries only what no deeper mate claimed.
- **`axis`** is a selector ref (`axis="#forearm.f2"` — a cylindrical
  face or circular edge yields its axis, a planar face its center+normal) or
  literals (`origin=(x, y, z), direction=(x, y, z)`). Refs resolve ONCE at
  build into world numbers; the viewer does arithmetic, never topology.
- **ZERO IS THE ARTIFACT AS WRITTEN.** Every DOF's rest value is 0 — the
  placement the author built. There is no `default=`; a presentation pose is a
  preset. A model that must be WRITTEN at another configuration is authored
  at that configuration (or is another model): no decorator argument moves
  geometry.
- **`couple(name, {dof: ratio})`** declares a virtual DOF gearing real ones
  linearly and ADDITIVELY (above, setting `curl=x` adds `x` degrees to `elbow`
  and `0.5*x` to `wrist`).
  Exact gear trains are ratio arithmetic, not code.
  A geared member BACK-DRIVES in the viewer: when exactly one coupling gears a
  DOF with a nonzero ratio, its Pose slider reads the effective value
  (own + ratio x coupling), is labelled "driven by <coupling>", and dragging it
  moves the COUPLING — `coupling = (target - own)/ratio`, clamped to the
  coupling's limits — so sliding one gear turns the whole train. A member's own
  value (from a preset or `--kinematics`) is never overwritten, and a DOF geared
  by two couplings stays independent: that inverse is underdetermined, so the
  viewer refuses it rather than guessing a split.
- A declaration needs at least one mate (or coupling): a pose is a set of joint
  values and a joint is what a mate declares, so `poses` alone declare nothing
  and are refused. A part with no joints declares no `kinematics=`.
- **`poses`** are named `{dof: value}` presets — all that remains of "pose"
  as a concept.
- The mate graph is a TREE: one parent mate per occurrence, no cycles.
  Closed-loop linkages (four-bars) are out of scope by design — they need a
  solver; the viewer evaluates pure forward kinematics from the sidecar's
  numbers at render time.

## Annotating a STEP you did not generate

A document with no model script gets its kinematics from
`cadgen step build IN OUT`, whose `--kinematics` takes the whole SPACE — the
same `{mates, couplings, poses}` vocabulary, as inline JSON or a `.json`
path. `--materials` accepts the named material declaration as inline JSON or
a `.json` path, and `--animation` accepts a self-contained JavaScript module
file or source string. The input is read with OCCT and
re-emitted by the canonical writer, so OUT's bytes are deterministic whichever
kernel wrote IN:

```bash
cadgen step build vendor/hinge.step STEP/hinge.step \
  --kinematics '{"mates": [{"name": "swing", "kind": "revolute",
                            "parent": "#body", "child": "#lever",
                            "axis": "#lever.f2", "limits": [0, 90]}],
                 "poses": {"open": {"swing": 45}}}'
```

**Wrapper script or `step build`?** A model that will keep changing belongs in a
script — a thin `@step` function that imports the foreign STEP and re-exports
it, so the kinematics live beside the geometry decisions and every edit is one
`python model.py`. Reach for `step build` when the geometry is fixed and not
yours: a one-shot annotation or canonicalization of a vendor file. Re-running it
is a no-op, editing only these annotations refreshes the sidecar without
re-emitting a byte, and vendor metadata (PMI, GD&T) does not survive the trip.

## Animation: the embedded module

A STEP document may carry one self-contained JavaScript animation module in
its unified sidecar. Author the module as a Python string and pass it to
`@step(animation=...)`. It exports `clips`; an export the renderer does not
know is a load error, never ignored. The module has no imports. For the arm
above, add this constant and update its decorator, keeping the same model body:

```python
ANIMATION = r"""
export const clips = {
  demo: {
    label: "Demo",
    duration: 8,          // seconds
    loop: true,           // default
    update(t, m) {        // called every frame; t in seconds
      const angle = 60 * (1 - Math.cos(2 * Math.PI * t / 8));
      m.get("forearm").rotate([0, 0, 1], angle, [0, 0, 0]);
      m.get("hand").rotate([0, 0, 1], angle, [0, 0, 0]);
    },
  },
};
"""

@step(out="../STEP/arm.step", kinematics=KINEMATICS, animation=ANIMATION)
def arm(): ...
```

- `m.get(target)` takes a LABEL (canonical) or occurrence-id refs
  (`"#o1.3.1"`, comma lists; each id covers its whole subtree). Unknown
  targets THROW — a typo never silently animates nothing. Labels here match
  RENDERED PARTS only: to animate a whole group, name its occurrence id.
- Handles support `.rotate(axis, degrees, origin=[0,0,0])`, `.translate(vec)`,
  `.opacity(0..1)` and `.visible(bool)`. Successive transforms premultiply:
  spin about a part's center first, then orbit the origin, and the spin rides
  the orbit. For flexible swept bodies, see
  [tube deformation and morph export](animation-deformation.md).
- Every frame starts from rest and `update(t)` rebuilds the state — a pure
  function of t, so scrub/loop/seek are free. No wall-clock, no state.
- Animation targets occurrences independently of mates. Rerun the model after
  editing its animation to refresh the sidecar. Literal annotation edits may
  reuse cached geometry; computed or imported annotations can require a rebuild.
  See [annotation caching](step-generation.md#annotation-caching).
- The model build validates and embeds the declaration. A model without
  `animation=` is simply a model without animation.
- Targets are checked at LOAD, against the compiled tree: every clip's
  `update(0, m)` runs once when the module loads, and a label or occurrence
  id no part carries is reported in the viewer's Status tab and in
  `snapshot --animation`'s error — not at the first frame that reaches it.
- Mesh-only models (no `.step`) have no document sidecar; animation is a
  STEP-document concern.

## Reviewing motion

Review motion interactively in the viewer or render a clip video as described
below. For a still of the arm example's configuration, render at DOF values:

```bash
cadgen step snapshot STEP/arm.step tmp/bent.png --kinematics '{"curl": 60}'
```

`--kinematics` is named for the `kinematics=` block it drives, and takes
either spelling: `{dof: value}` JSON, or the NAME of a pose the model
declares under `poses`. A name is checked against the declaration, so a typo
fails with the poses this model actually has:

```bash
cadgen step snapshot STEP/arm.step tmp/bent.png --kinematics bent
```

For still evidence of a CLIP, freeze one frame: `--animation` names a clip
the document sidecar's embedded animation declares and `--time` the
moment in seconds (default 0). The frame
is composed exactly as the viewer composes it: `--kinematics` sets the base
pose, and the clip's `update(t, m)` is evaluated at that time on top of it.
A clip name the model does not declare fails with the clips it has:

```bash
cadgen step snapshot STEP/arm.step tmp/demo_t2.png --animation demo --time 2.0
cadgen step snapshot STEP/arm.step tmp/demo_bent.png --kinematics bent --animation demo --time 2.0
```

In a JSON job the request is one field, `"animation": {"clip": "demo",
"time": 2.0}`, beside `"kinematics"`; the Python door takes the same object
(`step.snapshot(..., animation={"clip": "demo", "time": 2.0})`) or the clip
name with `time=`.

### Rendering the whole clip

`--video` renders the SPAN instead of a moment, into the `.mp4` or `.gif` the
OUT names. Everything else is unchanged — same display or Render settings, camera
and size profile as a still, and the same `--kinematics` base pose underneath:

```bash
cadgen step snapshot STEP/arm.step tmp/demo.mp4 --animation demo --video '{"fps": 30}'
cadgen step snapshot STEP/arm.step tmp/demo.gif --animation demo \
  --video '{"fps": 12, "seconds": 3, "start": 1.5, "quality": "draft"}'
```

The request's keys, all optional:

| key | default | meaning |
| --- | --- | --- |
| `fps` | `30` | frames per second, a whole number 1..120 |
| `seconds` | what is left of the clip from `start` | how much of the clip to render |
| `start` | `0` | seconds into the clip where the video begins; must be inside it |
| `quality` | `review` | `draft`, `review`, or `high` |
| `loop` | `true` | GIF only — an `.mp4` carries no loop count, so `"loop": false` on one is refused |

The span is measured against the clip rather than trusted, because the clip
evaluator ANSWERS a time past the end instead of refusing it: a clip that does
not loop holds its final pose, so an overrunning span buys frames that are all
one still image, and a looping clip wraps, so it renders a different span than
the one asked for. A `start` at or past the end is refused; an explicit
`seconds` that overruns a clip which does not loop renders and warns. Hence the
default: a looping clip gets one whole cycle from wherever it starts, and a clip
that stops gets the part of it that is left. `fps * seconds` is capped at 7200
frames — every frame is a full-size PNG on disk before ffmpeg runs.

Width and height come from `--width`/`--height`/`--size-profile` like any
other render; there is no size key here. `--video` needs `--animation` (it
renders a clip) and refuses `--time` (that freezes one frame instead), and it
needs **ffmpeg** on `PATH` — or `CADGEN_FFMPEG` pointing at one. A missing
encoder is reported before the first frame is drawn, never after minutes of
rendering. A GIF stores its frame delay in hundredths of a second, so a player
shows the nearest rate to the one asked for; `.mp4` is exact.

The camera is fitted ONCE, to everything the clip covers, so the model moves
and the frame does not. That is why a long clip is worth trimming with
`start`/`seconds`: framing the whole of a clip that travels a long way leaves
the interesting part small.

In a JSON job the request is a `"video"` object beside `"animation"`, and a
video job carries exactly one output:

```json
{
  "input": "STEP/arm.step",
  "animation": { "clip": "demo" },
  "video": { "fps": 24, "quality": "high" },
  "outputs": [{ "path": "tmp/demo.mp4", "camera": "iso" }]
}
```

The result names the file and what it covers — `saved video: tmp/demo.mp4
(120 frames, 30 fps, 4s)` — so a wrong clip or a wrong span shows up without
opening it. Still snapshots remain the evidence for a POSE; a video is for
motion a still cannot show.

### Exporting the clip INSIDE a GLB

A video is pixels. `cadgen glb build --animation` writes the motion itself: the
clip is sampled into glTF node animation, so whatever opens the `.glb` — Blender,
a three.js viewer, a browser's model preview — plays it. There is no camera, no
quality and no encoder here, and `fps` means something different: the SAMPLING
rate of the baked keyframes, not a playback rate.

```bash
cadgen glb build STEP/arm.step GLB/animated/arm.glb --animation demo
cadgen glb build STEP/arm.step GLB/animated/arm.glb \
  --animation '{"clip": "demo", "fps": 30, "seconds": 24, "start": 0}'
```

The request is a clip name, or an object whose keys are all optional but `clip`:

| key | default | meaning |
| --- | --- | --- |
| `clip` | — | the clip to bake; required |
| `fps` | `30` | keyframe samples per second, a whole number 1..120 |
| `seconds` | what is left of the clip from `start` | how much of the clip to bake |
| `start` | `0` | seconds into the clip where the span begins; must be inside it |
| `drop` | `[]` | effects to bake STATIC instead of refusing: `opacity`, `visible` |
| `deform` | `refuse` | what to do with `.deformTube()`: `refuse`, `morph`, `rest` |
| `deformTolerance` | `1.0` | `morph` only — millimetres the baked tubes may sit from the clip's own deformation, `0.01`..`10` |

The span is resolved exactly as `--video`'s is — a looping clip defaults to one
whole cycle, a clip that stops gets what is left of it, and `fps * seconds` is
capped at 7200 samples. The exported animation is re-based to zero, so `start`
picks where in the CLIP the span begins and the file still opens at t = 0.

**What glTF carries, and what it will not:**

| clip effect | in the GLB |
| --- | --- |
| `.rotate()` | sampled rotation channel on that occurrence's node |
| `.translate()` | sampled translation channel on the same node |
| `.rotate()` about a pivot | sampled rotation and translation channels |
| `.opacity()` | **refused.** glTF has no animated opacity. `"drop": ["opacity"]` bakes the value at `start` as a material alpha, and warns |
| `.visible()` | **refused.** Same reason. `"drop": ["visible"]` omits whatever is hidden at `start`, and warns — an occurrence dropped this way loses its motion too, because a node that is not in the file cannot be animated |
| `.deformTube()` | **refused by default.** Per-vertex motion, not a node transform. `"deform": "morph"` bakes it as glTF morph targets; see [deformation](animation-deformation.md); `"deform": "rest"` ships those tubes at rest shape and warns |

Nothing is dropped quietly: an effect the file cannot carry stops the export and
names the occurrences, so a hand whose tendons froze on the way out is a refusal
rather than a finished-looking file. Render the clip with
`cadgen step snapshot --animation <clip> --video` when the motion is one of
those — `--video` needs the clip named too, so both flags go together.

For `.deformTube()` authoring, morph fitting, memory limits and braid export
limitations, read [tube deformation and morph export](animation-deformation.md).

The CAD Viewer plays a GLB's embedded rigid, skinned and morph animation through
its Animation tab in both Inspect and Render. These are baked clips: the STEP
sidecar module's procedural controls are not available in the exported GLB.

An animated export writes ONE node per occurrence instead of the flat,
colour-grouped mesh a static one writes, so the file is bigger and its parts are
individually addressable. Only occurrences the clip actually MOVES get channels;
an occurrence held at a constant offset carries it on its node and nothing else.
Freshness folds the clip request and the sidecar animation source into the export's key, so
editing the choreography re-exports even though the STEP has not changed.

`--animation` is GLB's alone, and the CLI is generated from each door's
signature, so `cadgen stl build` and `cadgen 3mf build` have no such flag at all
— they exit 2 with `unrecognized arguments: --animation`. Neither format has
anywhere to put a clip; export it as `.glb`, or render it with
`cadgen step snapshot --animation <clip> --video`.

Animated GLB requires an explicit OUT. A static export without OUT writes one
sibling `.glb` beside the STEP; it does not read model output declarations.
Choose a separate destination for the animated file when retaining both.

Choose pivots and axes for the intended motion. For hinged motion, use the
physical hinge axis. Verify the relevant dimensions, alignments and clearances
with geometry checks.
