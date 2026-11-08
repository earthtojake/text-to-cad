# Snapshots

`cad urdf snapshot`, `cad srdf snapshot`, `cad sdf snapshot` and `cad mjcf snapshot` draw the robot to a
PNG still, as the CAD Viewer shows it, rendered by OCCT:

```bash
cad urdf snapshot path/to/robot.urdf review.png
cad urdf snapshot path/to/robot.urdf review.png --pose '{"shoulder_pitch": 30, "gripper_slide": 0.02}'
cad srdf snapshot path/to/robot.srdf review.png
cad srdf snapshot path/to/robot.srdf review.png --pose arm/ready
cad srdf snapshot path/to/robot.srdf review.png --pose '{"shoulder_pitch": 30}'
cad sdf snapshot path/to/robot.sdf review.png
cad sdf snapshot path/to/robot.sdf review.png --pose '{"arm::elbow": 45}'
cad mjcf snapshot path/to/scene.xml review.png --pose home
cad mjcf snapshot path/to/scene.xml review.png --pose '{"joint1": 30, "finger_joint2": 0.02}'
```

## Poses

The robot opens where the CAD Viewer opens it, every joint at zero. `--pose` gives joint values
over that, in degrees (metres for a prismatic joint), each naming a joint a person can drive,
within its limits, or the request is refused before anything renders: a fixed joint or a
`<mimic>` follower is refused by name (a follower follows its leader). Each link is placed by the
viewer's own forward kinematics and drawn in one colour of the Parts palette.

- **URDF**: mimic joints and four-bar linkages are followed; a `<tcad:four_bar>` input is refused
  by name (an input follows its driver; [urdf-four-bar.md](urdf-four-bar.md)).
- **SRDF**: hand it the `.srdf`: it draws the paired URDF's geometry, the same-folder `.urdf`
  whose `<robot name>` matches, exactly as `cad srdf validate` pairs them. No match, or more than one,
  is refused before anything renders, naming the robot name it looked for and the `.urdf` files it
  found. The robot opens at every joint zero, then this SRDF's `home` group state if it declares
  one. `--pose` names a group state (`group/name`, or a name only one group has) or gives joint
  values over that opening pose.
- **SDF**: the server resolves the description first: the frame graph (`relative_to`,
  `attached_to`) into every link's rest placement, a model nested in the model included, its links
  and joints named by scope (`arm::elbow`, the name `--pose` takes). A `revolute` joint with no
  `<limit>` has no limits.
- **MJCF**: the model opens at qpos0 (every control at zero, each joint's `ref`), as MuJoCo opens
  it; `--pose` names a `<keyframe>` key (`home`) or gives joint values over that -- a hinge's in
  degrees, a slide's in metres, around `ref`. A hinge with no `range` has no limits; a `ball` or
  `free` joint is drawn where it is authored and takes no value; a body with several joints is posed
  by each in turn. A linear `<equality><joint>` coupling is followed, as a mimic is.

## What each draws

### URDF and SRDF

A visual is a `box`, `cylinder` or `sphere`, which the server meshes itself, or
a mesh file beside the description (for an SRDF, beside its URDF): an STL or a 3MF (its numbers
scaled by the mesh's `scale`, the same on all three axes) or a GLB (metres). A `package://NAME/...`
mesh is found in the ROS package the description is in: the nearest folder above the `.urdf` named
NAME, or holding a `package.xml` that names it, so keep the description inside its package folder.
A mesh in another format (`.dae`, `.obj`), a remote URI, a package no folder above the description
is, or a missing file is refused by name, and a link mesh that cannot be loaded fails the snapshot
rather than leaving the link out.

### SDF

What the viewer and `cad sdf snapshot` draw is narrower than what the
validator accepts: the server resolves the frame graph into every link's rest placement — the
model's and every model nested in it, whose links, frames and joints it names by scope
(`arm::elbow`, the name `--pose` takes; a nested model is posed in the model it is nested in and
attached to its `canonical_link`, else its first link) — meshes `box`, `cylinder`, `sphere` and
`capsule` itself, and draws a mesh `<uri>` only when it is a local STL, 3MF or GLB file beside the
description or in its ROS package (`package://NAME/...`: the nearest folder above the description
named NAME, or holding a `package.xml` that names it). A `plane`, `heightmap`, `polyline` or
`ellipsoid`, a `model://` or remote URI, a package no folder above the description is, a `.dae`,
`.obj` or `.ply` mesh, a missing file, a scoped name that names nothing, a pose in a rotation
format other than `euler_rpy`, and a joint the stills cannot pose (a `ball` or `universal` joint)
are refused by name; the viewer refuses a model placed by `placement_frame`, and the validator's own
errors refuse the file before anything renders. A link mesh that cannot be loaded fails the
snapshot rather than leaving the link out. No plugin runs: pose joints with `--pose`.

### MJCF

What the viewer and `cad mjcf snapshot` draw is what [mjcf-authoring.md](mjcf-authoring.md) lists:
the geoms of groups 0 to 2 (3 and up are a model's collision geoms, as MuJoCo's own viewer hides
them) -- `sphere`, `capsule`, `cylinder` and `box` meshed by the server, a `plane` with a size as a
thin slab, a `mesh` whose asset is an STL or an OBJ under `meshdir` (the mesh `scale` applied) -- in
the geom's `rgba`, else its material's (a textured material draws MuJoCo's plain grey; no texture
is drawn). Not drawn, each said by `cad mjcf validate`: an unbounded plane (the viewer's grid stands
in for a floor), a heightfield, an SDF geom, an ellipsoid, an inline or MSH mesh, and whatever
`<replicate>`, `<attach>`, `<flexcomp>`, `<flex>` and `<composite>` would expand to. A `.xml` whose
root is not `<mujoco>`, an include that is not there, a mesh file that is not there and the
validator's own errors refuse the file before anything renders.

## Display, camera and annotations

A normal snapshot uses Solid mode, and every snapshot is light, whatever the viewer's theme.
`--display` takes any of the viewer's display modes (`parts`, `xray`, `hidden-line`, `wireframe`,
...), `exploded=AMOUNT`, or the display object: `camera` (projection and focal length) and `clip`
(`{"clip": {"axis": "x", "at": 0.05}}`, `at` in metres, the file's own unit, as the viewer draws
it). `--grid` draws the measuring grid, and `--camera`, `--size-profile`, `--width` and `--height`
frame and size it. A Quick Edit packet from the viewer (inline JSON, saved to a temporary
`.snapshot.json`, or its path) replays with `--annotation <packet> --camera authored`, its job's
`jointValues` given as `--pose`. Inspect supplied annotations before editing. Without annotations,
the captured view is optional context; render it when useful to the request.

## Files

Link meshes are resolved relative to the description, so they must be present: an unhydrated Git
LFS pointer is not a mesh and fails the snapshot. Run `git lfs checkout <mesh dir>` first.

OUT is written exactly as given and must be a `.png`; check the exit status before reading it. Use
`cad urdf snapshot --help` (or `srdf`, `sdf`, `mjcf`) for the complete current interface.
