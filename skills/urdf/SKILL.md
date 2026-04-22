---
name: urdf
description: URDF generation and validation for robot model outputs. Use when the agent needs to create, edit, regenerate, inspect, or validate `.urdf` files, `gen_urdf()` envelopes, robot links, joints, joint limits, parent/child kinematic structure, visual mesh references, or URDF-specific XML validation. Use the `cad` skill for STEP, STL, DXF, GLB/topology, snapshots, and `@cad[...]` geometry references.
---

# URDF

Use this skill for robot description outputs. URDF work is intentionally separate from ordinary CAD generation because the correctness questions are kinematic, XML, and mesh-reference oriented rather than primarily geometric.

## Workflow

1. Treat the Python source that defines `gen_urdf()` as source of truth. Treat the configured `.urdf` file as generated.
2. For the `gen_urdf()` envelope contract, read `references/generator-contract.md`.
3. For robot description edits, read `references/urdf-workflow.md`.
4. Edit links, joints, limits, axes, origins, inertials, materials, and mesh filenames deliberately.
5. Regenerate only the explicit URDF target with `scripts/gen_urdf`.
6. Use `--summary` for a compact robot/link/joint check after regeneration.
7. For validation expectations, read `references/validation.md`.
8. If the URDF references changed CAD mesh outputs, use the `cad` skill to regenerate the affected STEP/STL/render assets separately.

## Commands

Run with the Python environment for the project or workspace. If the environment lacks the URDF validation runtime packages, install this skill's script dependencies from `requirements.txt`. Invoke the tool as a filesystem script, for example `python <urdf-skill>/scripts/gen_urdf ...`. Relative target paths are resolved from the current working directory; the tool does not prepend a harness root such as `models/`.

- URDF sidecars: `scripts/gen_urdf`

The command interface is target-explicit. Pass the Python generator that defines `gen_urdf()`; use `--summary` for a compact robot/link/joint check.

## References

- URDF generation: `references/gen-urdf.md`
- Generator contract: `references/generator-contract.md`
- URDF edit workflow: `references/urdf-workflow.md`
- URDF validation: `references/validation.md`
