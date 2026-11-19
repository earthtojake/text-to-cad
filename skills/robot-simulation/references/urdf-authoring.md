# URDF authoring

Read this before writing or editing a `.urdf` by hand. A robot with a CAD model here has its URDF
generated instead ([from-cad.md](from-cad.md)). The frame contract is in
[SKILL.md](../SKILL.md#author-by-hand) and the checks in [urdf-checks.md](urdf-checks.md); this is
what `cad` reads of a URDF, and the conventions that keep a hand-written one auditable.

## What cad reads

- **Joints**: `fixed`, `revolute`, `continuous` and `prismatic`. A `floating` or `planar` joint is
  refused by `cad urdf validate`, by the snapshot and by the CAD Viewer. A base that moves stays the
  root link, and its freedom is the SRDF's `<virtual_joint>`
  ([srdf-authoring.md](srdf-authoring.md#elements)).
- **Geometry**: one `box`, `cylinder`, `sphere` or `mesh` in each `<visual>` and `<collision>`, and
  as many of either as the link needs. Mesh formats, units and paths are in [meshes.md](meshes.md).
- **Couplings**: a follower at a fixed ratio is `<mimic>`. A four-bar, which no ratio closes, takes
  a `cad` extension ([urdf-four-bar.md](urdf-four-bar.md)).

## Conventions

- **The ledger opens the file**, as a comment after the XML declaration
  ([urdf-ledger.md](urdf-ledger.md)).
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
  ([urdf-frames.md](urdf-frames.md), [urdf-checks.md](urdf-checks.md#the-sweep)).
