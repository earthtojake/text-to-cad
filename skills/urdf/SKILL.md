---
name: urdf
description: URDF robot description authoring and validation. Use when creating, editing, inspecting, validating, or debugging `.urdf` files, robot links, joints, limits, inertials, visual/collision geometry, mesh references, frame conventions, or robot-description artifacts. Use the SRDF skill for MoveIt2 semantic groups and IK/path-planning semantics; use the CAD skill for STEP/STL/3MF/DXF/GLB outputs. Open and visually review existing URDF files in CAD Viewer.
license: MIT
---

# URDF

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill for URDF robot-description outputs. Treat URDF work as constrained kinematic modeling, not just XML writing. The main correctness risks are frame placement, joint-axis semantics, unit consistency, mesh scale, and inertial data.

## Setup

Run cadgen through [uv](https://docs.astral.sh/uv/), so this skill's commands share
one installation, and its warm build daemon, with the CAD app's server:

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.19 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.7.19 python`

The first run downloads that installation and the first snapshot its headless
browser; later runs reuse both.

## Core Rules

1. The `.urdf` file is the source of truth. Author and edit URDF XML directly; do not build a Python generation pipeline for it. There is no `gen_urdf()` contract.
2. Before writing or changing URDF XML, establish the robot's frame, joint, geometry, unit, and assumption ledger and embed it as a comment block at the top of the `.urdf` file. See `references/design-ledger.md`.
3. Use URDF frame semantics exactly. Joint origins, link frames, joint axes, and visual/collision/inertial origins use different reference frames. See `references/frame-semantics.md`.
4. Do not infer spatial transforms, mesh units, handedness, axes, or joint signs from vague prose. Use CAD transforms, dimensioned drawings, measured values, existing source data, or explicit documented assumptions.
5. Never freehand numeric values that are the result of computation — inertia tensors, centers of mass, unit conversions across many links, mirrored transforms. Compute them: closed-form formulas for primitives, or a throwaway helper script for mesh-derived values. See `references/inertials.md`.
6. For physical links, model `inertial`, `visual`, and `collision` separately when the target consumer needs them. Frame-only links may intentionally omit mass and geometry.
7. Validate every created or modified `.urdf` with `cadgen urdf validate` before reporting completion. See `references/validation.md`.
8. Helper scripts are allowed and encouraged for computation, but they are scaffolding, not the artifact's source of truth. For complex or genuinely parametric models it is reasonable to keep a model-local helper script on disk next to related source code (for example STEP generator sources) and note it in the ledger; this is optional, and the checked-in `.urdf` remains canonical.

## Show the model

Show the user each file you create or change, and any they ask to see. Snapshots and
validation don't replace this.

- If your tools include `cad_show` (your host may prefix it), use it with the file's
  absolute path, and follow its description for when to call it again. `cad_view` reads
  what the user selected; `cad_screenshot` shows you what they see. Neither is a review
  of your own work.
- Otherwise run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --host 127.0.0.1 --json --detach
  ```

  `--detach` returns once the viewer answers requests and leaves it running in the
  background: always pass it, since a foreground viewer never exits (and piping its
  output through `tail` can hide the URL for good). It starts this machine's one viewer,
  or reuses it. Read `url` from its one JSON line (never guess the port), and for each
  file return `url?file=<its URL-encoded absolute path>`. If it fails to launch, say so.

Review mesh scale and placement, then sweep every movable joint against the
design ledger. A link alone does not complete the [viewer sweep](references/validation.md);
report any checks you could not perform.

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

Run `cadgen` as Setup defines it. `cadgen doctor <skill-dir>` reports the installation in use and checks that it is the one this skill pins — docs drift silently on another. Validation itself needs nothing beyond the Python standard library; only snapshots need the browser. Use `cadgen <verb> --help` for the complete current interface.

The validator shape is:

```bash
cadgen urdf validate path/to/robot.urdf
cadgen urdf validate path/to/robot.urdf --strict
cadgen urdf validate path/to/robot.urdf --json
cadgen urdf validate path/to/robot.urdf --packages robot_description=/path/to/pkg
cadgen urdf snapshot path/to/robot.urdf review.png
```

The validator collects all findings in one pass (severity, code, XML path) across XML structure, tree topology, joint semantics (limits, mimic, dynamics), geometry, mesh references, materials, inertial physics, and misspelled elements, and prints a summary. One run validates ONE file: `--strict` treats warnings as failures; `--json` prints one line of `{"ok", "path", "issues": [{"severity", "code", "message", "element", "hint"}], "summary"}`, where `element` is the XML path; `--packages NAME=PATH` resolves `package://` mesh URIs and repeats for several roots. It exits nonzero if the target fails. Relative targets resolve from the current working directory; run from the workspace that owns the files.

Validation is a guardrail, not spatial proof: a URDF can pass every structural check while placing a joint in the wrong spot. The ledger and viewer sweep exist for that reason.

## Snapshot Tool

`cadgen urdf snapshot` renders the robot to a PNG still, using the same shared
CLI and headless browser runtime every rendering skill uses — so a snapshot matches what
the CAD Viewer shows.

```bash
cadgen urdf snapshot path/to/robot.urdf review.png
```

It accepts `.urdf` only. Pose the robot with `--joint-values` — `{joint: value}` JSON in degrees (metres for a
prismatic joint), each naming a joint a person can drive, within its limits, or the request is
refused before anything renders: a fixed joint or a `<mimic>` follower is refused by name (a
follower follows its leader), and so is a leader value that would push a follower past the
follower's own limits. Joints you do not name stay at their defaults, where the CAD Viewer
opens the robot (the `"jointValues"` job field is the same thing in a packet). The snapshot
draws the robot with the viewer's own scene, so it shows what the viewer shows: cadgen
resolves the description first, meshes a `box`, `cylinder` or `sphere` itself, and refuses by
name a visual it cannot draw — a mesh that is not an STL, 3MF or GLB file beside the
description (`.dae`, `.obj` and `.ply` files are not drawn; `package://` and remote URIs are
not resolved) or a mesh file that is missing. A link mesh that cannot be loaded fails the
snapshot rather than leaving the link out. Robots are authored in metres and are framed on the
robot scene scale automatically.

A normal snapshot uses the Solid preset and Light appearance; omitted groups inherit preset defaults.
Pass `--display render` for the shared photographic scene. Inline display JSON and
JSON files use grouped settings such as `lighting`, `background`, and `floor`;
`appearance` is `light` (default) or `dark`. Projection and focal length belong
in `display.camera`. Top-level `--camera` and `--joint-values` remain active in every display
mode. The display modes are `solid` and `render`: `edges`, `clip`, `exploded`, the
`xray`, `hidden-line` and `wireframe` modes and the `hidden`/`off` surface styles
describe a STEP model's CAD edges, parts and solids, and are refused by name here.

Link meshes are resolved relative to the description, so they must be present: an
unhydrated Git LFS pointer is not a mesh and fails the snapshot. Run
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
