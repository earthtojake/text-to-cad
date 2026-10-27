---
name: srdf
description: MoveIt2 SRDF authoring, validation, and planning-semantics workflow. Use when creating, editing, inspecting, or validating `.srdf` files, MoveIt planning groups, virtual joints, passive joints, end effectors, group states, disabled collisions, URDF-paired planning semantics, or SRDF handoff for live review. Use the URDF skill for robot structure and the SDF skill for simulator descriptions. Open and visually review existing SRDF files in CAD Viewer.
license: MIT
---

# SRDF

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill for MoveIt semantic robot descriptions on top of an existing valid URDF. SRDF defines planning semantics; it does not define physical robot structure. The `.srdf` file is the source of truth: author and edit the XML directly.

SRDF correctness is a **planning semantics** problem. The common failure is not invalid XML; it is a plausible SRDF that gives MoveIt the wrong planning group, wrong tool link, wrong default state, unsafe disabled-collision matrix, or wrong joint units. Because language models are weak at spatial and kinematic reasoning, derive planning groups, end effectors, group states, and disabled collisions from the URDF topology, MoveIt Setup Assistant output, sampled collision analysis, or explicit user data. Do not infer them from visual theme alone — and do not type any link or joint name from memory: extract the URDF's link/joint table first and copy names from it.

## Setup

Run cadgen through the `cadgen` command its installation writes, so this skill's commands
share one installation, and its engine server, with the CAD app's:

- `cadgen` below means `cadgen +0.8.2` (`~/.local/bin/cadgen +0.8.2` where `~/.local/bin` is not on your PATH)
- `python` below means `cadgen +0.8.2 run`

If `cadgen` is not on your PATH, or it says 0.8.2 is not installed, run
`uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.2 cadgen doctor` once,
outside any sandbox or with its permission: it installs cadgen, registers it, writes the
`cadgen` command and starts the engine. With the CAD app's server running, nothing else
needs the sandbox's permission: it starts the engine and holds it. Without it, a sandboxed
shell cannot start the engine; when a command says no engine is running, run `cadgen server`
outside the sandbox once.

## Format boundary

- **URDF** owns physical robot structure: links, joints, geometry, inertials, limits, mimic joints, transmissions, and robot-state publishing.
- **SRDF** owns MoveIt semantics: virtual joints, passive joints, planning groups, group states, end effectors, and disabled collision pairs.
- **SDF** owns simulator/world semantics: physics, sensors, lights, plugins, worlds, and simulation-specific metadata.

Do not place geometry, inertials, joint origins, link poses, mesh references, physical joint limits, transmissions, or `ros2_control` interfaces in SRDF.

## Show the model

Show the user each model you create or change, and any model or file they ask to see.
A file you export is a download: give its path, do not open it.
Snapshots and validation don't replace this. Never screenshot the viewer to confirm your
own work; review with `cadgen snapshot`.

- If your tools include `cad_show` (your host may prefix it), call it with the model's id
  or the file's absolute path, and follow its description for when to call it again.
  The other tools depend on the host. A host that draws CAD cards or tabs (Claude
  Desktop, the Codex app) also has `cad_view`, which reads what the user selected, and
  `cad_screenshot`, which shows you what they see, both of a card or tab that is open, for
  when they ask about it. A text host (Claude Code in a terminal, `codex exec`) draws
  nothing: its `cad_show` opens the model's page in the user's browser and answers with
  the URL to give them, and it has no view to read. `cad_inspect`, `cad_snapshot` and
  `cad_export` are on every host. Call only the tools you have, and never say a card
  shows a model when your host drew none.
- Otherwise give the user the page's link once: a model's page is the `view:` line its
  run prints. For a file, run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --json FILE [FILE ...]
  ```

  The command ensures this installation's engine, registers each file and prints
  its page, `/<id>`, then exits. Read each file's `url` from `documents` in its one
  JSON line (never guess the port); the URL carries its token query. A page follows
  every later run of its model and every rewrite of its file, so share it once.
  Return that link to the user. If it fails to launch, say so.

An `.srdf` you write is the robot's model, not an export: show it. Keep the SRDF
beside its uniquely matching URDF (same robot name). Review
planning groups, named states and joints; visual review does not prove planning
correctness.

## Required workflow

1. **Start from a valid URDF.** Author or fix the URDF first with `$urdf` and validate it. The SRDF pairs with that URDF by colocation and robot name, and every name in the SRDF must exist in it.
2. **Extract the URDF table.** Before writing any SRDF XML, list the URDF's robot name, links, joints (with type, parent, child, limits, mimic flags). Copy names from this table only; never type them from memory. See `references/srdf-workflow.md`.
3. **Identify the planning task.** Record whether the goal is arm IK, gripper control, mobile base planning, dual-arm planning, tool use, or local smoke testing.
4. **Create or update the planning ledger.** Use `references/planning-ledger.md` before writing XML; keep a compact copy as a comment block in the `.srdf`.
5. **Pair with the URDF by colocation.** Save the `.srdf` in the same folder as its `.urdf`, with the same `<robot name>` — that is the only linking mechanism. The validator and the viewer both resolve the pairing by scanning the folder for the URDF whose robot name matches; exactly one URDF per robot name per folder. No metadata element links the files. See `references/authoring-contract.md`.
6. **Define virtual and passive joints deliberately.** Use them when needed by the robot model.
7. **Define planning groups from URDF topology.** Prefer chain groups for serial manipulators when base/tip form a real parent-to-child path in the URDF tree (the validator verifies this). Use joint/link/subgroup definitions only when they are deliberate.
8. **Define end effectors after group membership is known.** Avoid overlap between an end-effector group and its parent group. Record the actual target/TCP link.
9. **Define group states in URDF-native units.** Revolute and continuous values are radians; prismatic values are meters. Do not store degrees in SRDF. Values must lie within URDF limits and must not set fixed or mimic joints.
10. **Generate disabled collisions from evidence.** Use adjacency derived from the URDF joint table, MoveIt Setup Assistant sampling, or explicit user-provided collision matrices. Do not invent broad disable lists. See `references/disabled-collisions.md`.
11. **Validate every created or modified `.srdf`** with `cadgen srdf validate`; it cross-validates all names, chains, states, and pairs against the paired URDF. Fix findings and re-validate until clean.
12. **Run MoveIt smoke tests when available.** Use MoveIt Setup Assistant or a project MoveIt launch directly.
13. **Report assumptions and skipped checks.** Include incomplete validation, missing MoveIt environment, manually reasoned collision disables, and inferred target links.

## Commands

Run `cadgen` as Setup defines it. `cadgen doctor <skill-dir>` reports the installation in use and checks that it is the one this skill pins — docs drift silently on another. Validation itself needs nothing beyond the Python standard library; a snapshot draws with the CAD kernel. Use `cadgen <verb> --help` for the complete current interface.

The validator shape is:

```bash
cadgen srdf validate path/to/robot.srdf
cadgen srdf validate path/to/robot.srdf --strict
cadgen srdf validate path/to/robot.srdf --json
```

The validator parses the SRDF, resolves the paired URDF (the same-folder `.urdf` whose robot name matches; none, several, or an invalid one is an error), and cross-validates: group/joint/link/subgroup name existence, chain path resolvability, subgroup cycles, virtual/passive joints, end-effector topology, group-state membership/limits/completeness, disabled-collision pairs (including Adjacent-reason truthfulness), and misspelled elements. Each phase collects all its findings in one pass (severity, code, XML path), but a structural error stops the cross-file phase — re-run after every fix. One run validates ONE file: `--strict` treats warnings as failures and `--json` prints one line of `{"ok", "path", "issues": [{"severity", "code", "message", "element", "hint"}], "summary"}`, where `element` is the XML path. It exits nonzero if the target fails. Relative targets resolve from the current working directory.

## Hard rules

- The SRDF lives in the same folder as its URDF and shares its `<robot name>`; that colocation-plus-name match is the only pairing mechanism, and exactly one URDF per robot name may exist in the folder.
- Every link, joint, group, and subgroup name must come from the URDF table or a group defined in the same file.
- Group states use URDF-native units: radians for revolute/continuous, meters for prismatic.
- Disabled collision pairs require truthful reasons and provenance.
- End-effector groups should not share links with their parent planning group.
- Visual rendering review is useful but cannot prove planning correctness.

## Snapshot Tool

`cadgen snapshot` draws the robot to a PNG still, as the CAD Viewer shows it,
rendered by OCCT:

```bash
cadgen snapshot path/to/robot.srdf review.png
cadgen snapshot path/to/robot.srdf review.png --pose arm/ready
cadgen snapshot path/to/robot.srdf review.png --pose '{"shoulder_pitch": 30}'
```

Hand it the `.srdf`: it draws the paired URDF's geometry, the same-folder `.urdf`
whose `<robot name>` matches, exactly as `cadgen srdf validate` pairs them. No match,
or more than one, is refused before anything renders, naming the robot name it
looked for and the `.urdf` files it found.

The robot opens where the CAD Viewer opens it: every joint at zero, then this
SRDF's `home` group state if it declares one. `--pose` names a group state
(`group/name`, or a name only one group has) or gives joint values over that
opening pose, in degrees (metres for a prismatic joint), each naming a joint a
person can drive, within its limits, or the request is refused before anything
renders: a fixed joint or a `<mimic>` follower is refused by name (a follower
follows its leader). Each link is placed by the viewer's own forward kinematics and
drawn in one colour of the Parts palette. A visual is a `box`, `cylinder` or
`sphere`, which cadgen meshes itself, or an STL, 3MF or GLB file beside the URDF;
a mesh in another format (`.dae`, `.obj`), a `package://` or remote URI, or a
missing file is refused by name, and a link mesh that cannot be loaded fails the
snapshot rather than leaving the link out.

A normal snapshot uses Solid mode and Light appearance. `--display` takes any of the
viewer's display modes (`parts`, `xray`, `hidden-line`, `wireframe`, ...),
`exploded=AMOUNT`, or the display object: `appearance` (`light` or `dark`),
`camera` (projection and focal length) and `clip` (`{"clip": {"axis": "x", "at":
0.05}}`, `at` in metres, the file's own unit, as the viewer draws it). `--grid` draws
the measuring grid, `--preview` draws
Preview's photographic look, and `--camera`, `--size-profile`, `--width` and
`--height` frame and size it. A Quick Edit packet from the viewer (inline JSON, saved
to a temporary `.snapshot.json`, or its path) replays with
`--annotation <packet> --camera authored`, its job's `jointValues` given as `--pose`.
Inspect supplied annotations before editing. Without annotations, the captured
view is optional context; render it when useful to the request.

Link meshes are resolved relative to the description, so they must be present: an
unhydrated Git LFS pointer is not a mesh and fails the snapshot. Run
`git lfs checkout <mesh dir>` first.

OUT is written exactly as given and must be a `.png`; check the exit status before
reading it. Use `cadgen snapshot --help` for the complete current interface.

## References

- Authoring contract (structure, URDF pairing, golden skeleton): `references/authoring-contract.md`
- SRDF workflow (URDF table extraction, edit loop): `references/srdf-workflow.md`
- Planning ledger: `references/planning-ledger.md`
- Validation and verification recipe: `references/validation.md`
- End effectors: `references/end-effectors.md`
- Disabled collisions: `references/disabled-collisions.md`
