# LLM guardrails

This skill assumes agents are useful at structuring URDF, SRDF and MJCF documents and weak at silently deriving precise spatial, physical, and simulator-specific values. The workflow should route those weaknesses into explicit ledgers, constants, helpers, validators, and smoke tests.

## What agents can usually do well

- organize a robot or scene into links or bodies, joints, frames, visuals, collisions, sensors, actuators, and includes;
- translate user intent into a plausible document structure;
- maintain naming consistency when names are explicit;
- write small throwaway Python scripts for derived numbers and transformations;
- explain assumptions and create checklists;
- preserve existing patterns when examples are nearby.

## What agents should not be trusted to infer silently

- exact link poses, frame transforms, or joint origins;
- positive joint-axis directions from visual theme;
- mesh units, mesh scale, or coordinate-system conventions;
- center of mass or inertia tensors from rendered shape alone;
- plugin names, parameters, topics, namespaces, or sensor schemas;
- actuator gains, solver settings, or contact parameters;
- target simulator support for a given format version or extension;
- whether collision geometry is stable for physics;
- whether external URIs resolve in the deployment environment.

## Spatial-reasoning guardrails

LLMs are prone to plausible-looking spatial mistakes. Use these guardrails in every format:

- Do not infer dimensions, handedness, axes, mesh units, or joint signs from vague descriptions.
- Do not silently mirror left/right parts. A mirrored chain changes axis signs and off-diagonal inertia terms; derive the mirror transform explicitly (helper script) and record it in the ledger.
- Do not assume visual mesh origin equals link frame, collision frame, or center of mass.
- Do not assume CAD mesh units are meters. STL files carry no reliable unit metadata.
- Do not encode a kinematic correction by offsetting only the visual mesh; correct the link and joint frames unless the visual mesh is genuinely offset.
- Preserve existing proven transforms unless the task explicitly requires changing them.
- Record every assumed value in the ledger comment block; in helper scripts, name constants by physical meaning (`ASSUMED_BASE_TO_SHOULDER_Z_M`).

## Required mitigation pattern

For every spatial, physical, or simulator-specific value, use one of these sources:

1. user-provided requirement;
2. upstream geometry, robot-description, planning-metadata, mesh manifest, or model package source;
3. target simulator documentation;
4. measured or calculated value with method stated;
5. explicit assumption recorded in the ledger comment block and the final report.

When spatial information is missing, do not invent a precise-looking transform: the outcomes to choose from are in [urdf-ledger.md](urdf-ledger.md#when-information-is-missing). A provisional description is acceptable when clearly labelled; a plausible but undocumented one is not.

Do not hide guessed values in raw XML: every non-obvious number carries a comment or a ledger line naming its source.

## Placeholder policy

Placeholders are allowed only when the user asks for a scaffold, draft, or minimal example. Mark them as placeholders and keep them easy to replace.

Examples of acceptable placeholders:

```xml
<!-- placeholder_inertial: primitive approximation pending measured mass properties -->
<inertial>
  <mass>0.5</mass>
  ...
</inertial>
```

Examples of unacceptable placeholders:

- invented plugin names or actuator gains;
- arbitrary inertia values on a dynamic robot without a warning;
- guessed mesh scale that makes the visual look plausible;
- silently flipping a joint axis to match an expected screenshot.

## Spatial reasoning checklist

Before generating or modifying a description, answer these questions in the ledger or final report:

| Question | Required evidence |
|---|---|
| What frame is each pose expressed in? | the parent link or body, source file, or documented default |
| What frame is each joint axis expressed in? | the joint frame (URDF), the body frame (MJCF), or documented default |
| What is positive motion for each non-fixed joint? | command/test expectation or upstream source |
| Are mesh units and scales known? | manifest, CAD export config, or explicit assumption |
| Are visual and collision poses intentionally different? | simulation reason or source geometry |
| Are inertials measured, calculated, approximated, or omitted? | method and confidence |
| Are actuator, sensor and plugin parameters copied from target docs? | target simulator/version and source |

## Authoring style

Prefer this pattern:

```xml
<!-- Source: project CAD frame export 2026-05-12. Parent: base_link. RPY radians. -->
<origin xyz="0.18 0 0.12" rpy="0 -0.2 0"/>
```

Avoid this pattern:

```xml
<origin xyz="0.18 0 .12" rpy="0 -11.5 0"/>
```

The second version names no source or parent frame, uses degrees where URDF reads radians, and makes the source of the transform impossible to audit.

## Validation expectations

The validator should catch cheap deterministic mistakes, but it cannot prove the design is physically or simulator-correct. After bundled validation, use optional external checks and simulator or MoveIt smoke tests when the task depends on that behavior.

Report skipped checks explicitly. A skipped check is not automatically a failure, but it is relevant risk information.

## The report

When finishing a task, state:

- the `.urdf`, `.srdf` or MJCF path(s) created or modified, the target consumer and version;
- checks run and their result;
- checks skipped and why;
- assumptions and placeholders;
- unresolved resource paths and target-specific compatibility risks that need simulator or MoveIt verification.

Do not simply say that the file is valid. Say which validator or smoke test passed.

A compact report:

```text
Validated: path/to/scene.xml
Target consumer: MuJoCo 3.3
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
