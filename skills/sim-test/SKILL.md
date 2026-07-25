---
name: sim-test
description: Physics simulation validation for URDF/SDF mechanism definitions using PyBullet. Use when a design with moving parts (joints, motors, rotating or sliding components) needs motion, collision, contact, or friction behavior verified in a headless physics engine, or when writing pytest checks that load a generated URDF/SDF and assert joint limits, motor speeds, contact points, or slip behavior.
---

# Sim Test

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill after a mechanism definition has been produced with the
URDF or SDF skill and its motion, collision, or friction behavior needs
programmatic verification. This skill is a tool guide: it documents the
PyBullet API surface and example test patterns, not which scenarios you
must run. You decide which behaviors matter for the mechanism at hand,
based on the user's requirements and any design note for the task.

## Core Rules

1. You own the scenario selection. No file in this skill mandates a test
   for a mechanism type. Read the design intent, then simulate the
   behaviors that would actually break it.
2. PyBullet is the primary engine: easy install, headless `DIRECT` mode,
   native URDF loading. Two reasons to switch deliberately, after reading
   `references/mujoco-alternative.md`: contact fidelity is the deciding
   factor (gear meshing, grasping, stacked contacts), or the platform has
   no PyBullet wheel (PyBullet publishes Linux wheels only; MuJoCo ships
   Windows, macOS, and Linux wheels).
3. Write part tests as pytest files under `tests/generated/<part-name>/`,
   one directory per part. Example patterns below are starting shapes, not
   a fixed contract.
4. Start every simulation short and coarse: a few hundred steps at the
   default 1/240 s timestep answers most behavior questions. Refine
   (longer runs, smaller timesteps, more solver iterations) only when a
   result is ambiguous. Avoid multi-minute simulations in routine checks.
5. Assert against the design intent, not against whatever the current
   simulation happens to produce. State the basis for every expected value
   (user requirement, design note, or computed expectation).
6. Prefer fixing the URDF/SDF generator source over weakening a failing
   assertion. When an expectation itself turns out wrong, say so and
   correct the test with a stated reason.
7. Simulation complements visual review: hand the mechanism file to
   `$cad-viewer` when the task needs a human-facing preview, and treat
   neither layer as a substitute for the other.

## Workflow

1. Identify the mechanism definition (`.urdf` or `.sdf`) and its mesh
   dependencies. Read `references/urdf-sdf-integration.md` for path, mesh
   reference, and unit/scale pitfalls before loading.
2. Connect headless with `p.connect(p.DIRECT)`, load the model, and set
   gravity and friction parameters to match the intended operating
   condition.
3. Drive the mechanism with `p.setJointMotorControl2(...)`, step with
   `p.stepSimulation()`, and read back joint states, link states, and
   contact points. See `references/pybullet-api.md`.
4. Write the pytest file(s) under `tests/generated/<part-name>/` and run
   them with the project Python environment.
5. On failure, read the assertion output, fix the generator source,
   regenerate the definition, and rerun. Respect the iteration budget of
   the task's orchestration loop.

## Example Test Patterns

Patterns agents commonly adapt (choose per mechanism, never by default):

- A driven joint reaches and holds an expected speed range:
  command a velocity with `p.setJointMotorControl2`, settle for a fixed
  step count, assert `p.getJointState(...)[1]` lands in the expected band.
- No unintended contacts: step the mechanism through its travel, assert
  `p.getContactPoints(bodyA=..., bodyB=...)` stays empty for body pairs
  that must never touch (e.g. rotor vs. housing), and non-empty only where
  contact is designed (e.g. gear mesh region).
- Joint stays within limits: sweep the joint, assert
  `p.getJointState(...)[0]` never exceeds the URDF limit range.
- Friction response: set `p.changeDynamics(..., lateralFriction=...)` on a
  contact surface, apply a known force or slope, and observe whether the
  body holds or slips as the design expects.

## Tools

Install the skill dependencies into the project Python environment:

```bash
pip install -r requirements.txt
```

`pybullet` is the simulation engine; `numpy` backs result analysis. See
`references/pybullet-api.md` for the API surface and copyable snippets,
`references/urdf-sdf-integration.md` for loading generated definitions,
and `references/mujoco-alternative.md` for the high-contact-fidelity
alternative.

## References

- PyBullet API surface and code snippets: `references/pybullet-api.md`
- Loading URDF/SDF skill output into PyBullet:
  `references/urdf-sdf-integration.md`
- MuJoCo as a contact-fidelity alternative:
  `references/mujoco-alternative.md`
