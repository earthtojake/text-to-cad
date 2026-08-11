# URDF Validation and Verification

Every created or modified `.urdf` runs this recipe before the task is reported complete. Validation is a guardrail, not a substitute for the design ledger or a viewer/consumer smoke test: a URDF can pass every structural check while still having incorrect spatial assumptions.

## Recipe

Run in order; stop and fix at the first failing step:

1. **Bundled validator** (always): `python scripts/validate path/to/robot.urdf`. It collects *all* findings in one pass (severity, code, XML path); fix them and re-run until clean. Use `--strict` to fail on warnings, `--format json` for machine-readable output, and `--package NAME=PATH` to resolve `package://` mesh URIs.
2. **External URDF tools** (when installed): `check_urdf robot.urdf` (ros liburdfdom) parses with the reference parser and prints the link tree. Report as skipped when unavailable.
3. **Viewer sweep** (whenever `$cad-viewer` is available): load the file, confirm meshes appear at sane scale and pose, then sweep **every** movable joint through its limits and compare the motion against the ledger's positive-motion statement, joint by joint. This is the only step that catches a wrong axis sign.
4. **Consumer smoke test** (when the target runtime is available): RViz display, robot_state_publisher TF tree, Gazebo/Ignition load, or MoveIt model load.

Report which steps ran and which were skipped.

## What the Bundled Validator Checks

Structure:

- root element is `<robot>` with a non-empty name;
- links and joints have unique, non-empty names;
- every joint has parent and child links that exist;
- each child link has at most one parent; exactly one root link; connected, acyclic, exactly `links - 1` joints.

Joints:

- type is `fixed`, `continuous`, `revolute`, or `prismatic` (`floating`/`planar` are rejected — use them only with a consumer-specific validation path);
- origins have three finite values for `xyz`/`rpy` when present;
- movable joints have a nonzero, finite axis; warnings for an omitted axis (spec default `1 0 0`) and non-unit axes;
- revolute/prismatic joints have finite `lower <= upper` limits; `effort`/`velocity` must be non-negative and warn when omitted; fixed/continuous joints warn when they carry ignored position limits;
- `<dynamics>` damping/friction must be non-negative;
- `<mimic>` must reference an existing, non-fixed, non-self joint with no mimic cycles;
- joint names colliding with link names warn (URDF-to-SDF conversion breaks).

Geometry and meshes:

- each visual/collision has exactly one geometry child from `mesh`, `box`, `cylinder`, `sphere`;
- primitive dimensions are positive and finite; mesh `scale` values nonzero and finite (negative scale mirrors the mesh and warns — consumer support varies);
- local mesh paths resolve to existing files relative to the `.urdf`; `package://` and remote URIs pass with a warning because resolution is consumer-specific.

Inertials (when present):

- at most one `<inertial>` per link; `mass` positive and finite; all six tensor values present and finite;
- diagonal values positive; the full tensor must be positive semidefinite (eigenvalue check — catches bad off-diagonals);
- principal moments violating the triangle inequality (`l1 + l2 >= l3`) warn (real-world exports often violate slightly; `--strict` promotes it);
- movable links with geometry but no inertial warn.

Authoring hygiene:

- unknown elements under `<robot>`, `<link>`, `<joint>`, `<visual>`, `<collision>`, and `<inertial>` warn — misspelled elements are otherwise silently ignored by consumers (namespaced extensions like `<gazebo>` pass through);
- visual `<material name>` references without a matching definition warn;
- mesh extensions outside the common set (stl/dae/obj/3mf/glb/gltf/ply) warn.

The validator intentionally does not require inertials or collision geometry on every link — that is target-consumer policy, decided in the ledger (see `references/inertials.md`). When a file fails a *project* policy rather than these checks, report it as policy failure, not URDF invalidity.

## What Validation Cannot Prove

- That a joint origin or axis matches the physical robot — only the ledger plus the viewer sweep checks that.
- That mesh source units match the declared `scale`.
- That inertial values match the actual part, beyond plausibility gates.
- That `package://` URIs resolve in the target environment.

Call these out explicitly in the final report when they were not independently verified.

## Failure Handling

When validation fails: fix the `.urdf` (and the ledger if the modeled facts changed), re-run the validator, and continue the recipe from the top. If the root cause is a bad mesh export, fix it in the owning CAD workflow first — do not paper over asset problems with URDF origins.
