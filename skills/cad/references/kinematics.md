# CAD kinematics and animation

Read this file when the user asks to articulate, pose, or animate a STEP
model, or when designing or reviewing mates, couplings, pose presets, posed
exports, or animation clips.

There are THREE systems with different lifecycles, deliberately independent:

- **Geometry** is the module's constants and the factory the parameterless
  model calls with them (`WIDTH = 10.0` … `return _bracket(WIDTH)`). Changing
  one re-runs Python and rebuilds the outputs. They are not live in the viewer.
- **Kinematics** is typed mates declared as PURE DATA via `kinematics=` on
  the export decorators. It drives the viewer's pose sliders and bakes posed
  exports — no rebuild, no Python at render time. It lives in the model's
  sidecar (`<name>.step.json`, written beside the artifact).
- **Animation** is choreography in a plain `.js` module declared via
  `@step(animation="<name>.anim.js")`, whose TEXT is copied into the same
  sidecar. It targets occurrences directly and knows nothing about mates.
  Editing kinematics or animation never changes the model's tree and never
  dirties an export — but the `.anim.js` IS a build input: editing it makes
  the model stale, and the next run refreshes the sidecar's copy.

## Kinematics: typed mates

One `kinematics=` dict, closed keys `mates` / `couplings` / `poses` / `at`, on
any of `@step`/`@stl`/`@glb`/`@threemf`. Each decorator's declaration stands
alone (share a module-level dict; there is no cross-decorator inheritance).
`at` is the bake point and is covered below; the other three are the space.

```python
import cadgen
from cadgen import step
from cadgen import build123d as bd

KINEMATICS = {
    "mates": [
        cadgen.revolute("elbow", parent="#upper_arm", child="#forearm",
                        axis="#forearm.pivot_bore", limits=(0, 150)),
        cadgen.slider("extend", parent="#rail", child="#carriage",
                      axis="#rail.f2", limits=(0, 80)),
        cadgen.cylindrical("lead", parent="#housing", child="#screw",
                           axis="#screw.f1",
                           limits={"turn": (0, 3600), "travel": (0, 40)}),
        cadgen.fastened("mount", parent="#carriage", child="#bracket"),
    ],
    "couplings": [cadgen.couple("curl", {"mcp": 50, "pip": 70, "dip": 40})],
    "poses": {"open": {"jaw": 40}, "closed": {"jaw": 0}},
}

@step(out="../STEP/arm.step", kinematics=KINEMATICS,
      animation="arm.anim.js")
def arm(): ...


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
  at build or the build fails; `cadgen step inspect refs` lists the leaves.
  A ref may name a SUBASSEMBLY as well as a part — a labelled group `Compound`
  is an occurrence in the instance tree, and mating it carries every part
  beneath it. That is how a rocker-bogie chain is three mates instead of three
  hundred; `inspect refs` does not list group refs, because they are not
  rendered parts.
- **`axis`** is a selector ref (`axis="#forearm.pivot_bore"` — a cylindrical
  face or circular edge yields its axis, a planar face its center+normal) or
  literals (`origin=(x, y, z), direction=(x, y, z)`). Refs resolve ONCE at
  build into world numbers; the viewer does arithmetic, never topology.
- **ZERO IS THE ARTIFACT AS WRITTEN.** Every DOF's rest value is 0 — the
  placement the author built (or the baked pose, below). There is no
  `default=`; a presentation pose is a preset or a bake.
- **`couple(name, {dof: ratio})`** declares a virtual DOF gearing real ones
  linearly and ADDITIVELY (setting `curl=x` adds `50*x` degrees to `mcp`).
  Exact gear trains are ratio arithmetic, not code.
  A geared member BACK-DRIVES in the viewer: when exactly one coupling gears a
  DOF with a nonzero ratio, its Pose slider reads the effective value
  (own + ratio x coupling), is labelled "driven by <coupling>", and dragging it
  moves the COUPLING — `coupling = (target - own)/ratio`, clamped to the
  coupling's limits — so sliding one gear turns the whole train. A member's own
  value (from a preset or `--kinematics`) is never overwritten, and a DOF geared
  by two couplings stays independent: that inverse is underdetermined, so the
  viewer refuses it rather than guessing a split.
- **`poses`** are named `{dof: value}` presets — all that remains of "pose"
  as a concept.
- The mate graph is a TREE: one parent mate per occurrence, no cycles.
  Closed-loop linkages (four-bars) are out of scope by design — they need a
  solver; cadgen evaluates pure forward kinematics, identically in Python
  and the viewer, so a slider position and an exported bake agree to the bit.

## Export at a bake point

EVERYTHING SAYS KINEMATICS: the bake point is the kinematics dict's own `"at"`
key — a preset name or `{dof: value}` — so a declaration stays one object.

```python
@step(out="gripper.step", kinematics={**KINEMATICS, "at": "closed"})
@stl(out="gripper_open.stl", kinematics={**KINEMATICS, "at": "open"})
@stl(out="gripper_closed.stl", kinematics={**KINEMATICS, "at": "closed"})
```

The written artifact is its own q=0: a baked STEP's sidecar shifts limits and
re-zeroes presets to describe the file as written. Mesh bakes are transient —
stl/glb/3mf never have sidecars or animation. The mesh freshness ledger keys
on the bake point, so posed and rest variants never satisfy each other's no-op
gates.

For a ONE-OFF mesh at a configuration the model does not declare, the mesh
doors take the same argument name for the point:

```bash
cadgen stl build STEP/gripper.step tmp/gripper_open.stl --kinematics open
```

## Annotating a STEP you did not generate

A document with no model script gets its kinematics from
`cadgen step build IN OUT`, whose `--kinematics` takes the whole SPACE — the
same `{mates, couplings, poses, at}` vocabulary, as inline JSON or a `.json`
path — and whose `--animation` copies a `.js` module's text into OUT's sidecar.
The input is read with OCCT and re-emitted by the canonical writer, so OUT's
bytes are deterministic whichever kernel wrote IN:

```bash
cadgen step build vendor/hinge.step STEP/hinge.step \
  --kinematics '{"mates": [{"name": "swing", "kind": "revolute",
                            "parent": "#body", "child": "#lever",
                            "axis": "#lever.bore", "limits": [0, 90]}],
                 "poses": {"open": {"swing": 45}}}'
```

**Wrapper script or `step build`?** A model that will keep changing belongs in a
script — a thin `@step` function that imports the foreign STEP and re-exports
it, so the kinematics live beside the geometry decisions and every edit is one
`python model.py`. Reach for `step build` when the geometry is fixed and not
yours: a one-shot annotation or canonicalization of a vendor file. Re-running it
is a no-op, editing only the kinematics refreshes the sidecar without
re-emitting a byte, and vendor metadata (PMI, GD&T) does not survive the trip.

## Animation: the .anim.js contract

```js
// arm.anim.js — beside the model script; TEXT is copied into the sidecar.
export const clips = {
  demo: {
    label: "Demo",
    duration: 8,          // seconds
    loop: true,           // default
    update(t, m) {        // called every frame; t in seconds
      m.get("forearm").rotate([0, 0, 1], 120 * (t / 8), [0, 0, 25]);
      m.get("#o1.3.1,o1.3.2").translate([0, 0, 40 * Math.min(t / 2, 1)]);
      m.get("lid").opacity(t < 5 ? 1 : 1 - (t - 5) / 2);
    },
  },
};
```

- `m.get(target)` takes a LABEL (canonical) or occurrence-id refs
  (`"#o1.3.1"`, comma lists; each id covers its whole subtree). Unknown
  targets THROW — a typo never silently animates nothing. Labels here match
  RENDERED PARTS only: to animate a whole group, name its occurrence id.
- Handles: `.rotate(axis, degrees, origin=[0,0,0])`, `.translate(vec)`,
  `.opacity(0..1)`, `.visible(bool)`. Successive transform calls
  PREMULTIPLY: spin about a part's own center first, then orbit the origin,
  and the spin rides the orbit.
- Every frame starts from rest and `update(t)` rebuilds the state — a pure
  function of t, so scrub/loop/seek are free. No wall-clock, no state.
- Animation is deliberately Turing-complete and deliberately ignorant of
  mates: animating a jointed part re-describes the motion (a few lines of
  ratio math). That independence is what guarantees choreography edits can
  never invalidate builds.
- The declared file must exist (no convention discovery); a missing
  `animation=` target fails the build loudly.

## Reviewing motion

Snapshot renders stills; motion review is interactive in the viewer. For
still evidence of a configuration, render at DOF values:

```bash
cadgen step snapshot STEP/arm.step tmp/open.png --kinematics '{"jaw": 40}'
```

`--kinematics` is named for the `kinematics=` block it drives, and takes
either spelling: `{dof: value}` JSON, or the NAME of a pose the model
declares under `poses`. A name is checked against the declaration, so a typo
fails with the poses this model actually has:

```bash
cadgen step snapshot STEP/arm.step tmp/open.png --kinematics open
```

For still evidence of a CLIP, freeze one frame: `--animation` names a clip
the model's `.anim.js` declares and `--time` the moment in seconds (default
0). One frame, one clip, one time — there is no sequence output. The frame
is composed exactly as the viewer composes it: `--kinematics` sets the base
pose, and the clip's `update(t, m)` is evaluated at that time on top of it.
A clip name the model does not declare fails with the clips it has:

```bash
cadgen step snapshot STEP/arm.step tmp/demo_t2.png --animation demo --time 2.0
cadgen step snapshot STEP/arm.step tmp/demo_open.png --kinematics open --animation demo --time 2.0
```

In a JSON job the request is one field, `"animation": {"clip": "demo",
"time": 2.0}`, beside `"kinematics"`; the Python door takes the same object
(`step.snapshot(..., animation={"clip": "demo", "time": 2.0})`) or the clip
name with `time=`.

Identify fixed pivots, link lengths, gear ratios, and joint limits BEFORE
declaring mates; pivot every rotation about its hinge bore or mate face —
never a bounding-box center. Convert visual concerns into `cadgen step
inspect measure` checks before calling them fixed.
