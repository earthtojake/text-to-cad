# Snapshots

`cad urdf snapshot` and `cad srdf snapshot` draw the robot to a PNG still, as the viewer shows
it. An MJCF has no snapshot: it is MuJoCo's own file, which no `cad` command draws
([an MJCF](#an-mjcf), below).

```bash
cad urdf snapshot path/to/robot.urdf review.png --pose '{"shoulder_pitch": 30, "gripper_slide": 0.02}'
cad srdf snapshot path/to/robot.srdf review.png --pose arm/ready
```

## Poses

The robot opens where the viewer opens it, every joint at zero. `--pose` gives joint values
over that, in degrees (metres for a prismatic joint), each naming a joint a person can drive and
within its limits, or the request is refused before anything renders: a fixed joint or a `<mimic>`
follower is refused by name (a follower follows its leader).

- **URDF**: mimic joints and four-bar linkages are followed; a `<tcad:four_bar>` input is refused
  by name (an input follows its driver; [urdf-four-bar.md](urdf-four-bar.md)).
- **SRDF**: hand it the `.srdf`. It draws the paired URDF's geometry, the same-folder `.urdf`
  whose `<robot name>` matches, as `cad srdf validate` pairs them; no match, or more than one, is
  refused, naming the robot name it looked for and the `.urdf` files it found. The robot opens at
  this SRDF's `home` group state if it declares one, and `--pose` names a group state
  (`group/name`, or a name only one group has) or gives joint values over that opening pose.

## What each draws

Each visual is drawn in its colour (`--display parts`: each link one colour), its faces alone: a
mesh file carries no edges, and its triangles' folds are drawn only in the line modes
(`hidden-line`, `wireframe`, `xray`).

### URDF and SRDF

A visual is a `box`, `cylinder` or `sphere`, or a mesh file beside the description (for an SRDF,
beside its URDF): an STL or a 3MF (its numbers scaled by the mesh's `scale`, which must be the same
on all three axes) or a GLB (metres). A `package://NAME/...` mesh is found in the ROS package the
description is in ([meshes.md](meshes.md#reference-forms)). A mesh in another format (`.dae`,
`.obj`), a remote URI, a package no folder above the description is, or a missing file is refused
by name: a link mesh that cannot be loaded fails the snapshot rather than leaving the link out. A
mesh that is still a Git LFS pointer fails it without being named: run `git lfs checkout <mesh dir>`
first.

### An MJCF

No `cad` command draws a MuJoCo model's file. In its place:

- **The robot's kinematics, posed**: snapshot the CAD model it was generated from (`cad model snapshot
  "$ID" out.png --pose home`) or the URDF exported beside it (`cad urdf snapshot robot.urdf out.png
  --pose '{"elbow": 45}'`): the same links, joints and zero.
- **What it collides as**: the `collisions` and `excludes` lines of `cad mujoco check`
  ([mjcf-checks.md](mjcf-checks.md#what-collides-and-the-excludes)), which say exactly what a MuJoCo
  function left colliding, as a picture of boxes inside meshes does not.
- **The model as MuJoCo compiles and simulates it**: the person opens it in MuJoCo Studio (`cad run
  mujoco-studio --model path/to/scene.xml`).

## Display, camera and annotations

`cad urdf snapshot --help` lists the display modes, the camera forms and the sizes. What it does not
say:

- A robot file carries each part's colour and its material's name, not the material's look. `cad
  model snapshot` draws a metal's sheen (its flat faces dark where they mirror the studio's dark
  side, so a grey arm shows black panels), and the URDF's still draws the same parts in flat
  colours: compare the two by shape and pose, not by shading.
- A clip's `at` is in metres, the file's own unit: `--display '{"clip": {"axis": "x", "at": 0.05}}'`.
- The `--camera` presets look along the file's axes as a CAD view does: `front` from -Y, `back` from
  +Y, `right` from +X, `left` from -X, `top` from +Z, `bottom` from -Z, `iso` from above at a corner.
  A robot facing +X, as ROS lays one out (REP 103: X forward, Y left), shows its face to `--camera
  right` and its right side to `--camera front`.
- A Quick Edit packet from the viewer (inline JSON, saved to a temporary `.snapshot.json`, or its
  path) is drawn again as it was, pose and ink included, with `--job <packet>`. `--annotation
  <packet> --camera authored` draws its ink in its view over another pose or display.
