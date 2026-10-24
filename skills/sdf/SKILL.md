---
name: sdf
description: SDFormat/SDF model and world authoring, validation, and simulator handoff. Use for `.sdf` files, SDFormat XML, models, worlds, links, joints, poses, frames, inertials, visual/collision geometry, mesh URIs, sensors, lights, physics, plugins, includes, Gazebo, static SDF review, or simulator-specific metadata. Do not use for signed-distance-field geometry. Open and visually review existing SDF files in CAD Viewer.
license: MIT
---

# SDF

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill when the deliverable is an SDFormat document. SDFormat describes simulator and world behavior: models, worlds, frames, poses, links, joints, inertials, visuals, collisions, sensors, lights, physics, plugins, includes, and simulator metadata.

This skill is for **SDFormat**, not signed-distance-field geometry.

The `.sdf` file is the source of truth: author and edit the XML directly. There is no `gen_sdf()` contract.

## Setup

Run cadgen through [uv](https://docs.astral.sh/uv/), so this skill's commands share
one installation, and its engine server, with the CAD app's:

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.0 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.0 python`

The first run downloads that installation; later runs reuse it.

## Core rules

1. Author `.sdf` XML directly and validate every created or modified file with `cadgen sdf validate` before reporting completion.
2. Identify the target consumer before editing: Gazebo/libsdformat version, another simulator, visualization-only tooling, model package, or world handoff.
3. Decide document kind: model-level SDF, world-level SDF, or model-in-world. Prefer model-level SDF for reusable robot/object exports.
4. Use SI units unless the target explicitly requires otherwise: meters, kilograms, seconds, radians.
5. Prefer `version="1.12"` for new outputs unless the target consumer constrains the version.
6. Establish the design ledger before writing poses, frames, joint axes, mesh scales, inertials, sensors, or plugins, and keep it as a comment block at the top of the `.sdf`. Use `references/design-ledger.md` and `references/llm-guardrails.md`.
7. Write `relative_to` / `expressed_in` explicitly on every nontrivial pose and axis. Implicit frame defaults are the top SDF failure mode. See `references/frame-semantics.md`.
8. Do not infer spatial transforms from visual impression alone. Derive poses, axes, scale, mass, inertia, and frame names from upstream source data, drawings, simulator documentation, measured values, or explicit assumptions. Never freehand computed numbers — use formulas or a throwaway helper script (inertia tensors, unit conversions).
9. When the robot already has a URDF, derive the SDF from it instead of re-authoring geometry; see `references/interoperability.md`.
10. Regenerate upstream geometry, mesh, robot-description, render, topology, or package assets with their owning workflows before editing SDF that references them.
11. After authoring, run available checks: bundled validation (which runs `gz sdf --check` itself whenever `gz` is on PATH), simulator load, joint motion, and plugin/sensor startup.
12. Report assumptions, skipped checks, unresolved resource paths, and target-specific compatibility risks.

## Scope

Use this skill for SDFormat outputs. Do not use it for signed-distance-field modeling, raw geometry generation, planning semantics, or to paper over incorrect upstream robot/source data unless the task is explicitly simulator-only.

## Show the model

Show the user each model and file you create or change, and any they ask to see.
Snapshots and validation don't replace this. Once a viewer is open, the person is looking
at the model: after an edit, report the run's one line and stop. Never screenshot the
viewer to confirm your own work.

- If your tools include `cad_show` (your host may prefix it), call it with the model's id
  or the file's absolute path, and follow its description for when to call it again.
  `cad_view` reads what the user selected; `cad_screenshot` shows you what they see, for
  when they ask about it.
- Otherwise give the user the page's link once: a model's page is the `view:` line its
  run prints. For a file, run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --host 127.0.0.1 --json FILE [FILE ...]
  ```

  The command ensures this installation's engine, registers each file and prints
  its page, `/<id>`, then exits. Read each file's `url` from `documents` in its one
  JSON line (never guess the port); the URL carries its token query. A page follows
  every later run of its model and every rewrite of its file, so share it once.
  Return that link to the user. If it fails to launch, say so.

Review placement, resources and joints. The viewer does not execute simulator
plugins or validate dynamics; keep simulator checks separate.

## Workflow

1. Locate the target `.sdf` and its consumers.
2. Read or create the design ledger comment block.
3. Read `references/frame-semantics.md` before editing any `<pose>`, `<frame>`, joint axis, `relative_to`, `expressed_in`, nested scope, sensor frame, or plugin frame.
4. Author the XML directly, following the worked examples in `references/examples.md`.
5. Validate the explicit target with `cadgen sdf validate`; treat bundled validation as a guardrail, not simulator proof.
6. Run target-consumer smoke tests when available (`references/smoke-tests.md`).
7. Show the result ([Show the model](#show-the-model)). Static rendering does not execute SDF plugins or read file-authored motion metadata.
8. Report checks run, checks skipped, and assumptions.

## Commands

Run `cadgen` as Setup defines it. `cadgen doctor <skill-dir>` reports the installation in use and checks that it is the one this skill pins — docs drift silently on another. Validation itself needs nothing beyond the Python standard library; a snapshot draws with the CAD kernel. Use `cadgen <verb> --help` for the complete current interface.

```bash
cadgen sdf validate path/to/model.sdf
cadgen sdf validate path/to/model.sdf --strict
cadgen sdf validate path/to/model.sdf --json
cadgen snapshot path/to/model.sdf review.png
```

The validator checks document shape, name scopes, pose/frame graphs, joints, geometry, mesh URIs, inertials, sensors, and plugins, and prints its findings plus a summary. One run validates ONE file: `--strict` treats warnings as failures and `--json` prints one line of `{"ok", "path", "issues": [{"severity", "code", "message", "element", "hint"}], "summary"}`, where `element` is the XML path. It exits nonzero if the target fails.

External checking is on by default:

```bash
cadgen sdf validate path/to/model.sdf --gz-check required
cadgen sdf validate path/to/model.sdf --gz-check never
```

`gz sdf --check` is target-consumer validation. `--gz-check auto` is the default: it runs when `gz` is on PATH, reporting `gz_check_passed` or the tool's own output as the error `gz_check_failed`, and otherwise notes `info: gz_check_unavailable` and carries on. An absent optional tool says nothing about the file, so it never fails a clean document and `--strict` does not change that. `--gz-check required` makes the tool mandatory — a missing `gz` is then an error — and `--gz-check never` skips it outright. gz resolves a document's `<include>`/`<uri>` references itself, so it does not run on a document that names a remote one (`http`, `https`, `fuel`): that is `info: gz_check_remote` (an error under `required`), and `--gz-remote` lets gz fetch them.

## Required report shape

When finishing an SDF task, include a compact report:

```text
Validated: path/to/model.sdf
Checks run:
- bundled SDF validation: passed
- gz sdf --check: skipped, gz not installed
- simulator load: skipped, target simulator unavailable
- viewer review: live link returned, or explicit launch failure
Assumptions:
- Assumed mesh units are meters.
- Assumed lidar frame is coincident with lidar_link.
Risks:
- Camera plugin filename was not verified in the target simulator environment.
```

## Snapshot Tool

`cadgen snapshot` draws the robot to a PNG still, as the CAD Viewer shows it,
rendered by OCCT:

```bash
cadgen snapshot path/to/robot.sdf review.png
cadgen snapshot path/to/robot.sdf review.png --pose '{"arm::elbow": 45}'
```

cadgen resolves the description first: the frame graph (`relative_to`,
`attached_to`) into every link's rest placement, a model nested in the model
included, its links and joints named by scope (`arm::elbow`, the name `--pose`
takes). The robot opens where the CAD Viewer opens it, every joint at zero. `--pose`
gives joint values over that, in degrees (metres for a prismatic joint), each naming
a joint a person can drive, within its limits (a `revolute` joint with no `<limit>`
has none), or the request is refused before anything renders: a fixed joint or a
mimic follower is refused by name (a follower follows its leader). Each link is
drawn in one colour of the Parts palette.

A visual is a `box`, `cylinder`, `sphere` or `capsule`, which cadgen meshes itself,
or a mesh `<uri>` naming an STL, 3MF or GLB file beside the description, or a
`package://NAME/...` file of the ROS package the description is in (the nearest
folder above it named NAME, or holding a `package.xml` that names it). A `plane`,
`heightmap`, `polyline` or `ellipsoid`, a mesh in another format, a `model://` or
remote URI, a package no folder above the description is, a missing file, a pose in a
rotation format other than `euler_rpy`, and a joint the stills cannot pose (a `ball`
or `universal` joint) are refused by name. A link mesh that cannot be loaded fails the
snapshot rather than leaving the link out.

A normal snapshot uses Solid mode and Light appearance. `--display` takes any of the
viewer's display modes (`parts`, `xray`, `hidden-line`, `wireframe`, ...),
`exploded=AMOUNT`, or the display object: `appearance` (`light` or `dark`),
`camera` (projection and focal length) and `clip` (`{"clip": {"axis": "x", "at":
0.05}}`, `at` in metres). `--grid` draws the measuring grid, `--preview` draws
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

- SDF workflow: `references/sdf-workflow.md`
- Worked examples (golden skeletons): `references/examples.md`
- LLM guardrails: `references/llm-guardrails.md`
- Design ledger: `references/design-ledger.md`
- Frame semantics: `references/frame-semantics.md`
- Validation scope: `references/validation.md`
- Smoke tests: `references/smoke-tests.md`
- Interoperability notes (URDF-derived SDF, meshes, Gazebo): `references/interoperability.md`
