---
name: urdf
description: URDF robot description authoring and validation. Use when creating, editing, inspecting, validating, or debugging `.urdf` files, robot links, joints, limits, inertials, visual/collision geometry, mesh references, frame conventions, or robot-description artifacts. Use the SRDF skill for MoveIt2 semantic groups and IK/path-planning semantics; use the CAD skill for STEP/STL/3MF/DXF/GLB outputs.
---

# URDF

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill for URDF robot-description outputs. Treat URDF work as constrained kinematic modeling, not just XML writing. The main correctness risks are frame placement, joint-axis semantics, unit consistency, mesh scale, and inertial data.

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

## Core Rules

1. The `.urdf` file is the source of truth. Author and edit URDF XML directly; do not build a Python generation pipeline for it. There is no `gen_urdf()` contract.
2. Before writing or changing URDF XML, establish the robot's frame, joint, geometry, unit, and assumption ledger and embed it as a comment block at the top of the `.urdf` file. See `references/design-ledger.md`.
3. Use URDF frame semantics exactly. Joint origins, link frames, joint axes, and visual/collision/inertial origins use different reference frames. See `references/frame-semantics.md`.
4. Do not infer spatial transforms, mesh units, handedness, axes, or joint signs from vague prose. Use CAD transforms, dimensioned drawings, measured values, existing source data, or explicit documented assumptions.
5. Never freehand numeric values that are the result of computation — inertia tensors, centers of mass, unit conversions across many links, mirrored transforms. Compute them: closed-form formulas for primitives, or a throwaway helper script for mesh-derived values. See `references/inertials.md`.
6. For physical links, model `inertial`, `visual`, and `collision` separately when the target consumer needs them. Frame-only links may intentionally omit mass and geometry.
7. Validate every created or modified `.urdf` with `cadgen urdf validate` before reporting completion. See `references/validation.md`.
8. Helper scripts are allowed and encouraged for computation, but they are scaffolding, not the artifact's source of truth. For complex or genuinely parametric models it is reasonable to keep a model-local helper script on disk next to related source code (for example STEP generator sources) and note it in the ledger; this is optional, and the checked-in `.urdf` remains canonical.

## CAD Viewer Handoff

After completing URDF work that creates or modifies a `.urdf`, you must ALWAYS hand the explicit file path to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); if `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Workflow

1. Identify the target `.urdf` file and its consumers: RViz, robot_state_publisher, Gazebo/Ignition, MoveIt, a real robot driver, or another simulator.
2. Read or create the design ledger before editing frames, origins, axes, mesh scale, limits, or inertials. Keep the ledger as a comment block in the `.urdf` itself.
3. Prepare mesh assets first when links reference meshes: one mesh per link, exported in that link's frame by the owning CAD/mesh workflow. See `references/meshes.md`.
4. Author or edit the URDF XML directly, following `references/authoring-contract.md` for structure, ordering, and naming.
5. Compute — never guess — inertials and other derived numbers. See `references/inertials.md`.
6. Validate with `cadgen urdf validate`; fix findings and re-validate until clean.
7. Run the verification recipe in `references/validation.md`: external tools when available (`check_urdf`), then a viewer review sweeping every joint.
8. Report remaining assumptions, unchecked spatial data, and validation gaps.

## Commands

Run with the Python environment for the project or workspace. Treat `python` in examples as an interpreter placeholder; if bare `python` is unavailable, substitute `python3`, a project virtualenv interpreter, or the configured interpreter path. The validator uses only the Python standard library.

The validator shape is:

```bash
cadgen urdf validate path/to/robot.urdf
cadgen urdf validate path/to/robot.urdf --strict
cadgen urdf validate path/to/robot.urdf --json
cadgen urdf validate path/to/robot.urdf --packages robot_description=/path/to/pkg
cadgen urdf snapshot path/to/robot.urdf review.png
```

The validator collects all findings in one pass (severity, code, XML path) across XML structure, tree topology, joint semantics (limits, mimic, dynamics), geometry, mesh references, materials, inertial physics, and misspelled elements, and prints a summary. One run validates ONE file: `--strict` treats warnings as failures; `--json` emits the machine-readable findings document; `--packages NAME=PATH` resolves `package://` mesh URIs and repeats for several roots. It exits nonzero if the target fails. Relative targets resolve from the current working directory; run from the workspace that owns the files.

Validation is a guardrail, not spatial proof: a URDF can pass every structural check while placing a joint in the wrong spot. The ledger and viewer sweep exist for that reason.

## Snapshot Tool

`cadgen urdf snapshot` renders the robot to a PNG still, using the same shared
CLI and headless browser runtime every rendering skill uses — so a snapshot matches what
the CAD Viewer shows.

```bash
cadgen urdf snapshot path/to/robot.urdf review.png
```

It accepts `.urdf` only. Pose the robot with `--joint-values` — `{joint: degrees}` JSON,
joints you do not name staying at the rest pose (the `"jointValues"` job field is the same
thing in a packet). Robots are authored in metres and are framed on the robot scene scale
automatically.

Theme settings live under one `--theme`, mirroring the viewer's Theme tab. The default
theme is `snapshot` — Workbench Light with the ground grid, origin axis and shadows
removed, because in a still image those read as geometry. There is no `--display` on this
door: display settings (mode, clip, exploded, edges) are CAD topology settings, and a robot
carries none.

Link meshes are resolved relative to the description, so they must be present: an
unhydrated Git LFS pointer fails as "No link mesh loaded for robot". Run
`git lfs checkout <mesh dir>` first.

The grammar is `cadgen urdf snapshot TARGET [OUT] [flags]`, the same one every
format door uses. Use `cadgen urdf snapshot --help` for the complete current
interface — the flags a robot cannot act on are absent from it, not refused by it.

## References

- Authoring contract (structure, ordering, golden skeleton): `references/authoring-contract.md`
- Design ledger: `references/design-ledger.md`
- Frame semantics: `references/frame-semantics.md`
- Mesh preparation and references: `references/meshes.md`
- Inertials (formulas, scripts, sanity gates): `references/inertials.md`
- URDF edit workflow: `references/urdf-workflow.md`
- Validation and verification recipe: `references/validation.md`
