# Migrations

Read this file when source, command syntax or sidecars target a different
cadgen version. `cadgen doctor <skill-dir>` compares the installed version with
the skill's pin. cadgen cuts interfaces over with no compatibility layer: a
retired command, flag, argument, key or import is gone, and fails the way an
unknown one does (an unknown command, an unrecognized argument, an unknown key,
an `ImportError`) without naming what replaced it. The sections below map old
forms to current ones.

## Migration messages

A build, snapshot or check names one migration itself: a sidecar refused for
its schema version. Source or commands written for an older cadgen fail with the
current contract's ordinary errors instead; compare them with the sections
below. The CAD Viewer does not flag a model whose sidecar is refused: until it is
migrated it shows as a plain part, without its kinematics, materials or
animation.

- A refused sidecar (`unsupported sidecar schema N (expected M)`) is replaced by
  rerunning the model's script (`python <model>.py`). An imported STEP with no
  script is re-annotated with `cadgen step build`; clips need a model script.
  Editing `schemaVersion` by hand does not migrate the content.
- A migrated sidecar declares the current schema and the document's hash, the
  build prints no migration warning, a `cadgen step snapshot --kinematics …`
  pose differs from rest, and the Viewer shows the Position tool (and, for a
  model with clips, the Animation tool).
- Rebuilding or re-annotating a document replaces outputs an older cadgen wrote.

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
    m.get("#o:e8a03d5b61f4", "#o:19c7f2d4a8b5").opacity(0.5)


ANIMATION = {"demo": cadgen.clip(demo, duration=8, loop=False, label="Demo")}
```

- `rotate`, `translate`, `opacity` and `visible` keep their names and
  arguments. `deformTube({rest, path, twistDeg, maxSegmentLength, braid})`
  becomes `deform_tube(rest=..., path=..., twist_deg=...,
  max_segment_length=..., braid=...)`; the paths keep their shape.
- Every target starts with `#`: a bare label becomes `"#label"`, an occurrence
  is named by its token (`"#o:e8a03d5b61f4"`, below), and a comma list becomes
  one argument per target. A label
  several parts share moved them all; now it fails, listing numbered aliases
  (`#wheel_1`, `#wheel_2`) to pass instead.
- A group's name moves every part beneath it, and the module's helpers and
  constants become ordinary Python.
- A document annotated with `cadgen step build --animation` has no script to
  rebuild: wrap it in a model script that reads it with `read_step`, and
  declare the clips there.

Rebuilding the model (`python <model>.py`) writes a current sidecar; a target
no part carries fails the build, naming the clip and the time.

## Refs name geometry in 0.8

A ref was positional: `#o1.2.f7` named the second occurrence under the first and
its seventh face, numbers one saved revision gave them and the next could give to
other geometry. A ref now names what it points at: an occurrence by a **token**
minted from its place in the tree (`#o:4b1f9e2a7c03`) and an element by its
**name**, the operation of the model's code that made it and its number among
the elements that operation made (`#o:4b1f9e2a7c03/f:bracket.make_box1.6`, the
sixth face of the first box the function `bracket` made; a label may stand for
the occurrence, `#housing/f:bracket.make_box1.6`). An element of an imported file,
which no operation of a model made, is named by its geometry instead
(`f:9d2e8c1b5a70`). The old spellings resolve to nothing, as any unknown string
does: `resolve()` raises, a mate's `parent`, `child` or `axis` fails the build,
and a clip's `m.get("#o1.3")` fails the bake. Take the new ones where they are
shown -- the CAD Viewer's copy button, the `ref` of each row
`cadgen step snapshot --mode list` prints, each entity's `ref` from
`read_scene(...).resolve(...).entities(...)` -- and prefer labels, which need no
renaming. The sidecar is schema 11: its mate ends, material assignments and
animation tracks name occurrences by token. A schema-10 sidecar is refused and
is rebuilt by rerunning the model, which binds them anew.

A ref by geometry (`f:` and twelve hexadecimal characters, how an imported
file's elements are named) also finds an element of a part a model made, by its
geometry: `resolve()`, a mate's `axis` and `cadgen store where` take it, and
the viewer and `store where` give the element's name. An element's name moves when
the code that made it moves to another operation (an earlier call of the same
operation added in the same function, in making that part, renumbers the later
ones; an edit to another part renames nothing); a label keeps it in what a later
operation makes of the labelled shape: with `boss.label = "boss"`, the faces
`boss` brings to `plate + boss` are `f:boss.1`, `f:boss.2`, …. A label set after
the shape was used renames nothing already made of it. A labelled part placed in
an assembly keeps its own names, its label naming the occurrence (`#lid`), so
parts made alike and labelled apart are one part.

## Meshes come from cadgen in 0.8

cadgen 0.8 meshes every component itself -- OCCT's triangulation at one display
tolerance, each face checked against its exact surface and meshed again where it
strays -- and every client draws those meshes: the CAD Viewer, snapshots and the
CAD app no longer tessellate, and nothing cadgen runs needs Node.

- `@step` takes no mesh tolerance: delete `mesh_tolerance=` and
  `mesh_angular_tolerance=` from it (`@step got an unexpected keyword argument`).
  A model run (`python <model>.py`) takes no `--mesh-tolerance` or
  `--mesh-angular-tolerance`, and a snapshot job no `quality` key: every view
  and snapshot draws the display tolerance.
- `@stl`/`@glb`/`@threemf` and the export commands keep both tolerances, in the
  same units. An export that names none is written at the display tolerance
  (chord `5e-4` of the bounding diagonal, angle `0.35`), from the meshes the
  viewer draws; a declared export no longer inherits anything from `@step`.

- The first build or export after upgrading rewrites every STL, 3MF and GLB
  once, with OCCT's triangles: the same surfaces within the same tolerances, in
  different bytes. Compare meshes by geometry, not hash.
- A tolerance outside what cadgen meshes is refused before anything builds:
  `mesh_tolerance` below `5e-5` of the bounding diagonal, or
  `mesh_angular_tolerance` below `0.05` or above `1.5708` radians.
- `CADGEN_MESH_CACHE` is gone: a mesh is an ordinary store entry.
- A build now meshes its parts before it reports done, so a view only reads. Each
  model's first `python <model>.py` after upgrading, current or not, meshes its
  parts again, once (`Meshing parts n/total`); a STEP no build has touched since
  is meshed on its first view or snapshot. `cadgen store gc` reclaims what the
  older cadgen stored.

## Saved STEP files are exports in 0.8

- A model's STEP is written from its result by the build pool and checked
  against it: a parse of the file must name every occurrence, face and edge as
  the result does, each body within the display tolerance, drawn alike. The
  file carries those names -- each part's key in its product's description, each
  face's and edge's name on its entity -- for any reader.
- A file whose translation changed a body (OCCT's STEP writer and reader are
  not lossless) shows its own content, its elements named by their geometry.
  The build warns (`<file> does not hold the result it was written from, so it
  shows its own content; ...`): at once with no daemon, at the next touch of the
  file through the daemon. `cadgen store why` says `shows its own content:`, and
  the model's next run writes the file without names (a file already written
  without names is kept until the model changes, or `--force` writes the names
  again).
- Every model rebuilds once after the upgrade and writes its STEP again; a
  rebuild whose result is unchanged keeps the file.

## Snapshot and GLB requests in 0.8

- Section mode is gone: `--mode section` is refused (`Unsupported render mode:
  section. Modes: list, view`), and so are `--section` and a job's `section`
  key. Clip a view and look straight at the cut
  ([cross-sections](snapshot-review.md#cross-sections)): the section plane's
  normal is the clip's `axis` (`XY` is `z`, `XZ` is `y`, `YZ` is `x`), its
  offset is the clip's `at`, and the camera faces the cut (`top`, `back`,
  `right`). A view writes `.png`; nothing writes an SVG outline. So
  `--mode section --section XZ:12.5` becomes:

  ```bash
  cadgen step snapshot STEP/housing.step tmp/cut.png --camera back --display '{"clip": {"axis": "y", "at": 12.5}}'
  ```

- `display.clip` places its plane with `at`, the plane's coordinate on its axis
  in millimetres, in the model's own frame. `offset` and `offsets`, fractions of
  the model's extent along the axis, are refused (`display.clip has unknown
  key(s): offset`). `{"axis": "y", "offset": 0.25}` becomes `{"axis": "y", "at":
  Y}` with `Y = min + 0.25 × (max − min)` over the model's Y extent, which the
  `bounds` that `--mode list` prints give. With no `at` the plane goes through
  the middle. `offsets` kept a fraction for each axis; a clip cuts across its
  one `axis`, so name that axis and its `at`.
- `cadgen glb build --animation` takes no `fps`, `deform` or `deformTolerance`
  (`--animation has unknown key(s): fps; supported keys: clip, drop, seconds,
  start`). The file carries the clip's own keys, not samples at a rate, and
  every bending tube as a glTF skin, so there is no rate or mode to choose:
  delete the keys. `clip`, `seconds`, `start` and `drop` keep their meaning.

## Children build serially, and a parent follows its children by key, in 0.8

A child a parent's body calls is decoded from its stored result when the store
holds one for its inputs as they are, else built there and then, in the parent's
own process, before the call returns. Children build one at a time, in the order
the body calls them; nothing runs in parallel, and the time line counts a child's
build under `children`. A child's STEP is written while its parent's body runs,
and the command returns once every file is written: in the build tree a model's
`done` says its result is recorded, and its file follows. `python model.py
--no-wait` returns at that point -- every result recorded, the preview on screen
-- and the files are written after it has answered.

A parent records each child by its **key** -- a hash of the child (its script and
function) and everything it was built from: its sources, data files, constants,
its own children and the cadgen and kernel versions that built it -- so:

- editing a child's source rebuilds the child AND its parent, even when the
  child's geometry is unchanged. The parent's rerun decodes the child's stored
  result; only the parent's own body runs. `cadgen store why <parent.py>` says
  `child rebuilt: <child.py>`; a child not yet rebuilt reads `child stale`.
- upgrading cadgen or the CAD kernel rebuilds every model once:
  `producer changed: cadgen 0.7.21 -> 0.8.0`.
- bringing a source back to a state already built is a hit: the stored result is
  restored and nothing runs -- for a child too, whose parent is then a hit as well
  and restores the child with its own files.
- deleting a model's STEP (or a declared mesh) beside a current model exports it
  again from the stored result, without running the model.

The record's `children` entries read `{"model", "key"}`; a record from 0.7.21
is not read (its schema is in the key), so the first run of each model after
the upgrade builds it.
