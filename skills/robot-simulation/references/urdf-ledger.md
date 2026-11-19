# URDF design ledger

Read this before writing or editing a `.urdf` by hand. The ledger is a comment block that opens the
file and says what the XML cannot: where each number came from, what each frame and sign means, and
what was assumed. A reader audits the file against it without the CAD at hand. A hand-written MJCF
takes the same block.

## In the file

Directly after the XML declaration:

```xml
<?xml version="1.0"?>
<!--
  robot: example_arm | consumers: RViz, MoveIt
  units: metres, kilograms, radians | frames: +X forward, +Y left, +Z up (REP 103)
  root: base_footprint, frame only | dimensions from: STEP/example_arm.step
  links: each frame on its parent joint, axes parallel to the root's at zero; tool0 frame only, on the flange face
  joints: shoulder_pitch about +Y, positive tips the arm forward (toward +X); limits from the servo datasheet
  meshes: 3MF/, one per link in the link's frame, millimetres, scale 0.001
  inertials: solid-primitive formulas at each link's mass
  assumptions:
  - base_link mass 1.2 kg estimated, not weighed
  - tool0 placed from the flange drawing, not measured
-->
```

What each line answers for:

- **frames and links**: the convention, where each link's frame sits and how its axes point, and
  which links are frame only.
- **joints**: for every moving joint, what a positive value does, in words, and where its origin,
  axis and limits came from. The sign of an axis is part of the model, and the words are what the
  sweep is held against ([urdf-checks.md](urdf-checks.md#the-sweep)).
- **meshes**: the source file, its units and the scale that makes them metres; a visual origin that
  is not identity, and why ([meshes.md](meshes.md)).
- **inertials**: each one's source (CAD mass properties, a datasheet, a formula at an assumed mass
  or density, left out on purpose) and how far to trust it ([inertials.md](inertials.md)).
- **assumptions**: one line for every value that was guessed or inferred: a dimension, a mesh's
  units, a sign, an axis, which link is the parent, an offset, a mass, a `package://` path not
  resolved here.

A robot too large for a line a link keeps its per-link and per-joint rows in a README beside the
file, which the block names.

## When information is missing

Where a transform, an axis, a unit or a mass has no source, do not write a precise-looking number.
Keep what the existing file has, ask for the dimension or the CAD, or write an approximation that
says it is one (a frame-only placeholder link, a named constant, an assumptions line), and report
the file as valid in structure and provisional in space.
