# SDF authoring

Use this reference when editing SDF robot model structure, world structure, mesh references, or simulator metadata. The deliverable is an SDFormat document: models, worlds, frames, poses, links, joints, inertials, visuals, collisions, sensors, lights, physics, plugins, includes, and simulator metadata. This is **SDFormat**, not signed-distance-field geometry: do not use it for signed-distance-field modeling, raw geometry generation, planning semantics, or to paper over incorrect upstream robot/source data unless the task is explicitly simulator-only.

Prefer `version="1.12"` for new outputs unless the target consumer constrains the version, and SI units (meters, kilograms, seconds, radians) unless the target explicitly requires otherwise.

## Edit loop

1. Locate the target `.sdf`. It is the source of truth; author and edit the XML directly.
2. Identify the target consumer and required SDFormat version.
3. Decide whether the output is model-level, world-level, or model-in-world.
4. Fill or update the design ledger before writing XML; keep the compact form as a comment block in the `.sdf` (see [sdf-ledger.md](sdf-ledger.md)).
5. If the model describes a robot that already has a URDF, derive the SDF from that URDF rather than re-authoring geometry from scratch (see [interoperability.md](interoperability.md#sdf-from-a-urdf)).
6. For every pose and axis, state the frame in which it is expressed. Write `relative_to` / `expressed_in` explicitly wherever ambiguity would otherwise remain (see [sdf-frames.md](sdf-frames.md)).
7. Author the XML per the golden skeletons in [sdf-examples.md](sdf-examples.md). Compute derived numbers — inertia tensors, unit conversions — with formulas or a throwaway helper script; never freehand them ([inertials.md](inertials.md)). Mesh URIs and scale: [meshes.md](meshes.md).
8. Validate with `cad sdf check <file.sdf>`; review errors as structural guardrails, not exhaustive simulator proof ([sdf-checks.md](sdf-checks.md)).
9. Show new or modified `.sdf` files ([Show the model](../SKILL.md#show-the-model)). Report any failure explicitly.
10. Run available smoke tests (`gz sdf --check`, simulator load; [sdf-checks.md](sdf-checks.md#smoke-tests)).
11. Report assumptions, skipped checks, unresolved resource paths, and target-specific compatibility risks ([guardrails.md](guardrails.md#the-report)).

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

## Plugins and sensors

For plugins and sensors, record:

- plugin filename or sensor type;
- expected simulator distribution/version;
- topics, frames, update rates, namespaces;
- parameter source;
- startup smoke test result.

Do not invent plugin parameters. Incorrect plugin XML can pass lightweight validation and still fail at simulator load time.

CAD Viewer reviews SDF files as static model/world structure through live viewer links. It lists a plugin and never runs one, so no plugin gets motion out of it: pose joints by hand in the Viewer, or with `--pose` in a snapshot. Use simulator-native controllers, plugins, or test harnesses for simulator behavior.

## Existing SDF inspection

When inspecting existing `.sdf` files, separate three questions:

1. Is the XML structurally valid enough for the bundled validator?
2. Is it compatible with the target SDFormat/libsdformat/simulator version?
3. Does it satisfy this project's packaging, mesh, and workflow policy?

Do not reject valid SDF solely because it violates a project preference unless the task or repository policy requires that preference.
