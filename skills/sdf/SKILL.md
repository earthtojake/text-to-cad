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

## Setup

This skill's commands are thin entrypoints over the `cadgen` distribution, which
carries the Python build runtime and the JavaScript it executes. Install it once:

```bash
python -m pip install -r requirements.txt
```

Rendering additionally needs a browser, which pip cannot supply:

```bash
python -m playwright install chromium
```

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

## CAD Viewer Handoff

After completing SDF work that creates or modifies a `.sdf`, you must ALWAYS hand the explicit file path to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); if `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Workflow

1. Locate the target `.sdf` and its consumers.
2. Read or create the design ledger comment block.
3. Read `references/frame-semantics.md` before editing any `<pose>`, `<frame>`, joint axis, `relative_to`, `expressed_in`, nested scope, sensor frame, or plugin frame.
4. Author the XML directly, following the worked examples in `references/examples.md`.
5. Validate the explicit target with `cadgen sdf validate`; treat bundled validation as a guardrail, not simulator proof.
6. Run target-consumer smoke tests when available (`references/smoke-tests.md`).
7. Hand the file to `$cad-viewer`. Static rendering does not execute SDF plugins or read file-authored motion metadata.
8. Report checks run, checks skipped, and assumptions.

## Commands

Run `cadgen` from the Python environment this skill's `requirements.txt` was installed into (`python -m cadgen.cli <verb>` with that interpreter is the PATH-independent equivalent). `cadgen doctor <skill-dir>` verifies the installed cadgen matches this skill's pin — docs drift silently on a mismatched install. Validation itself needs nothing beyond the Python standard library; only snapshots need the browser. Use `cadgen <verb> --help` for the complete current interface.

```bash
cadgen sdf validate path/to/model.sdf
cadgen sdf validate path/to/model.sdf --strict
cadgen sdf validate path/to/model.sdf --json
cadgen sdf snapshot path/to/model.sdf review.png
```

The validator checks document shape, name scopes, pose/frame graphs, joints, geometry, mesh URIs, inertials, sensors, and plugins, and prints its findings plus a summary. One run validates ONE file: `--strict` treats warnings as failures and `--json` prints one line of `{"ok", "path", "issues": [{"severity", "code", "message", "element", "hint"}], "summary"}`, where `element` is the XML path. It exits nonzero if the target fails.

External checking is on by default:

```bash
cadgen sdf validate path/to/model.sdf --gz-check required
cadgen sdf validate path/to/model.sdf --gz-check never
```

`gz sdf --check` is target-consumer validation. `--gz-check auto` is the default: it runs when `gz` is on PATH, reporting `gz_check_passed` or the tool's own output as the error `gz_check_failed`, and otherwise notes `info: gz_check_unavailable` and carries on. An absent optional tool says nothing about the file, so it never fails a clean document and `--strict` does not change that. `--gz-check required` makes the tool mandatory — a missing `gz` is then an error — and `--gz-check never` skips it outright.

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

`cadgen sdf snapshot` renders the robot to a PNG still, using the same shared
CLI and headless browser runtime every rendering skill uses — so a snapshot matches what
the CAD Viewer shows.

```bash
cadgen sdf snapshot path/to/robot.sdf review.png
```

It accepts `.sdf` only (a format door, same `TARGET [OUT]` grammar as the rest). Pose the robot with `--joint-values` — `{joint: degrees}` JSON,
joints you do not name staying at the rest pose (the `"jointValues"` job field is the same
thing in a packet). Robots are authored in metres and are framed on the robot scene scale
automatically.

A normal snapshot uses deterministic light CAD lighting and hides grid and axis guides.
Pass `--render light` or `--render dark` (or photographic Render JSON or a file path)
for the shared Render scene. An envelope with no `studio` resolves Light in the CLI.
Set its camera inside Render JSON; top-level `--camera`, `--display`, and `--joint-values`
control normal snapshots and cannot be combined with Render. Robot link meshes have no CAD-edge or exploded assembly
topology, so those display combinations are rejected clearly.

Link meshes are resolved relative to the description, so they must be present: an
unhydrated Git LFS pointer fails as "No link mesh loaded for robot". Run
`git lfs checkout <mesh dir>` first.

The grammar is `cadgen sdf snapshot TARGET [OUT] [flags]`, the same one every
format door uses. Use `cadgen sdf snapshot --help` for the complete current
interface — the flags a robot cannot act on are absent from it, not refused by it.

## References

- SDF workflow: `references/sdf-workflow.md`
- Worked examples (golden skeletons): `references/examples.md`
- LLM guardrails: `references/llm-guardrails.md`
- Design ledger: `references/design-ledger.md`
- Frame semantics: `references/frame-semantics.md`
- Validation scope: `references/validation.md`
- Smoke tests: `references/smoke-tests.md`
- Interoperability notes (URDF-derived SDF, meshes, Gazebo): `references/interoperability.md`
