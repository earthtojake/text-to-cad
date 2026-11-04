# SDF validation and smoke tests

Every created or modified `.sdf` is validated with `cad sdf validate <file.sdf>` before the task is reported complete. The validator collects all findings in one pass (severity, code, XML path); `--strict` fails on warnings and `--json` emits a machine-readable document. The bundled validation is dependency-light and intended to catch common structural errors. It is not a replacement for libsdformat, Gazebo, or target-simulator validation.

## Validation model

The validator writes nothing; it prints structured diagnostics and sets the exit status. Severities:

- `error`: invalid or unsafe; always blocking, so the run exits nonzero;
- `warning`: likely problem or unverified simulator behavior; non-blocking unless `--strict`;
- `info`: assumption, skipped check, or useful context; never blocking.

`--strict` treats warnings as failures. A clean run exits 0 and prints one `OK <file>: ...` summary line.

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
- root-, world-, and link-level lights need a valid type (`point`/`directional`/`spot`) and validated poses;
- duplicate names are reported with a path and scope.

### Poses

The validator should check all `<pose>` elements:

- default `rotation_format="euler_rpy"` has exactly six finite values;
- `rotation_format="quat_xyzw"` has exactly seven finite values;
- unsupported `rotation_format` is an error;
- quaternion values are approximately normalized;
- `degrees="true"` always warns (`pose_uses_degrees`), and `--strict` promotes that warning to a blocking finding;
- nontrivial omitted `relative_to` is a warning;
- `relative_to` resolves within local scope when possible;
- nested `::` references have valid syntax and resolve when the local tree is available.

### Frames

The validator should check that:

- `<frame name="...">` has a non-empty unique name in its scope;
- `attached_to`, when present, resolves locally when possible;
- world frames, lights, and model poses resolve against world frames, inline models, and explicitly named includes; names in this world scope do not become unqualified targets inside a model;
- frame attachment chains do not cycle, including world model pose references back to a frame attached to that model;
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

CAD Viewer lists SDF plugins, sensors, lights, physics settings and includes as static metadata, with their counts (an included model is not drawn). A model nested in the model is drawn with it. No plugin runs and none moves the model, whatever its name: SDF rendering is static unless joints are posed manually. The bundled validator checks generic structure only and never executes a plugin of any kind.

What the viewer and `cad sdf snapshot` draw, and what they refuse by name, is narrower than what the validator accepts: see [snapshots.md](snapshots.md#sdf). Static rendering does not execute SDF plugins or read file-authored motion metadata; review placement, resources and joints, and keep simulator checks separate.

After `.sdf` files are created or modified, show them ([Show the model](../SKILL.md#show-the-model)). Report any failure explicitly.

## External checks

`gz sdf --check` runs as part of every validation: `--gz-check auto` is the default and invokes the tool when it is on PATH. The three modes are:

| Mode | `gz` present | `gz` absent |
|---|---|---|
| `auto` (default) | `gz_check_passed` info, or `gz_check_failed` **error** with the tool's output | `gz_check_unavailable` info |
| `required` | same as `auto` | `gz_check_unavailable` **error** |
| `never` | not run | `gz_check_skipped` info |

A `gz` on PATH that cannot start (a broken launcher, a missing interpreter) is a `gz_check_failed` **error** under `auto` and `required` alike, naming why it could not start.

`gz sdf --check` resolves the document's own `<include>`/`<uri>` references, and the document chooses them. So gz does not run on a document that names a remote reference (`http://`, `https://`, `fuel://`), or that does not parse as XML: that is a `gz_check_remote` info under `auto` and an **error** under `required`, naming the references. `--gz-remote` lets gz fetch them; without it, validating a file never waits on a host the file names. Local references (relative paths, `file://`, `model://`, `package://`) are not refused, and a local model the document includes is not read for remote references of its own.

A tool that is not installed says nothing about the document, so under `auto` its absence is a note and never blocks — including under `--strict`, which promotes warnings about the FILE. Use `required` to demand the external check. Record which mode ran in the diagnostics report.

## SDF validity vs project policy

Separate these categories:

| Category | Examples |
|---|---|
| SDF structural validity | root `<sdf>`, version, legal element shape, non-empty names, references |
| Numeric plausibility | finite poses, positive dimensions, positive mass, normalized axes, PSD inertia |
| Simulator compatibility | libsdformat version, supported joint types, plugin availability, sensor support |
| Project policy | mesh location, preferred URI style, STL/DAE preference, collision simplification, no unresolved external URIs |

Do not reject valid SDF merely because it violates a project policy unless the task or repository requires that policy. Prefer warnings and strict-mode controls.

## Smoke tests

Use smoke tests after the SDF passes bundled validation. The goal is to catch simulator and spatial failures that dependency-light XML checks cannot detect.

### Bundled validation

```bash
cad sdf validate path/to/model.sdf
cad sdf validate path/to/model.sdf --strict
```

Use `--strict` when warnings should block handoff. It is safe on any machine: the default `--gz-check auto` notes a missing `gz` as `info` rather than a finding against the file, so `--strict` fails only on the document's own warnings.

### SDFormat parser check

`cad sdf validate` already runs `gz sdf --check` whenever `gz` is on PATH. Run it directly to read the parser's own output:

```bash
gz sdf --check path/to/model.sdf
```

or make it mandatory, so a missing `gz` is an error instead of a note:

```bash
cad sdf validate path/to/model.sdf --gz-check required
```

Use the exact simulator environment that will consume the file when possible.

### Simulator load check

Load the model or world in the target simulator and check:

- no parser warnings or plugin load errors;
- model appears at the intended pose;
- visual and collision assets resolve;
- collision geometry is not visibly offset from visuals;
- dynamic model does not explode, fall through the floor, or produce invalid inertia warnings.

### Joint motion check

For each non-fixed joint:

- command a small positive motion;
- confirm the moving child moves in the expected direction;
- confirm limits stop motion where expected;
- confirm continuous joints can rotate continuously if intended.

### CAD Viewer static review

After generating or modifying an `.sdf`, show it ([Show the model](../SKILL.md#show-the-model)). Report any failure explicitly.

- confirm direct model links, joints, frames, visuals, and collisions are placed correctly;
- confirm includes, plugins, sensors and lights are listed as static metadata, and nested models are drawn with the model;
- confirm the Viewer refuses by name any geometry or mesh it cannot draw, rather than leaving it out;
- record any simulator-only behavior that CAD Viewer cannot execute.

### Sensor and plugin check

For each sensor or plugin:

- confirm plugin library loads;
- confirm expected topics/services appear;
- confirm frame names match the design ledger;
- confirm update rate and namespace behavior;
- capture one sample output if practical.

### Visual review

Return the live CAD Viewer link, or explicitly report why launching failed. Visual review is useful but insufficient: it can catch gross placement and mesh problems, but it cannot prove axis frames, inertials, dynamics, or plugin behavior.

## When to stop

Stop and fix the SDF (or its upstream assets) when:

- bundled validation has errors;
- `gz sdf --check` fails under a required external-check policy;
- the simulator reports invalid inertias or unresolved required assets;
- a joint moves opposite from the documented positive direction;
- plugin startup fails for a plugin required by the task.

Report each check as run, passed, failed or skipped in the compact report ([guardrails.md](guardrails.md#the-report)).
