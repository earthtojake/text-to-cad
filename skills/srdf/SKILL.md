---
name: srdf
description: MoveIt2 SRDF generation, validation, and planning-semantics workflow. Use when creating, editing, regenerating, inspecting, or validating `.srdf` files, `gen_srdf()` sources, MoveIt planning groups, virtual joints, passive joints, end effectors, group states, disabled collisions, URDF-linked planning semantics, or SRDF handoff for live review. Use the URDF skill for robot structure, the SDF skill for simulator descriptions, and the cad-viewer skill for rendering, live review links, and optional MoveIt2 controls.
---

# SRDF

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill for MoveIt semantic robot descriptions on top of an existing valid URDF. SRDF defines planning semantics; it does not define physical robot structure.

SRDF correctness is a **planning semantics** problem. The common failure is not invalid XML; it is a plausible SRDF that gives MoveIt the wrong planning group, wrong tool link, wrong default state, unsafe disabled-collision matrix, or wrong joint units. Because language models are weak at spatial and kinematic reasoning, derive planning groups, end effectors, group states, and disabled collisions from the URDF topology, MoveIt Setup Assistant output, sampled collision analysis, or explicit user data. Do not infer them from visual appearance alone.

## Format boundary

- **URDF** owns physical robot structure: links, joints, geometry, inertials, limits, mimic joints, transmissions, and robot-state publishing.
- **SRDF** owns MoveIt semantics: virtual joints, passive joints, planning groups, group states, end effectors, and disabled collision pairs.
- **SDF** owns simulator/world semantics: physics, sensors, lights, plugins, worlds, and simulation-specific metadata.

Do not place geometry, inertials, joint origins, link poses, mesh references, physical joint limits, transmissions, or `ros2_control` interfaces in SRDF.

## CAD Viewer Handoff

After completing SRDF work that creates or modifies a `.srdf`, you must ALWAYS hand the explicit file path to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); include optional MoveIt2 controls in the handoff only when the user needs interactive IK or path-planning review. If `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Required workflow

1. **Start from a valid URDF.** Generate or fix the URDF first. The SRDF generator validates against the source-relative `.urdf` path supplied by `gen_srdf()`.
2. **Identify the planning task.** Record whether the goal is arm IK, gripper control, mobile base planning, dual-arm planning, tool use, or local smoke testing.
3. **Create or update the planning ledger.** Use `references/planning-ledger.md` before writing XML.
4. **Define virtual and passive joints deliberately.** Use them when needed by the robot model, even though the current lightweight runtime does not fully inventory them yet.
5. **Define planning groups from URDF topology.** Prefer chain groups for serial manipulators when base/tip form a real path. Use joint/link/subgroup definitions only when they are deliberate.
6. **Define end effectors after group membership is known.** Avoid overlap between an end-effector group and its parent group. Record the actual target/TCP link.
7. **Define group states in URDF-native units.** Revolute and continuous values are radians; prismatic values are meters. Do not store degrees in SRDF.
8. **Generate disabled collisions from evidence.** Use adjacency, MoveIt Setup Assistant sampling, or explicit user-provided collision matrices. Do not invent broad disable lists.
9. **Regenerate only explicit SRDF targets.** Generation validates the generated SRDF against the linked URDF before writing.
10. **Run MoveIt smoke tests when available.** Use MoveIt Setup Assistant or a project MoveIt launch directly.
11. **Report assumptions and skipped checks.** Include incomplete validation, missing MoveIt environment, manually reasoned collision disables, and inferred target links.

## Commands

Run with the Python environment for the project or workspace. Treat `python` in examples as an interpreter placeholder; if bare `python` is unavailable, substitute `python3`, a project virtualenv interpreter, or the configured interpreter path.

From this skill directory, the SRDF launcher shape is:

```bash
python scripts/srdf path/to/source.py
python scripts/srdf path/to/source.py -o path/to/robot.srdf
python scripts/srdf path/to/a.py=out/a.srdf path/to/b.py=out/b.srdf
```

Relative source targets and CLI output overrides are resolved from the current working directory. When running from outside this skill directory, prefix the launcher path so target files still resolve from the intended workspace.

## Hard rules

- SRDF must reference an existing valid URDF.
- The SRDF robot name must match the URDF robot name.
- Group states use URDF-native units: radians for revolute/continuous, meters for prismatic.
- Disabled collision pairs require truthful reasons and provenance.
- End-effector groups should not share links with their parent planning group.
- `$cad-viewer` owns optional local `moveit2_server` guidance for interactive planning review.
- Visual rendering review is useful but cannot prove planning correctness.

## References

- Generation command: `references/gen-srdf.md`
- Generator contract: `references/generator-contract.md`
- SRDF workflow: `references/srdf-workflow.md`
- Planning ledger: `references/planning-ledger.md`
- Validation scope: `references/validation.md`
- End effectors: `references/end-effectors.md`
- Disabled collisions: `references/disabled-collisions.md`
- Runtime notes and current limitations: `references/implementation-notes.md`

For local MoveIt2 controls, use `$cad-viewer`; in that skill, read `references/moveit2-server.md`.
