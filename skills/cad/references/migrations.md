# Migrations

Read this file when source, command syntax or sidecars target a different
cadgen version. `cadgen doctor <skill-dir>` compares the installed version with
the skill's pin. A modeling failure alone does not establish version skew.

cadgen uses hard interface cutovers. A retired interface may fail with a
teaching error naming its replacement; it is not a compatibility alias.
The retired inspect CLI is replaced by Python checks using `read_scene` and
native geometry; see [inspection](inspection-and-validation.md).

## Migration messages

A build, snapshot or check can report that a model needs migrating: a sidecar
refused for its schema version, or a retired decorator argument or command named
by a teaching error. The CAD Viewer does not flag such a model: until it is
migrated it loses its kinematics, materials and animation and looks like a plain
part.

- A refused sidecar (`unsupported sidecar schema N (expected M)`) is replaced by
  running the model's script again (`python <model>.py`), which writes a current
  sidecar beside the STEP. An imported STEP that has no script is re-annotated
  with `cadgen step build`; clips need a model script
  ([schema 10](#sidecar-schema-10-animation-is-python-clips)). Editing
  `schemaVersion` by hand does not migrate the content.
- A migrated sidecar declares the current schema and the document's hash, the
  build prints no migration warning, and the model articulates: a
  `cadgen step snapshot --kinematics …` pose differs from rest, and the Viewer
  shows the Position tool (and, for a model with clips, the Animation tool).
- A script that no longer runs on the installed cadgen needs the source changes
  in the sections below.

## When to suspect skew

- **A model script runs, exits 0, and writes nothing.** An older source carries
  no decorated function and no entry point of its own, so Python defines a
  function and exits. Nothing looks for an entry point by name.
- **A command or flag you are sure of comes back unknown**, and the help lists
  an unfamiliar set. Building a model is running its script; there is no
  generation verb. The error names any replacement.
- **A sidecar is refused for its schema version.** Sidecars are never upgraded
  in place and never partially read, because a wrong-shaped one would cost a
  model its kinematics silently.
- **A model that used to articulate renders inert**, presenting as a plain
  document with no pose and no animation. Nothing is discovered by convention:
  kinematics and animation are `kinematics=` and `animation=` on the model's
  decorator, and the build puts both in the document's sidecar. A JavaScript
  file beside the document is read by nothing.
- **Meshes come out visibly coarser or finer, with no error.** Mesh tolerance
  kept its name and changed meaning — chord tolerance is a fraction of the
  component's bounding diagonal, not an absolute length — so a value carried
  across from an older project is wrong in proportion to the part's own size.
  A carried-over value above `0.05` is refused outright with the conversion
  (X mm on a part whose diagonal is D mm is X/D); a smaller one is accepted
  whether or not it suits the part's size.

A migrated source may still have incompatible saved outputs; rebuilding or
re-annotating the document replaces them.

## Sidecar schema 10: animation is Python clips

A schema-10 sidecar carries animation as keyframes the build samples from
Python clips. A schema-9 sidecar is refused, and `@step(animation=...)` refuses
a JavaScript module string (`@step animation= must be a dict of clip id ->
cadgen.clip(update, duration=...), got str`). Port each clip in the module's
`export const clips` to a Python function:

```python
# Before: a JavaScript module in a string
ANIMATION = r"""
export const clips = {
  demo: {
    label: "Demo",
    duration: 8,
    loop: false,
    update(t, m) {
      const angle = 60 * (1 - Math.cos(2 * Math.PI * t / 8));
      m.get("forearm").rotate([0, 0, 1], angle, [0, 0, 0]);
      m.get("#o1.3,#o1.4").opacity(0.5);
    },
  },
};
"""
```

```python
# After: Python clips
import math

import cadgen


def demo(t, m):
    angle = 60 * (1 - math.cos(2 * math.pi * t / 8))
    m.get("#forearm").rotate((0, 0, 1), angle, (0, 0, 0))
    m.get("#o1.3", "#o1.4").opacity(0.5)


ANIMATION = {"demo": cadgen.clip(demo, duration=8, loop=False, label="Demo")}
```

- `rotate`, `translate`, `opacity` and `visible` keep their names and
  arguments. `deformTube({rest, path, twistDeg, maxSegmentLength, braid})`
  becomes `deform_tube(rest=..., path=..., twist_deg=...,
  max_segment_length=..., braid=...)`; the paths keep their shape.
- Every target starts with `#`: a bare label becomes `"#label"`, an occurrence
  id is `"#o1.3"`, and a comma list becomes one argument per target. The root
  is named after the STEP file, so a label equal to the file's stem (`arm` in
  `arm.step`) now also names the whole model; its occurrence id names the part
  alone.
- A group's name resolves directly and moves every part beneath it, so a group
  needs no occurrence id.
- The module's unexported helpers and constants become ordinary Python.
- A document annotated with `cadgen step build --animation` has no script to
  rebuild: wrap it in a model script that reads it with `read_step`, and
  declare the clips there.

Then rebuild the model (`python <model>.py`), which writes a schema-10 sidecar.
Targets are checked as it builds: a label no part carries fails the build,
naming the clip and the time.

## Meshes come from cadgen in 0.8

cadgen 0.8 meshes every component itself, with OCCT, and every client draws
those meshes: the CAD Viewer, snapshots and the CAD app no longer tessellate,
and nothing cadgen runs needs Node. A model script needs no change:
`mesh_tolerance`, `mesh_angular_tolerance`, `--mesh-tolerance` and
`--mesh-angular-tolerance` keep their names, units and defaults. What changes:

- The first build or export after upgrading rewrites every STL, 3MF and GLB
  once, with OCCT's triangles: the same surfaces within the same tolerances, in
  different bytes and triangle counts. Compare meshes by geometry, never by
  hash.
- A tolerance outside what cadgen meshes is refused where it enters, before
  anything builds: `mesh_tolerance` below `5e-5` of the bounding diagonal, or
  `mesh_angular_tolerance` below `0.05` or above `1.5708` radians.
- `CADGEN_MESH_CACHE` is gone and nothing reads it: a mesh is an ordinary store
  entry, evicted and rebuilt like the rest.
- Each model's first view or snapshot after upgrading derives its surfaces and
  meshes again, once: both formats moved. What the older cadgen stored is never
  read again; the daemon reclaims it the first time it idles after the
  upgrade, and `cadgen store gc` does it by hand.

## Migration guides

- **cadgen 0.4 → 0.5** — generator functions became decorated model scripts, the
  generation CLI was removed, sidecars and provenance moved, snapshot job JSON
  was re-keyed, and mesh tolerance became relative.
  https://github.com/earthtojake/text-to-cad/blob/main/docs/migrations/migrating-0.4-to-0.5.md
