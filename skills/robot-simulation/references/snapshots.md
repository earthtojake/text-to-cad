# Snapshots

`cad urdf snapshot` and `cad srdf snapshot` draw the robot to a PNG still, as the CAD Viewer shows
it, rendered by OCCT. An MJCF has no snapshot: it is MuJoCo's own file, which no `cad` command
draws ([an MJCF](#an-mjcf), below).

```bash
cad urdf snapshot path/to/robot.urdf review.png
cad urdf snapshot path/to/robot.urdf review.png --pose '{"shoulder_pitch": 30, "gripper_slide": 0.02}'
cad srdf snapshot path/to/robot.srdf review.png
cad srdf snapshot path/to/robot.srdf review.png --pose arm/ready
cad srdf snapshot path/to/robot.srdf review.png --pose '{"shoulder_pitch": 30}'
```

## Poses

The robot opens where the CAD Viewer opens it, every joint at zero. `--pose` gives joint values
over that, in degrees (metres for a prismatic joint), each naming a joint a person can drive,
within its limits, or the request is refused before anything renders: a fixed joint or a
`<mimic>` follower is refused by name (a follower follows its leader). Each link is placed by the
viewer's own forward kinematics and drawn in its visuals' colours (`--display parts`: each link
one colour of the Parts palette).

- **URDF**: mimic joints and four-bar linkages are followed; a `<tcad:four_bar>` input is refused
  by name (an input follows its driver; [urdf-four-bar.md](urdf-four-bar.md)).
- **SRDF**: hand it the `.srdf`: it draws the paired URDF's geometry, the same-folder `.urdf`
  whose `<robot name>` matches, exactly as `cad srdf validate` pairs them. No match, or more than one,
  is refused before anything renders, naming the robot name it looked for and the `.urdf` files it
  found. The robot opens at every joint zero, then this SRDF's `home` group state if it declares
  one. `--pose` names a group state (`group/name`, or a name only one group has) or gives joint
  values over that opening pose.

## What each draws

Each visual is drawn in its colour, its faces alone as the CAD Viewer draws a robot: a mesh file
carries no edges, and its triangles' folds are drawn only in the line modes (`hidden-line`,
`wireframe`, `xray`).

### URDF and SRDF

A visual is a `box`, `cylinder` or `sphere`, which the server meshes itself, or
a mesh file beside the description (for an SRDF, beside its URDF): an STL or a 3MF (its numbers
scaled by the mesh's `scale`, the same on all three axes) or a GLB (metres). A `package://NAME/...`
mesh is found in the ROS package the description is in: the nearest folder above the `.urdf` named
NAME, or holding a `package.xml` that names it, so keep the description inside its package folder.
A mesh in another format (`.dae`, `.obj`), a remote URI, a package no folder above the description
is, or a missing file is refused by name, and a link mesh that cannot be loaded fails the snapshot
rather than leaving the link out.

### An MJCF

No `cad` command draws a MuJoCo model's file. What to use in its place:

- **The robot's kinematics, posed**: snapshot the CAD model it was generated from (`cad model snapshot
  "$ID" out.png --pose home`) or the URDF exported beside it (`cad urdf snapshot robot.urdf out.png
  --pose '{"elbow": 45}'`): the same links, joints and zero.
- **What it collides as**: read `cad mujoco check` ([mjcf-checks.md](mjcf-checks.md#what-collides-and-the-excludes)):
  the collision geoms by kind and by body, and each contact exclude with how its two bodies stand at
  rest; `--json` has every geom's kind and size. A table says exactly what a MuJoCo function left
  colliding, which a picture of boxes inside meshes does not.
- **The model as MuJoCo compiles and simulates it**: the person opens it in MuJoCo Studio (`cad run
  mujoco-studio --model path/to/scene.xml`).

## Display, camera and annotations

A normal snapshot uses Solid mode, and every snapshot is light, whatever the viewer's theme. A
robot file carries each part's colour and its material's name, not the material's look: a `cad model
snapshot` draws a metal's sheen (its flat faces dark where they mirror the studio's dark side, so a
grey arm shows black panels), while the URDF's still draws the same parts in their flat
colours. The two compare by shape and pose, not by shading.
`--display` takes any of the viewer's display modes (`parts`, `xray`, `hidden-line`, `wireframe`,
...), `exploded=AMOUNT`, or the display object: `camera` (projection and focal length) and `clip`
(`{"clip": {"axis": "x", "at": 0.05}}`, `at` in metres, the file's own unit, as the viewer draws
it). `--grid` draws the measuring grid, `--preview` draws the robot lit in a studio in place of a
display mode (the picture for a person), and `--camera`, `--size-profile`, `--width` and `--height`
frame and size it. The `--camera` presets look along the file's axes as a CAD view does: `front`
from -Y, `back` from +Y, `right` from +X, `left` from -X, `top` from +Z, `bottom` from -Z, `iso` from
above at a corner. A robot facing +X, as ROS lays one out (REP 103: X forward, Y left), shows its face
to `--camera right` and its right side to `--camera front`. A Quick Edit packet from the viewer (inline JSON, saved to a temporary
`.snapshot.json`, or its path) replays with `--annotation <packet> --camera authored`, its job's
`jointValues` given as `--pose`. Inspect supplied annotations before editing. Without annotations,
the captured view is optional context; render it when useful to the request.

## Files

Link meshes are resolved relative to the description, so they must be present: an unhydrated Git
LFS pointer is not a mesh and fails the snapshot. Run `git lfs checkout <mesh dir>` first.

OUT is written exactly as given and must be a `.png`; check the exit status before reading it. Use
`cad urdf snapshot --help` (or `srdf`) for the complete current interface.
