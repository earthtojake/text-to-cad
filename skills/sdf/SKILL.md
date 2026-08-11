---
name: sdf
description: SDFormat/SDF model and world authoring, validation, and simulator handoff. Use for `.sdf` files, SDFormat XML, models, worlds, links, joints, poses, frames, inertials, visual/collision geometry, mesh URIs, sensors, lights, physics, plugins, includes, Gazebo, static SDF review, or simulator-specific metadata. Do not use for signed-distance-field geometry.
---

# SDF

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill when the deliverable is an SDFormat document. SDFormat describes simulator and world behavior: models, worlds, frames, poses, links, joints, inertials, visuals, collisions, sensors, lights, physics, plugins, includes, and simulator metadata.

This skill is for **SDFormat**, not signed-distance-field geometry.

The `.sdf` file is the source of truth: author and edit the XML directly. There is no `gen_sdf()` contract.

## Core rules

1. Author `.sdf` XML directly and validate every created or modified file with `scripts/validate` before reporting completion.
2. Identify the target consumer before editing: Gazebo/libsdformat version, another simulator, visualization-only tooling, model package, or world handoff.
3. Decide document kind: model-level SDF, world-level SDF, or model-in-world. Prefer model-level SDF for reusable robot/object exports.
4. Use SI units unless the target explicitly requires otherwise: meters, kilograms, seconds, radians.
5. Prefer `version="1.12"` for new outputs unless the target consumer constrains the version.
6. Establish the design ledger before writing poses, frames, joint axes, mesh scales, inertials, sensors, or plugins, and keep it as a comment block at the top of the `.sdf`. Use `references/design-ledger.md` and `references/llm-guardrails.md`.
7. Write `relative_to` / `expressed_in` explicitly on every nontrivial pose and axis. Implicit frame defaults are the top SDF failure mode. See `references/frame-semantics.md`.
8. Do not infer spatial transforms from visual impression alone. Derive poses, axes, scale, mass, inertia, and frame names from upstream source data, drawings, simulator documentation, measured values, or explicit assumptions. Never freehand computed numbers — use formulas or a throwaway helper script (inertia tensors, unit conversions).
9. When the robot already has a URDF, derive the SDF from it instead of re-authoring geometry; see `references/interoperability.md`.
10. Regenerate upstream geometry, mesh, robot-description, render, topology, or package assets with their owning workflows before editing SDF that references them.
11. After authoring, run available checks: bundled validation, optional `gz sdf --check`, simulator load, joint motion, and plugin/sensor startup.
12. Report assumptions, skipped checks, unresolved resource paths, and target-specific compatibility risks.

## Scope

Use this skill for SDFormat outputs. Do not use it for signed-distance-field modeling, raw geometry generation, planning semantics, or to paper over incorrect upstream robot/source data unless the task is explicitly simulator-only.

## CAD Viewer Handoff

After completing SDF work that creates or modifies a `.sdf`, you must ALWAYS hand the explicit file path to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); if `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Workflow

1. Locate the target `.sdf` and its consumers.
2. Read or create the design ledger comment block.
3. Read `references/frame-semantics.md` before editing any `<pose>`, `<frame>`, joint axis, `relative_to`, `expressed_in`, nested scope, sensor frame, or plugin frame.
4. Author the XML directly, following the worked examples in `references/examples.md`.
5. Validate the explicit target with `scripts/validate`; treat bundled validation as a guardrail, not simulator proof.
6. Run target-consumer smoke tests when available (`references/smoke-tests.md`).
7. Hand the file to `$cad-viewer`. Static rendering does not execute SDF plugins or read file-authored motion metadata.
8. Report checks run, checks skipped, and assumptions.

## Commands

Run with the project or workspace Python environment. Treat `python` in examples as an interpreter placeholder; if bare `python` is unavailable, substitute `python3`, a project virtualenv interpreter, or the configured interpreter path. The validator uses only the Python standard library.

```bash
python scripts/validate path/to/model.sdf
python scripts/validate path/to/a.sdf path/to/b.sdf
python scripts/validate path/to/model.sdf --strict
```

The validator checks document shape, name scopes, pose/frame graphs, joints, geometry, mesh URIs, inertials, sensors, and plugins, and prints per-file findings plus a summary. `--strict` treats warnings as failures. It exits nonzero if any target fails.

Optional external checking:

```bash
python scripts/validate path/to/model.sdf --gz-check auto
python scripts/validate path/to/model.sdf --gz-check required
python scripts/validate path/to/model.sdf --gz-check never
```

`gz sdf --check` is optional target-consumer validation. It should be reported as skipped when unavailable unless explicitly required.

## Required report shape

When finishing an SDF task, include a compact report:

```text
Validated: path/to/model.sdf
Checks run:
- bundled SDF validation: passed
- gz sdf --check: skipped, gz not installed
- simulator load: skipped, target simulator unavailable
- viewer handoff: `$cad-viewer` link returned
Assumptions:
- Assumed mesh units are meters.
- Assumed lidar frame is coincident with lidar_link.
Risks:
- Camera plugin filename was not verified in the target simulator environment.
```

## Snapshot Tool

`scripts/snapshot` renders the robot to a PNG still or an orbit GIF, using the same shared
CLI and headless browser runtime every rendering skill uses — so a snapshot matches what
the CAD Viewer shows.

```bash
python scripts/snapshot --input path/to/robot.sdf --output review.png
python scripts/snapshot --input path/to/robot.sdf --output turntable.gif --mode orbit
```

It accepts `.sdf` only. Pose the robot with the job field `"jointValues"` (joint name to
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

- SDF workflow: `references/sdf-workflow.md`
- Worked examples (golden skeletons): `references/examples.md`
- LLM guardrails: `references/llm-guardrails.md`
- Design ledger: `references/design-ledger.md`
- Frame semantics: `references/frame-semantics.md`
- Validation scope: `references/validation.md`
- Smoke tests: `references/smoke-tests.md`
- Interoperability notes (URDF-derived SDF, meshes, Gazebo): `references/interoperability.md`
