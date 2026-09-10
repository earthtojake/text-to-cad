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
  artifact), the one thing a sidecar is written for.
- **Animation** is choreography in the RENDER MODULE beside the document:
  `STEP/<name>.step.js`, next to `<name>.step` and `<name>.step.json`. It is
  authored and committed, discovered by name, loaded by the viewer and the
  snapshot door, and read by NO build — no decorator names it, the sidecar
  carries no copy, the gate has no clause for it. It targets occurrences
  directly and knows nothing about mates. Editing it is a reload in the
  viewer, never a rebuild; editing kinematics never changes the tree either,
  but it does rewrite the sidecar, so a kinematics edit is a (cheap) run.

## Kinematics: typed mates

Kinematics is the ONE thing a model writes a sidecar for, and it never moves
geometry: the declaration describes how the written tree articulates, the
viewer poses it at render time. A model that declares none has no sidecar.

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

@step(out="../STEP/arm.step", kinematics=KINEMATICS)
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
  A label resolves **into linked children**: a part labelled inside a
  sub-assembly you call (`#shoulder_yaw_servo` living in `base_link()`'s
  tree) resolves to its occurrence under the link (`o1.1.1`), so an assembly
  can mate parts of a sub-assembly it links without owning their geometry.
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
  placement the author built. There is no `default=`; a presentation pose is a
  preset. A model that must be WRITTEN at another configuration is authored
  at that configuration (or is another model): no decorator argument moves
  geometry.
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

## Animation: the render module (`<name>.step.js`)

A STEP document may carry ONE JavaScript module beside it, named after the
document: `STEP/arm.step` → `STEP/arm.step.js`. It is the place for
render-only behaviour — today choreography, as the `clips` export below;
other render-only exports will join it, and an export the renderer does not
know is a load ERROR, never ignored. It is an ES module with no imports,
authored by you and COMMITTED even though it lives in a format folder (the
project's `.gitignore` whitelists `*.step.js`; see `project-layout.md`).

```js
// STEP/arm.step.js — beside arm.step; the viewer loads it by name.
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
- No build reads the file. Nothing declares it: drop it beside the document
  and the viewer's Animation tab appears on the next load; delete it and the
  tab goes. A model without one is simply a model without animation.
- Targets are checked at LOAD, against the compiled tree: every clip's
  `update(0, m)` runs once when the module loads, and a label or occurrence
  id no part carries is reported in the viewer's Status tab and in
  `snapshot --animation`'s error — not at the first frame that reaches it.
- Mesh-only models (no `.step`) have no document to sit beside, and so no
  render module; animation is a STEP-document concern.

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
the document's render module (`STEP/arm.step.js`) declares and `--time` the
moment in seconds (default 0). One frame, one clip, one time — there is no sequence output. The frame
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
