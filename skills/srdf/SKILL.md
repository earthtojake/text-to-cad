---
name: srdf
description: MoveIt2 SRDF authoring, validation, and planning-semantics workflow. Use when creating, editing, inspecting, or validating `.srdf` files, MoveIt planning groups, virtual joints, passive joints, end effectors, group states, disabled collisions, URDF-paired planning semantics, or SRDF handoff for live review. Use the URDF skill for robot structure, the SDF skill for simulator descriptions, and the cad-viewer skill for rendering, live review links, and optional MoveIt2 controls.
---

# SRDF

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill for MoveIt semantic robot descriptions on top of an existing valid URDF. SRDF defines planning semantics; it does not define physical robot structure. The `.srdf` file is the source of truth: author and edit the XML directly. There is no `gen_srdf()` contract.

SRDF correctness is a **planning semantics** problem. The common failure is not invalid XML; it is a plausible SRDF that gives MoveIt the wrong planning group, wrong tool link, wrong default state, unsafe disabled-collision matrix, or wrong joint units. Because language models are weak at spatial and kinematic reasoning, derive planning groups, end effectors, group states, and disabled collisions from the URDF topology, MoveIt Setup Assistant output, sampled collision analysis, or explicit user data. Do not infer them from visual theme alone — and do not type any link or joint name from memory: extract the URDF's link/joint table first and copy names from it.

## Format boundary

- **URDF** owns physical robot structure: links, joints, geometry, inertials, limits, mimic joints, transmissions, and robot-state publishing.
- **SRDF** owns MoveIt semantics: virtual joints, passive joints, planning groups, group states, end effectors, and disabled collision pairs.
- **SDF** owns simulator/world semantics: physics, sensors, lights, plugins, worlds, and simulation-specific metadata.

Do not place geometry, inertials, joint origins, link poses, mesh references, physical joint limits, transmissions, or `ros2_control` interfaces in SRDF.

## CAD Viewer Handoff

After completing SRDF work that creates or modifies a `.srdf`, you must ALWAYS hand the explicit file path to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); include optional MoveIt2 controls in the handoff only when the user needs interactive IK or path-planning review. If `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Required workflow

1. **Start from a valid URDF.** Author or fix the URDF first with `$urdf` and validate it. The SRDF pairs with that URDF by colocation and robot name, and every name in the SRDF must exist in it.
2. **Extract the URDF table.** Before writing any SRDF XML, list the URDF's robot name, links, joints (with type, parent, child, limits, mimic flags). Copy names from this table only; never type them from memory. See `references/srdf-workflow.md`.
3. **Identify the planning task.** Record whether the goal is arm IK, gripper control, mobile base planning, dual-arm planning, tool use, or local smoke testing.
4. **Create or update the planning ledger.** Use `references/planning-ledger.md` before writing XML; keep a compact copy as a comment block in the `.srdf`.
5. **Pair with the URDF by colocation.** Save the `.srdf` in the same folder as its `.urdf`, with the same `<robot name>` — that is the only linking mechanism. The validator, the viewer, and the MoveIt2 server all resolve the pairing by scanning the folder for the URDF whose robot name matches; exactly one URDF per robot name per folder. No metadata element links the files. See `references/authoring-contract.md`.
6. **Define virtual and passive joints deliberately.** Use them when needed by the robot model.
7. **Define planning groups from URDF topology.** Prefer chain groups for serial manipulators when base/tip form a real parent-to-child path in the URDF tree (the validator verifies this). Use joint/link/subgroup definitions only when they are deliberate.
8. **Define end effectors after group membership is known.** Avoid overlap between an end-effector group and its parent group. Record the actual target/TCP link.
9. **Define group states in URDF-native units.** Revolute and continuous values are radians; prismatic values are meters. Do not store degrees in SRDF. Values must lie within URDF limits and must not set fixed or mimic joints.
10. **Generate disabled collisions from evidence.** Use adjacency derived from the URDF joint table, MoveIt Setup Assistant sampling, or explicit user-provided collision matrices. Do not invent broad disable lists. See `references/disabled-collisions.md`.
11. **Validate every created or modified `.srdf`** with `scripts/validate`; it cross-validates all names, chains, states, and pairs against the paired URDF. Fix findings and re-validate until clean.
12. **Run MoveIt smoke tests when available.** Use MoveIt Setup Assistant or a project MoveIt launch directly.
13. **Report assumptions and skipped checks.** Include incomplete validation, missing MoveIt environment, manually reasoned collision disables, and inferred target links.

## Commands

Run with the Python environment for the project or workspace. Treat `python` in examples as an interpreter placeholder; if bare `python` is unavailable, substitute `python3`, a project virtualenv interpreter, or the configured interpreter path. The validator uses only the Python standard library.

From this skill directory, the validator shape is:

```bash
python scripts/validate path/to/robot.srdf
python scripts/validate path/to/a.srdf path/to/b.srdf
python scripts/validate path/to/robot.srdf --strict
python scripts/validate path/to/robot.srdf --format json
```

The validator collects all findings in one pass (severity, code, XML path). It parses the SRDF, resolves the paired URDF (the same-folder `.urdf` whose robot name matches; none or several is an error), and cross-validates: group/joint/link/subgroup name existence, chain path resolvability, subgroup cycles, virtual/passive joints, end-effector topology, group-state membership/limits/completeness, disabled-collision pairs (including Adjacent-reason truthfulness), and misspelled elements. `--strict` treats warnings as failures; `--format json` emits a machine-readable findings document. It exits nonzero if any target fails. Relative targets resolve from the current working directory.

## Hard rules

- The SRDF lives in the same folder as its URDF and shares its `<robot name>`; that colocation-plus-name match is the only pairing mechanism, and exactly one URDF per robot name may exist in the folder.
- Every link, joint, group, and subgroup name must come from the URDF table or a group defined in the same file.
- Group states use URDF-native units: radians for revolute/continuous, meters for prismatic.
- Disabled collision pairs require truthful reasons and provenance.
- End-effector groups should not share links with their parent planning group.
- `$cad-viewer` owns optional local `moveit2_server` guidance for interactive planning review.
- Visual rendering review is useful but cannot prove planning correctness.

## Snapshot Tool

`scripts/snapshot` renders the robot to a PNG still or an orbit GIF, using the same shared
CLI and headless browser runtime every rendering skill uses — so a snapshot matches what
the CAD Viewer shows.

```bash
python scripts/snapshot --input path/to/robot.srdf --output review.png
python scripts/snapshot --input path/to/robot.srdf --output turntable.gif --mode orbit
```

It accepts `.srdf` only. Pose the robot with the job field `"jointValues"` (joint name to
degrees, defaulting to the rest pose) rather than `--params`, which is STEP-only; robots
are authored in metres and are framed on the robot scene scale automatically.

Theme settings live under one `--theme`, mirroring the viewer's Theme tab. The default
theme is `snapshot` — Workbench Light with the ground grid, origin axis and shadows
removed, because in a still image those read as geometry. There is no `--display`: display
settings (mode, clip, exploded, edges) are CAD topology settings, and a robot carries none.

Link meshes are resolved relative to the description, so they must be present: an
unhydrated Git LFS pointer fails as "No link mesh loaded for robot". Run
`git lfs checkout <mesh dir>` first.

Use `python scripts/snapshot --help` for the complete current command interface.

## References

- Authoring contract (structure, URDF pairing, golden skeleton): `references/authoring-contract.md`
- SRDF workflow (URDF table extraction, edit loop): `references/srdf-workflow.md`
- Planning ledger: `references/planning-ledger.md`
- Validation and verification recipe: `references/validation.md`
- End effectors: `references/end-effectors.md`
- Disabled collisions: `references/disabled-collisions.md`

For local MoveIt2 controls, use `$cad-viewer`; in that skill, read `references/moveit2-server.md`.
