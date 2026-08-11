# URDF Workflow

Use this reference when editing robot-description structure, frame placement, mesh references, inertial data, or any `.urdf` output.

## Edit Loop

1. Locate the target `.urdf`. It is the source of truth; edit it directly.
2. Identify target consumers and strictness requirements: visualization, TF tree, simulation, planning, or real robot integration.
3. Read the design-ledger comment block at the top of the file; create it if missing (see `references/design-ledger.md`). Update the ledger in the same edit that changes modeled facts.
4. If links reference meshes, prepare or verify the per-link assets first (see `references/meshes.md`).
5. Apply URDF frame semantics exactly: joint origin in parent frame, child link frame at joint frame, joint axis in joint frame, visual/collision/inertial origins in link frame (see `references/frame-semantics.md`).
6. Author links, joints, limits, axes, origins, inertials, and geometry per `references/authoring-contract.md`. Compute derived numbers — inertia tensors, unit conversions, mirrored transforms — with formulas or a helper script; never freehand them (see `references/inertials.md`).
7. Validate with `python scripts/validate <file.urdf>` and fix findings until clean.
8. Run the rest of the verification recipe in `references/validation.md`: external tools when available, then a `$cad-viewer` sweep of every movable joint against the ledger's positive-motion statements.
9. Report smoke tests run, checks skipped, and remaining assumptions.

## Spatial-Reasoning Guardrails

LLMs are prone to plausible-looking spatial mistakes. Use these guardrails:

- Do not infer dimensions, handedness, axes, mesh units, or joint signs from vague descriptions.
- Do not silently mirror left/right parts. A mirrored chain changes axis signs and off-diagonal inertia terms; derive the mirror transform explicitly (helper script) and record it in the ledger.
- Do not assume visual mesh origin equals link frame, collision frame, or center of mass.
- Do not assume CAD mesh units are meters. STL files carry no reliable unit metadata.
- Do not encode a kinematic correction by offsetting only the visual mesh; correct the link and joint frames unless the visual mesh is genuinely offset.
- Preserve existing proven transforms unless the task explicitly requires changing them.
- Record every assumed value in the ledger comment block; in helper scripts, name constants by physical meaning (`ASSUMED_BASE_TO_SHOULDER_Z_M`).

## Standard Link Tags

Use these tags for each link that represents physical robot geometry:

- `inertial`: mass, center of mass, and inertia tensor used by simulators.
- `visual`: display geometry and optional material.
- `collision`: contact geometry used by physics and planning.

Frame-only links, such as `base_footprint`, optical frames, or tool-center marker frames, may intentionally omit these tags when they represent no physical mass or geometry.

For movable physical links, avoid zero or missing mass unless the target simulator explicitly supports that modeling choice. If exact mass properties are unavailable, use a documented approximation and make the approximation easy to replace later.

## Joint Authoring

For every joint, confirm:

- parent and child direction are correct;
- joint origin is expressed in the parent link frame and places the child frame at zero position;
- non-fixed joint axis is expressed in the joint frame, preferably a signed unit vector along a principal axis;
- positive motion is stated in words in the ledger ("positive shoulder_pitch raises the arm") — the axis sign is part of the model, not a cosmetic detail;
- revolute limits are radians, prismatic limits are meters;
- continuous joints are not given artificial finite lower/upper limits;
- fixed joints are used for frame relationships and rigid assemblies.

Supported joint types may vary by consumer. The bundled validator supports `fixed`, `continuous`, `revolute`, and `prismatic`; do not author `floating` or `planar` joints unless the consumer and validation path support them.

After authoring, the axis-sign check is non-negotiable: sweep the joint in the viewer and compare the motion with the ledger statement. Structural validation cannot catch a flipped sign.

## Collision Geometry

Add collision geometry under each `<link>` that should participate in physics, contact, or collision-aware planning. Do not encode collision behavior on joints.

Use one or more `<collision>` blocks per link. The `<origin>` is expressed in the link frame, just like `<visual>`, and mesh scales must match the units of the exported mesh.

Prefer simplified collision geometry over detailed visual meshes, from simplest to most specific:

- primitive `<box>`, `<cylinder>`, or `<sphere>` geometry when it approximates the part well;
- a coarse, closed collision mesh exported from CAD;
- the visual mesh as a temporary fallback for loading and smoke tests.

## Inertials

For each physical link, use an explicit `inertial` block when the target simulator or dynamics consumer needs mass properties. The inertial origin is the center of mass in the link frame — not automatically the visual mesh origin, collision origin, or link origin.

All values are computed or copied from source data, never freehanded; see `references/inertials.md` for formulas, the mesh-script recipe, and sanity gates.

## Downstream Ownership

- CAD or mesh workflows own mesh generation and per-link splitting/export.
- This skill owns the `.urdf`: references, scales, placements, structure.
- SRDF/MoveIt workflows own semantic groups, named joint poses via `<group_state>`, and planning metadata. Renaming links or joints here breaks them; update both in the same task.
