# SDF workflow

Use this reference when editing SDF robot model structure, world structure, mesh references, or simulator metadata.

## Edit loop

1. Locate the target `.sdf`. It is the source of truth; author and edit the XML directly.
2. Identify the target consumer and required SDFormat version.
3. Decide whether the output is model-level, world-level, or model-in-world.
4. Fill or update the design ledger before writing XML; keep the compact form as a comment block in the `.sdf` (see `references/design-ledger.md`).
5. If the model describes a robot that already has a URDF, derive the SDF from that URDF rather than re-authoring geometry from scratch (see `references/interoperability.md`).
6. For every pose and axis, state the frame in which it is expressed. Write `relative_to` / `expressed_in` explicitly wherever ambiguity would otherwise remain (see `references/frame-semantics.md`).
7. Author the XML per `references/authoring-contract.md`. Compute derived numbers — inertia tensors, unit conversions — with formulas or a throwaway helper script; never freehand them.
8. Validate with `python scripts/validate <file.sdf>`; review errors as structural guardrails, not exhaustive simulator proof.
9. Hand new or modified `.sdf` files to `$cad-viewer` for live viewer links when available.
10. Run available smoke tests (`gz sdf --check`, simulator load).
11. Report assumptions and skipped checks.

## Model vs world

Use **model-level SDF** when exporting a reusable robot or object model that another world can include.

Use **world-level SDF** when the task includes:

- physics engine settings;
- lights or scene setup;
- terrain or ground plane;
- multiple initial model placements;
- world plugins;
- includes of external model packages;
- simulator scene setup.

Use **model-in-world SDF** when the task explicitly needs both an inline model and world-specific context.

The lightweight validator should allow pure world-only documents. A world-only document with lights, physics, actors, or includes can be valid SDFormat even when it contains no inline `<model>`.

## Mesh references

SDF mesh URIs should be stable from the `.sdf` file's perspective or use a simulator/package URI convention understood by the consumer.

Good URI choices include:

- relative paths beside the SDF when the model is self-contained;
- `model://...` for simulator model packages;
- `package://...` when the simulator environment resolves package roots;
- `fuel://...`, `http://...`, or `https://...` only when the consumer is expected to fetch external assets.

Mesh assets themselves are owned by the CAD/mesh workflow: one asset per link, exported in the link's own frame, with source units recorded. If a mesh is wrong, fix the export, not the SDF poses.

## Inertials and physics

For dynamic models, inertial data is simulation-critical. If inertials are estimated, record the approximation method. Do not copy visual origins into inertial origins unless that is physically justified.

Collision geometry should be selected for stable and fast physics, not visual fidelity. Use primitive or simplified collision geometry when possible.

## Plugins and sensors

For plugins and sensors, record:

- plugin filename or sensor type;
- expected simulator distribution/version;
- topics, frames, update rates, namespaces;
- parameter source;
- startup smoke test result.

Do not invent plugin parameters. Incorrect plugin XML can pass lightweight validation and still fail at simulator load time.

CAD Viewer reviews SDF files as static model/world structure through `$cad-viewer` links. Do not add Explorer-only motion plugins; use simulator-native controllers, plugins, or test harnesses for simulator behavior.

## Existing SDF inspection

When inspecting existing `.sdf` files, separate three questions:

1. Is the XML structurally valid enough for the bundled validator?
2. Is it compatible with the target SDFormat/libsdformat/simulator version?
3. Does it satisfy this project's packaging, mesh, and workflow policy?

Do not reject valid SDF solely because it violates a project preference unless the task or repository policy requires that preference.
