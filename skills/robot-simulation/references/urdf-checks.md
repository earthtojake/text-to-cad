# URDF checks

Read this when a `.urdf` was written or changed by hand, or a check's result has to be read.
[Check each change](../SKILL.md#check-each-change) has the commands and which change takes which
check; this is what `cad urdf validate` covers, how to sweep the joints, and what a clean result
leaves open.

## The validator

```bash
cad urdf validate path/to/robot.urdf --packages robot_description=/path/to/pkg
```

```text
warning: missing_effort at /robot/joint[@name='shoulder_pitch']/limit: robot.urdf revolute joint 'shoulder_pitch' limit omits 'effort' Hint: The URDF schema requires effort and velocity; simulators misbehave without them.
OK robot.urdf: robot 'example_arm', root 'base_footprint', 3 links, 2 joints (1 movable), 2 resolved mesh references, total mass 1.8 kg
```

Read the `OK` line as a check of its own: a wrong root, a count of moving joints that is off, fewer
meshes found than the file names, or a total mass that is not the robot's is a fault no finding
reports.

An **error** fails the file and says what to change. Errors cover the tree (one root, unique names,
every joint's parent and child a link), joint types, axes, limits and mimics, the one shape of each
visual and collision and its sizes, a local mesh file that is not there, and an inertial that is not
physical (a mass or a diagonal that is not positive, a tensor that is not positive semidefinite).

A **warning** passes unless `--strict`:

- An omitted `<axis>`, which the format reads as `1 0 0`, or one that is not unit length.
- `effort` or `velocity` omitted from a revolute or prismatic `<limit>`, or 0 on a joint that is no
  `<mimic>` follower.
- A `<limit>` on a fixed joint, or `lower` or `upper` on a continuous one: consumers ignore them.
- A joint and a link of one name.
- A moving link with geometry and no `<inertial>`. Nothing requires an inertial or a collision on a
  link: which consumer needs them is yours to decide ([inertials.md](inertials.md)).
- Principal moments that break the triangle inequality, and an inertia more than 10 times off what
  the link's one primitive collision (else its one primitive visual) has at that mass, which is
  usually a unit bug.
- A negative mesh `scale`, which mirrors; a mesh extension outside `stl`, `dae`, `obj`, `3mf`, `glb`,
  `gltf` and `ply`; and a `package://` or remote mesh, which is not looked for at all.
  `--packages NAME=PATH` (repeatable) gives a package its folder, and a file missing from it is then
  an error.
- An unknown element under `<robot>`, a link, a joint, a visual, a collision or an inertial: a
  misspelled tag, which every consumer ignores silently. `<transmission>`, `<gazebo>`,
  `<ros2_control>` and `<sensor>` under `<robot>`, and namespaced elements anywhere, pass.
- A visual's `<material name>` that nothing defines.

## The sweep

Only moving each joint shows a flipped sign, a wrong axis, a misplaced origin or a limit that is too
wide. Draw the robot at zero, then each moving joint alone at a positive value and at both limits,
from a camera that looks along its axis, and hold each picture against the ledger's line for that
joint:

```bash
cad urdf snapshot robot.urdf zero.png --camera front
cad urdf snapshot robot.urdf shoulder.png --camera front --pose '{"shoulder_pitch": 60}'
```

A positive turn shows counter-clockwise from the camera at the positive end of its axis (`top` for
+Z, `right` for +X) and clockwise from the other end, as `front`, which looks from -Y, shows a turn
about +Y ([snapshots.md](snapshots.md) has the cameras and what a snapshot draws). The page given to
the person is not the sweep: say which joints were swept and which were not.

## What a clean result leaves open

- **Whether the frames are the robot's.** No check knows where a joint is or which way it turns: the
  ledger and the sweep do. A frame-only link and a `<collision>` are drawn in no snapshot, so their
  placement rests on the numbers alone.
- **Units.** A limit typed in degrees is a legal number of radians. A mesh file is found, never
  opened, so one in millimetres with no `scale`, or in a format `cad` cannot draw, passes.
- **An inertial's values**, beyond the warnings above ([inertials.md](inertials.md) has the gates).
- **That a picture means a valid file.** `cad urdf snapshot` runs no validation and draws files the
  validator fails (a negative mass, reversed limits). The viewer does not: its page refuses one,
  with the validator's errors.
- **That a consumer loads it.** `package://` resolves differently in every environment. Run
  `check_urdf` (liburdfdom, the parser ROS uses) where it is installed, then the consumer's own load,
  and report either as skipped where it was.
