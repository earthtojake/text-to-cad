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
one installation, and its engine server, with the CAD app's:

- `cadgen` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.0 cadgen`
- `python` below means `uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.0 python`

The first run downloads that installation; later runs reuse it.

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

Run `cadgen` as Setup defines it. `cadgen doctor <skill-dir>` reports the installation in use and checks that it is the one this skill pins — docs drift silently on another. Validation itself needs nothing beyond the Python standard library; a snapshot draws with the CAD kernel. Use `cadgen <verb> --help` for the complete current interface.

The validator shape is:

```bash
cadgen urdf validate path/to/robot.urdf
cadgen urdf validate path/to/robot.urdf --strict
cadgen urdf validate path/to/robot.urdf --json
cadgen urdf validate path/to/robot.urdf --packages robot_description=/path/to/pkg
cadgen snapshot path/to/robot.urdf review.png
```

The validator collects all findings in one pass (severity, code, XML path) across XML structure, tree topology, joint semantics (limits, mimic, dynamics), geometry, mesh references, materials, inertial physics, and misspelled elements, and prints a summary. One run validates ONE file: `--strict` treats warnings as failures; `--json` prints one line of `{"ok", "path", "issues": [{"severity", "code", "message", "element", "hint"}], "summary"}`, where `element` is the XML path; `--packages NAME=PATH` resolves `package://` mesh URIs and repeats for several roots. It exits nonzero if the target fails. Relative targets resolve from the current working directory; run from the workspace that owns the files.

Validation is a guardrail, not spatial proof: a URDF can pass every structural check while placing a joint in the wrong spot. The ledger and viewer sweep exist for that reason.

## Snapshot Tool

`cadgen snapshot` draws the robot to a PNG still, as the CAD Viewer shows it,
rendered by OCCT:

```bash
cadgen snapshot path/to/robot.urdf review.png
cadgen snapshot path/to/robot.urdf review.png --pose '{"shoulder_pitch": 30, "gripper_slide": 0.02}'
```

The robot opens where the CAD Viewer opens it, every joint at zero. `--pose` gives
joint values over that, in degrees (metres for a prismatic joint), each naming a
joint a person can drive, within its limits, or the request is refused before
anything renders: a fixed joint, a `<mimic>` follower or a `<tcad:four_bar>` input
is refused by name (a follower follows its leader, an input its driver). Each link
is placed by the viewer's own forward kinematics, mimic joints and four-bar
linkages followed, and drawn in one colour of the Parts palette.

A visual is a `box`, `cylinder` or `sphere`, which cadgen meshes itself, or a mesh
file beside the description: an STL or a 3MF (its numbers scaled by the mesh's
`scale`, which must be even) or a GLB (metres). A `package://NAME/...` mesh is found
in the ROS package the description is in: the nearest folder above the `.urdf` named
NAME, or holding a `package.xml` that names it, so keep the description inside its
package folder. A mesh in another format (`.dae`, `.obj`), a remote URI, a package no
folder above the description is, or a missing file is refused by name, and a link mesh
that cannot be loaded fails the snapshot rather than leaving the link out.

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

- Authoring contract (structure, ordering, golden skeleton): `references/authoring-contract.md`
- Design ledger: `references/design-ledger.md`
- Frame semantics: `references/frame-semantics.md`
- Mesh preparation and references: `references/meshes.md`
- Inertials (formulas, scripts, sanity gates): `references/inertials.md`
- URDF edit workflow: `references/urdf-workflow.md`
- Validation and verification recipe: `references/validation.md`
