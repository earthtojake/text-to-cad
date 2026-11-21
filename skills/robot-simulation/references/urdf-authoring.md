# URDF authoring

Read this before writing or editing a `.urdf` by hand. A robot with a CAD model here has its URDF
generated instead ([from-cad.md](from-cad.md)). The frame contract is in
[SKILL.md](../SKILL.md#author-by-hand) and the checks in [urdf-checks.md](urdf-checks.md); this is
what `cad` reads of a URDF, and the conventions that keep a hand-written one auditable.

## What cad reads

- **Joints**: `fixed`, `revolute`, `continuous` and `prismatic`. A `floating` or `planar` joint is
  refused by `cad urdf validate`, by the snapshot and by the viewer. A base that moves stays the
  root link, and its freedom is the SRDF's `<virtual_joint>`
  ([srdf-authoring.md](srdf-authoring.md#elements)).
- **Geometry**: one `box`, `cylinder`, `sphere` or `mesh` in each `<visual>` and `<collision>`, and
  as many of either as the link needs. Mesh formats, units and paths are in [meshes.md](meshes.md).
- **Couplings**: a follower at a fixed ratio is `<mimic>`. A four-bar, which no ratio closes, takes
  a `cad` extension ([urdf-four-bar.md](urdf-four-bar.md)).

## Conventions

- **The ledger opens the file**, as a comment after the XML declaration ([The ledger](#the-ledger)).
- **Links, then joints**, each in tree order from the root, so the file reads as the tree does.
- **A frame-only link** (`base_footprint`, `tool0`, an optical frame) is an empty element, and the
  ledger says it is one, so its missing geometry and inertial read as intent.
- **A link and a joint never share a name.** A shared name is legal, but a tool that keeps both in
  one namespace refuses the file, and the validator warns: the link `elbow_link`, the joint `elbow`.
- **Every revolute and prismatic `<limit>` gives `effort` and `velocity`**, from the drive's
  datasheet. A ROS controller reads a 0 literally, and the validator warns of one omitted or 0.
- **Meshes come first**: one per link, in the link's frame, before the XML that places it
  ([meshes.md](meshes.md)).
- **Every moving joint's positive motion is written in the ledger and swept**
  ([Frames and signs](#frames-and-signs), [urdf-checks.md](urdf-checks.md#the-sweep)).

## Frames and signs

The frame contract is in [SKILL.md](../SKILL.md#author-by-hand). These are the two places it is misread,
and no validator sees either.

- **Positive rotation is right-handed about the axis, whatever the joint is called.** With +X
  forward, +Y left and +Z up, a positive turn about +Y tips an upright link forward and a forward
  link down. A pitch joint that should raise a forward link for positive values takes
  `<axis xyz="0 -1 0"/>`. Write each joint's positive motion in [the ledger](#the-ledger) and sweep it
  ([urdf-checks.md](urdf-checks.md#the-sweep)).
- **The axis is in the joint frame, so the joint origin's `rpy` turns it.** `<axis xyz="0 0 1"/>`
  under `rpy="1.5708 0 0"` turns about the parent's -Y. Where the mechanism allows, leave joint
  origins unrotated and give each axis as a signed principal direction (`1 0 0`, `0 -1 0`): it then
  reads the same in the parent's frame. An axis that is not principal is a reason to check the
  frames again before accepting it.

## The ledger

The ledger is a comment block that opens the file and says what the XML cannot: where each number came
from, what each frame and sign means, and what was assumed. A reader audits the file against it without
the CAD at hand. A hand-written MJCF takes the same block. Directly after the XML declaration:

```xml
<?xml version="1.0"?>
<!--
  robot: example_arm | consumers: RViz, MoveIt
  units: metres, kilograms, radians | frames: +X forward, +Y left, +Z up (REP 103)
  root: base_footprint, frame only | dimensions from: STEP/example_arm.step
  links: each frame on its parent joint, parallel to the root at zero; tool0 frame only, on the flange
  joints: shoulder_pitch about +Y, positive tips the arm forward (+X); limits from the servo datasheet
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
  is not identity, and why; what stands in for the mesh as the collision ([meshes.md](meshes.md)).
- **inertials**: each one's source (CAD mass properties, a datasheet, a formula at an assumed mass
  or density, left out on purpose) and how far to trust it ([inertials.md](inertials.md)).
- **assumptions**: one line for every value that was guessed or inferred: a dimension, a mesh's
  units, a sign, an axis, which link is the parent, an offset, a mass, a `package://` path not
  resolved here.

A robot too large for a line per link keeps its per-link and per-joint rows in a README beside the
file, which the block names.

## When information is missing

Where a transform, an axis, a unit or a mass has no source, do not write a precise-looking number.
Keep what the existing file has, ask for the dimension or the CAD, or write an approximation that
says it is one (a frame-only placeholder link, a constant named as assumed, an assumptions line),
and report the file as valid in structure and provisional in space.
