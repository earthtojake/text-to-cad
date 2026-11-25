# Guardrails

Read this when a value in a hand-written URDF, SRDF or MJCF has no source, before writing a placeholder, and for the shape of the final report. A plausible number passes every check, so the guard is where the number came from.

## Values that need a source

The rule in [SKILL.md](../SKILL.md#author-by-hand) for transforms, axes, signs, units and inertias holds as well for what only the target reads: actuator gains, solver and contact settings, plugin names with their parameters, topics and namespaces, sensor schemas, and whether the target's version takes a format version or an extension, or resolves an external URI. Take each from the target's documentation for that version, or record it as an assumption.

Say the source where the number is, with its frame and its unit:

```xml
<!-- Source: project CAD frame export 2026-05-12. Parent: base_link. RPY radians. -->
<origin xyz="0.18 0 0.12" rpy="0 -0.2 0"/>
```

Where a value has no source, [urdf-authoring.md](urdf-authoring.md#when-information-is-missing) has the outcomes to choose from. The inferences that go wrong without a sign:

- A mirrored left or right chain changes axis signs and the off-diagonal inertia terms: derive the mirror transform in a script and record it.
- A visual mesh's origin is not the link frame, the collision frame or the centre of mass unless its export made it so, and an STL carries no unit ([meshes.md](meshes.md)).
- A kinematic error is corrected in the link and joint frames, never by offsetting the visual mesh alone.
- A transform already proven is kept unless the task is to change it.

## Placeholder policy

A placeholder is allowed only when the user asks for a scaffold, a draft or a minimal example, and is labelled so that it is found and replaced:

```xml
<!-- placeholder_inertial: primitive approximation pending measured mass properties -->
<inertial>
  <mass value="0.5"/>
  ...
</inertial>
```

Never a placeholder: an invented plugin name or actuator gain, an inertia on a dynamic robot with no warning, a mesh scale guessed until the picture looks plausible, a joint axis flipped to match an expected screenshot.

## The report

When finishing a task, state:

- the `.urdf`, `.srdf` or MJCF path(s) created or modified, the target consumer and its version;
- each check run and its result, by name, never only that the file is valid;
- each check skipped and why: a skipped check is a risk to know of, not a failure;
- assumptions and placeholders;
- unresolved resource paths and compatibility risks that need the simulator or MoveIt to verify.

```text
Validated: path/to/scene.xml
Target consumer: MuJoCo 4.0
Checks run:
- cad mujoco check: passed with 2 warnings (inertia_from_visuals on two finger links)
- collisions and excludes: read against the model; 12 collision geoms, 5 excludes, all touching at rest
- joint motion: base_yaw positive motion verified in the CAD model's snapshots; gripper joints skipped
- MuJoCo Studio: URL given to the person, or explicit launch failure
Assumptions:
- Assumed mesh units are meters.
- Assumed camera site is coincident with the wrist camera's optical centre.
Risks:
- Actuator gains were not tuned against the hardware.
```

A URDF or SRDF report has the same shape: `cad urdf validate` or `cad srdf validate`, `check_urdf`, the viewer sweep, MoveIt smoke tests, each run or skipped, and the assumptions (inferred TCP links, manual collision pairs, unverified planner behavior).
