# SDF smoke tests

Use smoke tests after the SDF passes bundled validation. The goal is to catch simulator and spatial failures that dependency-light XML checks cannot detect.

## Recommended checks

### Bundled validation

```bash
python scripts/validate path/to/model.sdf
python scripts/validate path/to/model.sdf --strict
```

Bundled validation runs during explicit target generation. Use `--strict` when warnings should block handoff.

### SDFormat parser check

When Gazebo tooling is installed:

```bash
gz sdf --check path/to/model.sdf
```

or through the skill CLI:

```bash
python scripts/validate path/to/model.sdf --gz-check auto
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

After generating or modifying an `.sdf`, hand the explicit path to `$cad-viewer` for a live viewer link when available.

- confirm direct model links, joints, frames, visuals, and collisions are placed correctly;
- confirm includes, plugins, sensors, lights, nested models, and unsupported geometry are listed as static metadata;
- record any simulator-only behavior that CAD Viewer cannot execute.

### Sensor and plugin check

For each sensor or plugin:

- confirm plugin library loads;
- confirm expected topics/services appear;
- confirm frame names match the design ledger;
- confirm update rate and namespace behavior;
- capture one sample output if practical.

### Visual review

When CAD Viewer or an equivalent viewer is available through `$cad-viewer`, return the viewer link. Visual review is useful but insufficient: it can catch gross placement and mesh problems, but it cannot prove axis frames, inertials, dynamics, or plugin behavior.

## Report format

Use a compact report:

```text
Checks run:
- bundled SDF validation: passed
- gz sdf --check: skipped, gz not installed
- simulator load: passed in Gazebo Harmonic
- joint motion: shoulder_pan positive motion verified; gripper joints skipped
- plugin startup: camera plugin unresolved, requires target simulator package

Assumptions:
- Assumed mesh units are meters.
- Assumed lidar frame is coincident with lidar_link.
```

## When to stop

Stop and fix the SDF (or its upstream assets) when:

- bundled validation has errors;
- `gz sdf --check` fails under a required external-check policy;
- the simulator reports invalid inertias or unresolved required assets;
- a joint moves opposite from the documented positive direction;
- plugin startup fails for a plugin required by the task.
