# SDF validation

Every created or modified `.sdf` is validated with `python scripts/validate <file.sdf>` before the task is reported complete. The validator collects all findings in one pass (severity, code, XML path); `--strict` fails on warnings and `--format json` emits a machine-readable document. The bundled validation is dependency-light and intended to catch common structural errors. It is not a replacement for libsdformat, Gazebo, or target-simulator validation.

## Validation model

The validator should produce structured diagnostics with severities:

- `error`: invalid or unsafe enough to block writing output;
- `warning`: likely problem or unverified simulator behavior; output can be written unless `--strict` is used;
- `info`: assumption, skipped check, or useful context.

`--strict` treats warnings as failures.

## Bundled checks

### Root and document shape

The validator should check that:

- the root element is `<sdf>`;
- the root has a non-empty `version` attribute;
- the version looks like `major.minor`;
- the document contains meaningful SDF content such as a model, world, actor, light, include, or plugin;
- structurally valid pure world files are accepted even when they contain no inline model.

### Names and scopes

The validator should check that:

- world names are non-empty and unique at root scope;
- root model names are non-empty and unique;
- model link, joint, frame, sensor, light, visual, and collision names are non-empty where required and unique within their owner scope;
- links, joints, frames, and nested models share one frame-graph namespace per scope: cross-type name collisions are errors;
- a model with no links, includes, or nested models is an error;
- unknown elements under model/link/joint/visual/collision/inertial warn (misspelled elements are otherwise silently ignored);
- the version must be a known SDFormat release (1.4–1.12) or it warns;
- world- and link-level lights need a valid type (`point`/`directional`/`spot`) and validated poses;
- duplicate names are reported with a path and scope.

### Poses

The validator should check all `<pose>` elements:

- default `rotation_format="euler_rpy"` has exactly six finite values;
- `rotation_format="quat_xyzw"` has exactly seven finite values;
- unsupported `rotation_format` is an error;
- quaternion values are approximately normalized;
- `degrees="true"` is a warning unless strict mode is enabled;
- nontrivial omitted `relative_to` is a warning;
- `relative_to` resolves within local scope when possible;
- nested `::` references have valid syntax and resolve when the local tree is available.

### Frames

The validator should check that:

- `<frame name="...">` has a non-empty unique name in its scope;
- `attached_to`, when present, resolves locally when possible;
- frame attachment chains do not cycle;
- unresolved nested or external frame references are reported as warnings when local validation cannot prove them invalid.

### Joints

Known SDF 1.12 joint types:

```text
continuous, revolute, gearbox, revolute2, prismatic, ball, screw, universal, fixed
```

The validator should check that:

- joint type is non-empty and known;
- `<parent>` and `<child>` text exists;
- `world` is allowed as parent but not child;
- unscoped parent/child references exist in the same model;
- `axis` and `axis2` vectors are finite, nonzero, and normalized;
- `axis2` is used only where the joint type supports a second axis;
- `expressed_in` resolves when local resolution is possible;
- limit and dynamics values are finite or documented infinities where SDFormat permits them;
- effort/velocity/stiffness/dissipation must be non-negative (`-1` is accepted as the unlimited sentinel for effort/velocity); axis `<dynamics>` damping/friction must be non-negative;
- finite lower limits do not exceed finite upper limits;
- continuous joints with fake finite position limits produce a warning.

### Geometry and mesh URIs

The validator should check that:

- each visual/collision owner has one geometry element;
- each geometry has exactly one known primitive or mesh child when possible;
- box size has 3 positive finite values;
- cylinder radius and length are positive and finite;
- sphere radius is positive and finite;
- plane size has 2 positive finite values;
- mesh URI values are non-empty;
- mesh scale has 3 nonzero finite values when present (negative scale mirrors the mesh and warns — consumer support varies);
- local mesh references resolve relative to the `.sdf` file's location;
- known external URI schemes such as `model://`, `package://`, `fuel://`, `http://`, and `https://` are accepted without local filesystem resolution.

### Inertials

The validator should check that:

- mass is positive and finite;
- inertial pose is valid when present;
- inertia tensor components are finite;
- inertia matrix is positive semidefinite within tolerance; principal moments violating the triangle inequality warn;
- missing inertial data on dynamic physical links is at least a warning;
- frame-like or static links can omit inertials when documented.

### Sensors and plugins

The validator should check that:

- sensor names are non-empty and unique within owner scope;
- sensor `type` is non-empty and from the known SDFormat sensor-type list (unknown types warn);
- sensor `update_rate`, when present, is finite and non-negative;
- sensor pose is valid;
- plugin filename is non-empty;
- plugin name, when present, is non-empty;
- arbitrary simulator-specific plugin schemas are not invented by the validator.

Plugin filenames and parameters can pass bundled validation and still fail in the target simulator. Use smoke tests.

### CAD Viewer review

CAD Viewer treats SDF plugins, sensors, lights, includes, and nested models as static metadata. The bundled validator checks generic structure only; it does not validate Explorer-only motion contracts or execute simulator plugins.

After `.sdf` files are created or modified, hand explicit paths to `$cad-viewer` for live viewer links when available.

This plugin is for CAD Viewer visualization and review. It is not a Gazebo physics/controller plugin and should not be represented as simulator runtime behavior.

## External checks

When Gazebo tooling is available, run:

```bash
gz sdf --check path/to/file.sdf
```

The CLI option should be:

```bash
python scripts/validate path/to/file.sdf --gz-check auto
```

External checks should be recorded in the diagnostics report. A skipped optional check is not a bundled-validation failure unless the user requested `--gz-check required`.

## SDF validity vs project policy

Separate these categories:

| Category | Examples |
|---|---|
| SDF structural validity | root `<sdf>`, version, legal element shape, non-empty names, references |
| Numeric plausibility | finite poses, positive dimensions, positive mass, normalized axes, PSD inertia |
| Simulator compatibility | libsdformat version, supported joint types, plugin availability, sensor support |
| Project policy | mesh location, preferred URI style, STL/DAE preference, collision simplification, no unresolved external URIs |

Do not reject valid SDF merely because it violates a project policy unless the task or repository requires that policy. Prefer warnings and strict-mode controls.
