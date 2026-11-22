---
name: robot-simulation
description: Writes and reviews robot and world descriptions (URDF, SRDF, MJCF) for ROS, MoveIt and MuJoCo. Use to generate a robot description or a MuJoCo scene from a CAD model's joints, or to write, edit or check a .urdf, .srdf or MJCF .xml by hand. Not for the CAD part itself, which the cad skill makes, and it runs no simulation.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# Robots and worlds for simulation and motion planning

A robot is described for its consumers in XML: a URDF for its structure (ROS, RViz,
robot_state_publisher), an SRDF beside it for MoveIt's planning semantics, and an MJCF for MuJoCo.
There are two routes to one:

- **Generate it from CAD.** A text-to-cad model that holds the mechanism, materials and named frames
  is the source of truth: `cad model export` writes the URDF or MJCF, with frames, limits, masses,
  inertias and meshes exact from the kernel. The file is regenerated, never edited.
- **Author it by hand.** A robot with no CAD model here, an SRDF (always), a MuJoCo scene, or a file
  that already exists: the XML is the source of truth. The risk is not XML syntax but frames, axis
  signs, units, mesh scale, inertials and planning semantics: a file can pass every check and still
  place a joint in the wrong spot.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| A URDF or MJCF from a CAD model | The model's declarations, then `cad model export <id> robot.xml` or `.urdf` | [Generate from CAD](#generate-from-cad), [from CAD](references/from-cad.md) |
| Collision shapes, joint dynamics, actuators for MuJoCo | A MuJoCo function, run with `cad run` | [The MuJoCo function](#the-mujoco-function), [MuJoCo environment](references/mujoco-environment.md) |
| A robot from a vendor's STEP | Read it, group parts into links, find each axis, declare, export | [From a vendor STEP](references/from-a-vendor-step.md) |
| A MuJoCo scene: several robots, objects, a world | `spec()` for each piece, composed with MuJoCo's own `MjSpec` | [MuJoCo environment](references/mujoco-environment.md#the-scene-in-code) |
| Tune a MuJoCo model's physics | `cad mujoco check`'s model-health findings, one parameter at a time | [Tuning](references/mujoco-environment.md#tuning), [MJCF checks](references/mjcf-checks.md) |
| A URDF by hand | The `.urdf` and its ledger, then `cad urdf validate` | [Authoring](references/urdf-authoring.md) (frames and signs, the ledger), [checks](references/urdf-checks.md) |
| MoveIt groups, end effectors, states, collision pairs | A `.srdf` beside the URDF, then `cad srdf validate` | [Authoring](references/srdf-authoring.md) (end effectors, disabled collisions, the ledger), [checks](references/srdf-checks.md) |
| An MJCF by hand | `robot.xml` and a `scene.xml` that includes it, then `cad mujoco check` | [Authoring](references/mjcf-authoring.md), [checks](references/mjcf-checks.md) |
| Link meshes for a hand-written file | One mesh per link, in the link's frame | [Meshes](references/meshes.md) |
| Mass, centre of mass, inertia | Materials on the CAD parts; else a formula or a script, never intuition | [Inertials](references/inertials.md) |
| A four-bar in the viewer | `<tcad:four_bar>` on the derived URDF joint | [Four-bar](references/urdf-four-bar.md) |
| See the robot or a pose | `cad urdf snapshot`, `cad srdf snapshot`; an MJCF in MuJoCo Studio | [Snapshots](references/snapshots.md) |
| Work across formats, or convert a URDF to MJCF | Which file owns what | [Interoperability](references/interoperability.md) |

## Setup

Written for `cad==0.11.16`. Before first use in a chat, run `cad --version`. If `cad` is missing or older than
0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.

If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
https://github.com/earthtojake/text-to-cad
A project written for an earlier version may need changes; the migration guides say what:
https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations

MuJoCo (`cad mujoco check`, `cad run mujoco-studio`, a script that imports `mujoco`) and CoACD
(`decompose()`) are fetched by `cad` the first time they are needed, about 20 MB and 4 MB; nothing to
install. `cad <command> --help` is the complete, current interface.

## Generate from CAD

The model says what is true of the machine, in its body (the `cad` skill's kinematics reference
covers the mechanism itself), and the export writes each format from it:

| In the model | Says | Written as |
| --- | --- | --- |
| build123d joints, connected | Links, joints, and each joint's range around the as-built pose, which is zero | Bodies and joints; links and joints |
| `mechanism_state(...)` | Named poses; name one `home` | MJCF keys (URDF has none) |
| `gear_pair`, `rack_and_pinion_pair` | A follower joint on its leader | `<equality><joint>`; `<mimic>` |
| `part.material`, `mass()`, `point_mass()` | Density, a measured total, a lump the CAD leaves out | Exact `<inertial>`s |
| `frame(part, name, location)` | A tool point, a mount, a sensor | A site; an empty link |
| `body(part, name)` | A part kept as its own body | A child body; a link on a fixed joint |
| `limits(assembly, joint, effort=, velocity=)` | The drive's datasheet limits | `actuatorfrcrange`; `<limit>` |
| `link(part_or_assembly, name)` | A link's name (`base_link`) | Body and link names |
| `free(assembly)` | Not bolted to the world | `<freejoint>`; a floating root |

```python
from cad.build123d import body, frame, free, limits, link, mass, point_mass

frame(palm, "tcp", bd.Pos(0, 0, 65))   # mm, in the palm's own frame
body(camera, "camera")                 # fixed to the palm, a body of its own
limits(root, "left", effort=2, velocity=1.5)   # N*m, rad/s: the servo's datasheet
point_mass(palm, 120, bd.Pos(0, 0, 20), name="motor")   # g, mm in the palm's own frame
mass(palm, 410)                        # g: the palm as weighed, its motor included
link(palm, "base_link")                # the palm's link, named as ROS names a base
free(root)                             # on a mobile base: not bolted to the world
```

```bash
cad run src/gripper.py
cad model ranges "$ID"                                       # stops where the parts meet, to write into the joints
cad model export "$ID" sim/gripper.xml
cad model export "$ID" description/gripper.urdf --zero home
```

`$ID` is the `id:` line the run printed; the suffix picks the format, and meshes are written beside
the file. Each export says what it wrote (links, joints, total mass, couplings, frames, keys) with a
warning for anything left out: read it first, since a mass of 0 or a missing joint is a model to fix.
An MJCF export also writes a `scene.xml` beside it once (floor, light), which is yours to edit.
[From CAD](references/from-cad.md) has each declaration in full, joint ranges, the zero pose and
`--zero`.

- **Never edit a generated file.** A frame, limit, mass or mesh is changed in the model; a collision
  shape, damping or actuator in the MuJoCo function; a floor or solver setting in the scene.
- **The kernel cannot know intent**: check that each joint's positive motion is the one meant
  (`cad model snapshot "$ID" out.png --pose <state>`) and that the collision shapes suit the physics.

### The MuJoCo function

A plain export holds no chosen collision shape, joint dynamics or actuator: each part collides as its
own mesh's convex hull, and nothing drives the joints. Those are a simulation's choices, made in a
plain Python function beside the model that turns the robot into a `mujoco.MjSpec`, edits it with
MuJoCo's own API and returns it:

```python
# src/gripper_mujoco.py
import mujoco
from cad.mujoco import collisions, fit, save, spec

from gripper import gripper


def gripper_mujoco() -> mujoco.MjSpec:
    s = spec(gripper())
    for part in ("palm", "left", "right"):
        fit(s, part, "box")                        # the kernel's box of the part's exact solid
    for geom in collisions(s, "left") + collisions(s, "right"):
        geom.friction = [1.1, 0.005, 0.0001]       # sliding, torsional, rolling
    left = s.joint("left")
    left.armature = 0.002                          # kg*m^2
    left.damping = [0.1, 0, 0]                     # N*m*s/rad, a 3-vector in MuJoCo 4
    grip = s.add_actuator(name="grip", target="left", trntype=mujoco.mjtTrn.mjTRN_JOINT)
    grip.set_to_position(kp=20, dampratio=1, inheritrange=True)
    return s


if __name__ == "__main__":
    save(gripper_mujoco(), "sim/gripper.xml")
```

```bash
cad run src/gripper_mujoco.py
cad mujoco check sim/scene.xml
```

`spec`, `fit`, `decompose`, `collisions`, `parts` and `save` are the only helpers; they name a part by
its label path, as `cad model inspect` prints it. Everything else is MuJoCo's API. `save` writes the
file with its meshes, and a `scene.xml` where there is none, then prints the check's warnings, what
the model collides as and its contact excludes: read them against the choices the function made. This
file replaces the plain export ([MuJoCo environment](references/mujoco-environment.md#the-mujoco-function)).

## Author by hand

For a robot that has a CAD model here, generate the URDF or MJCF and author only what it does not
carry: the SRDF, a MuJoCo scene. Each format owns one thing:

- **URDF**: physical structure. Links, joints, geometry, inertials, limits, mimic joints.
- **SRDF**: MoveIt semantics over a valid URDF. Groups, group states, end effectors, disabled
  collision pairs. It pairs with its URDF by colocation and robot name alone: same folder, same
  `<robot name>`, exactly one such URDF.
- **MJCF**: a MuJoCo model. Bodies, joints, geoms, default classes, actuators, equalities and
  keyframes, in one file or a `scene.xml` that includes the robot's.
- **Meshes** belong to the CAD workflow: one per link, exported in that link's frame. A wrong export
  is fixed there, never with a URDF origin or an MJCF body position.

What holds for every format:

- Name the consumers first (RViz, robot_state_publisher, MoveIt, a driver, MuJoCo), and how strict
  each is.
- Keep a ledger of the modeled facts (frames, joints, geometry, units, assumptions and where each
  came from) as a comment block at the top of a hand-written file, updated in the same edit.
- Units are SI: metres, kilograms, seconds, radians. An MJCF says `<compiler angle="radian"/>`, since
  MuJoCo's default is degrees.
- Transforms, axes, joint signs, mesh units and inertia tensors come from a source (CAD, a drawing, a
  datasheet, a measurement, a formula or script), never from prose or how a picture looks. An
  assumption is stated as one ([guardrails](references/guardrails.md)).
- Names are shared identifiers: SRDF groups, controllers and TF read the URDF's link and joint names,
  so a rename updates every consumer in the same task, and any URDF edit re-runs `cad srdf validate`
  on the SRDF beside it.

The trap in each format, and where its contract is:

- **URDF**: most errors are frame errors. A joint's `<origin>` is the parent-link-frame transform to
  the joint frame at zero, the child link frame coincides with the joint frame, `<axis>` is in the
  joint frame, and `visual`, `collision` and `inertial` origins are each in the link frame
  ([frames and signs](references/urdf-authoring.md#frames-and-signs)).
- **SRDF**: the failure is a plausible file with the wrong group, tool link, default state or
  collision matrix. Extract the URDF's link and joint table and copy every name from it; derive groups
  from its topology and disabled collisions from evidence
  ([authoring](references/srdf-authoring.md)).
- **MJCF**: units and defaults. Angles are degrees unless the compiler line says radians (a keyframe's
  `qpos` is radians regardless), and a geom or joint inherits from its default class. Split the robot
  from its world, and clear every model-health warning before tuning physics
  ([authoring](references/mjcf-authoring.md)).

## Check each change

```bash
cad urdf validate path/to/robot.urdf
cad urdf validate path/to/robot.urdf --packages robot_description=/path/to/pkg
cad srdf validate path/to/robot.srdf --strict
cad mujoco check path/to/scene.xml
cad mujoco check path/to/scene.xml --strict --json
cad urdf snapshot path/to/robot.urdf review.png --pose '{"shoulder_pitch": 30}'
cad srdf snapshot path/to/robot.srdf review.png --pose arm/ready
cad run mujoco-studio --model path/to/scene.xml
```

| Change | Check it with |
| --- | --- |
| A CAD model's mechanism or declarations | Run it, export again (or run its MuJoCo function again), validate the file; `cad model snapshot` at each mechanism state first, where the joint signs show |
| A MuJoCo function or a scene script | Run it and read what `save` printed, then `cad mujoco check` on the scene |
| Any `.urdf` | `cad urdf validate` until clean; `check_urdf` when installed; `cad srdf validate` on an SRDF beside it |
| A joint origin, axis, sign or limit | Every movable joint moved through its limits, in the viewer or in snapshots at `--pose` values. Only this catches a flipped sign |
| A mesh, its scale or placement | A snapshot: about 1000x too large or small is a `scale` bug |
| An inertial | The [sanity gates](references/inertials.md#sanity-gates) |
| Any `.srdf` | `cad srdf validate`, which cross-checks every name, chain, state and pair against the URDF; named states in a snapshot |
| Any MJCF | `cad mujoco check`: MuJoCo's own compile, the model-health checks, what collides and the contact excludes |
| MuJoCo physics | One parameter changed, checked, and run in MuJoCo Studio against the baseline ([tuning](references/mujoco-environment.md#tuning)) |
| A ROS or MoveIt consumer | Its own load where available: RViz, the TF tree, MoveIt Setup Assistant |

- A check validates one file and collects every finding (severity, code, location, hint). `--strict`
  fails on warnings, `--json` prints the result as one object, and the exit status is 1 for a file
  that fails and 2 for a command refused.
- A snapshot's `--pose` takes degrees (metres for a slide), though the files hold radians.
- No `cad` command draws an MJCF. `cad run mujoco-studio` serves MuJoCo Studio's web viewer for the
  person, reloading as the file changes; it listens on every network interface with no
  authentication, so it is for this computer or a trusted network.
- A clean check is a guardrail, not proof: it cannot show that an axis matches the robot, that mesh
  units match `scale`, that a planning group suits the task or that a gain is right. Report which
  checks ran, which were skipped, and the assumptions made
  ([report shape](references/guardrails.md#the-report)).

## Show the model

Show the person each model you create or change as soon as its first run succeeds, and any model
or file they ask to see. A model's page is the `view:` line its run prints, and a file's is the `url`
that `cad viewer --json FILE [FILE ...]` prints for it (never guess the port). Show it with
the first of these you have:

1. `cad_show` among your tools (your host may prefix it): call it with the model's id or the file's
   absolute path; its description says the rest.
2. A tool that opens a page in the app's own browser pane, not in the person's own browser (in the
   Claude desktop app, the Browser pane's `preview_start` with the page's `url`, or its `navigate`):
   open the page there yourself, and give the person the link as well.
3. Neither: give the person the link, to open in their browser.

The page follows every run of the model. A file you export is a download: give its path. Showing is
for the person: to check your own work, review with `cad <type> snapshot`, never a screenshot
of the page. If it fails to launch, say so.

An MJCF is the exception: the viewer and `cad_show` do not open one. Show the person the CAD
model it was generated from, and for the MJCF itself run `cad run mujoco-studio --model FILE` and
give them the URL it prints.
