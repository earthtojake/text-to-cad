---
name: sdf
description: SDFormat/SDF model and world generation, validation, and simulator handoff. Use for `.sdf` files, SDFormat XML, Python `gen_sdf()` sources, models, worlds, links, joints, poses, frames, inertials, visual/collision geometry, mesh URIs, sensors, lights, physics, plugins, includes, Gazebo, static SDF review, or simulator-specific metadata. Do not use for signed-distance-field geometry.
---

# SDF

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill when the deliverable is an SDFormat document or a Python `gen_sdf()` source. SDFormat describes simulator and world behavior: models, worlds, frames, poses, links, joints, inertials, visuals, collisions, sensors, lights, physics, plugins, includes, and simulator metadata.

This skill is for **SDFormat**, not signed-distance-field geometry.

## Core rules

1. Treat the Python file defining `gen_sdf()` as source of truth. Treat configured `.sdf` files as generated artifacts unless the user explicitly asks for direct XML editing.
2. Identify the target consumer before editing: Gazebo/libsdformat version, another simulator, visualization-only tooling, model package, or world handoff.
3. Decide document kind: model-level SDF, world-level SDF, or model-in-world. Prefer model-level SDF for reusable robot/object exports.
4. Use SI units unless the target explicitly requires otherwise: meters, kilograms, seconds, radians.
5. Prefer `version="1.12"` for new outputs unless the target consumer constrains the version.
6. Establish the design ledger before writing poses, frames, joint axes, mesh scales, inertials, sensors, or plugins. Use `references/design-ledger.md` and `references/llm-guardrails.md`.
7. Do not infer spatial transforms from visual impression alone. Derive poses, axes, scale, mass, inertia, and frame names from upstream source data, drawings, simulator documentation, measured values, or explicit assumptions.
8. Prefer helper functions and named constants over large XML string literals. Hidden numbers are a common SDF failure mode.
9. Generate only explicit targets with `scripts/sdf` or the repository's existing SDF launcher. Do not run directory-wide generation.
10. Regenerate upstream geometry, mesh, robot-description, render, topology, or package assets with their owning workflows before regenerating SDF that references them.
11. After generation, run available checks: bundled validation, optional `gz sdf --check`, simulator load, joint motion, and plugin/sensor startup.
12. Report assumptions, skipped checks, unresolved resource paths, and target-specific compatibility risks.

## Scope

Use this skill for SDFormat outputs and generators. Do not use it for signed-distance-field modeling, raw geometry generation, planning semantics, or to paper over incorrect upstream robot/source data unless the task is explicitly simulator-only.

## CAD Viewer Handoff

After completing SDF work that creates or modifies a `.sdf`, you must ALWAYS hand the explicit file path to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); if `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Workflow

1. Locate the `gen_sdf()` source and intended `.sdf` output.
2. Read or create the design ledger.
3. Read `references/frame-semantics.md` before editing any `<pose>`, `<frame>`, joint axis, `relative_to`, `expressed_in`, nested scope, sensor frame, or plugin frame.
4. Edit the generator source, not generated XML.
5. Use optional builder helpers when they make the generated structure clearer; raw ElementTree is still allowed.
6. Regenerate the explicit target.
7. Treat bundled validation as a guardrail, not simulator proof.
8. Run target-consumer smoke tests when available.
9. Report checks run, checks skipped, and assumptions. Static rendering does not execute SDF plugins or read file-authored motion metadata.

## Commands

Run with the project or workspace Python environment. Treat `python` in examples as an interpreter placeholder; if bare `python` is unavailable, substitute `python3`, a project virtualenv interpreter, or the configured interpreter path.

```bash
python scripts/sdf path/to/source.py
python scripts/sdf path/to/source.py -o path/to/output.sdf
python scripts/sdf path/to/a.py=out/a.sdf path/to/b.py=out/b.sdf
```

Plain Python targets write sibling `.sdf` files beside their sources. `-o` / `--output` is valid only with one plain target. `SOURCE.py=OUTPUT.sdf` supports custom multi-target destinations.

If the runtime supports optional external checking:

```bash
python scripts/sdf path/to/source.py --gz-check auto
python scripts/sdf path/to/source.py --gz-check required
python scripts/sdf path/to/source.py --gz-check never
```

`gz sdf --check` is optional target-consumer validation. It should be reported as skipped when unavailable unless explicitly required.

## Required report shape

When finishing an SDF task, include a compact report:

```text
Generated: path/to/model.sdf from path/to/model.py
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

## References

- Generation command: `references/gen-sdf.md`
- Generator contract: `references/generator-contract.md`
- SDF workflow: `references/sdf-workflow.md`
- Builder helpers: `references/builder-helpers.md`
- LLM guardrails: `references/llm-guardrails.md`
- Design ledger: `references/design-ledger.md`
- Frame semantics: `references/frame-semantics.md`
- Validation scope: `references/validation.md`
- Smoke tests: `references/smoke-tests.md`
- Interoperability notes: `references/interoperability.md`
- Examples: `references/examples.md`
- Runtime notes and current limitations: `references/implementation-notes.md`
