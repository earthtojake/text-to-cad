# MJCF validation

Every created or modified MJCF is validated with `cad mjcf validate <file.xml>` before the task is reported complete. Validate the file a consumer loads -- `scene.xml`, which includes or attaches the robot's -- and the robot's own file when it is used alone. A generated MJCF (`cad model export`) and a scene a script saved are validated the same way. The validator collects all findings in one pass (severity, code, XML path); `--strict` fails on warnings and `--json` emits a machine-readable document. It reads the model with the viewer's own reader, the Python standard library alone, and then compiles it with MuJoCo where MuJoCo is there: the compile is the one check that knows every rule of the format.

## Validation model

The validator writes nothing; it prints structured diagnostics and sets the exit status. Severities:

- `error`: invalid, or not what MuJoCo would load; always blocking, so the run exits nonzero;
- `warning`: likely problem, or a part of the model the viewer draws as less than MuJoCo makes of it; non-blocking unless `--strict`;
- `info`: context, a skipped check, or a passed compile; never blocking.

A clean run exits 0 and prints one `OK <file>: MJCF '<model>', N bodies, N controls, N visuals, N mesh files, N keyframes` line. Read the counts: a robot of seven joints that says 0 controls has its joints in the wrong place, and 0 visuals means every geom sits in a collision group.

## Bundled checks

Each finding has a code; the codes are stable.

### Document and includes

- the file is well-formed XML (`invalid_xml`, `unreadable_file`) with `<mujoco>` at its root (`not_mjcf`) and exactly one `<worldbody>` (`missing_worldbody`, `several_worldbodies`);
- every `<include>` names a file (`include_without_file`) that is there, relative to the main file's folder (`include_not_found`), readable (`include_invalid`), and included once (`include_repeated`);
- `<compiler angle>` is `degree` or `radian` (`bad_compiler_angle`) and `eulerseq` is three of `xyzXYZ` (`bad_compiler_eulerseq`);
- every number list parses (`bad_number`) and has the count its attribute takes (`bad_number_count`).

### Defaults and assets

- a nested `<default>` has a class name (`default_without_class`), declared once (`duplicate_default_class`), and every `class` or `childclass` an element names is declared (`unknown_default_class`);
- a `<mesh>` has a name or a file to take it from (`mesh_without_name`), declared once (`duplicate_mesh_name`), its file there under `meshdir` (`mesh_file_not_found`) and an STL, OBJ or MSH (`mesh_format_unknown`); an MSH or an inline mesh warns `mesh_not_drawn`;
- a `<material>` has a name (`material_without_name`), and every material a geom names is declared (`material_unknown`).

### Bodies and geoms

- body, joint and geom names are unique (`duplicate_body_name`, `duplicate_joint_name`, `duplicate_geom_name`);
- an element takes one orientation (`several_orientations`), and that one is well formed (`bad_orientation`: a zero quaternion, a zero `zaxis`, parallel `xyaxes`);
- an `<inertial>` has a mass (`inertial_without_mass`);
- a geom's type is MuJoCo's (`unknown_geom_type`), its `size` has the values its type needs and they are positive (`geom_size`), `fromto` is on a capsule, cylinder, box or ellipsoid (`fromto_on_shape`) and its points differ (`fromto_degenerate`);
- a mesh geom names a mesh (`mesh_geom_without_mesh`) the assets declare (`mesh_asset_unknown`);
- a geom the viewer draws in groups 0 to 2 that it cannot draw -- `hfield`, `sdf`, `ellipsoid` -- warns `geom_not_drawn`; an unbounded plane (size 0) is an info of the same code, the viewer's grid standing in for the floor;
- `<replicate>`, `<attach>`, `<flexcomp>`, `<flex>` and `<composite>` warn `compile_only_element`: MuJoCo's compiler expands them, and the reader sees nothing of what they make.

### Joints, equalities and keyframes

- a joint belongs to a body, not `<worldbody>` (`joint_in_worldbody`); its type is `hinge`, `slide`, `ball` or `free` (`unknown_joint_type`); its axis has length (`axis_zero`);
- a range runs low to high (`range_inverted`); `limited="true"` has a range (`limited_without_range`); a range that `autolimits="false"` leaves unlimited warns `range_unlimited`;
- a `ball` joint warns, and a `free` joint is an info, `joint_not_posable`: the body is drawn where it is authored;
- `<equality><joint>` names joints the model has (`equality_unknown_joint`); a polynomial coupling (`polycoef` past its linear term) is an info, `equality_not_linear`, and the follower becomes a control of its own;
- a key's `qpos` has the model's length -- 1 per hinge or slide, 4 per ball, 7 per free joint -- or warns `keyframe_length` and is no pose.

## MuJoCo's compile

`--compile` asks MuJoCo's compiler to load the file as MuJoCo's own tools do (`MjModel.from_xml_path`): includes, defaults and assets resolved by the compiler, mesh files read, inertias computed. It catches what the reader cannot: a mesh too small to hull, a body with no mass to move, a name clash across an include, an actuator naming a missing joint, every attribute MuJoCo does not know.

| Mode | MuJoCo installed | MuJoCo absent |
|---|---|---|
| `auto` (default) | `compiled` info (its version and counts), or `compile_failed` **error** with MuJoCo's message | `compile_skipped` info |
| `required` | same as `auto` | the `cad` command makes the environment of `cad[mujoco]` and compiles there; `compile_unavailable` **error** only where it cannot |
| `never` | not run | not run |

Each warning MuJoCo issues while compiling is a `compile_warning` warning, in MuJoCo's words. `cad[mujoco]` is MuJoCo's headless core and Studio's web viewer (`mujoco-core` and `mujoco-studio`, about 20 MB, no window system), fetched once the first time `required` needs it and reused after.

Once compiled, the model is checked for what MuJoCo's modelling guide says to rule out before tuning anything ([Model health](#model-health), below).

Under `auto` a missing MuJoCo is a note and never blocks, even under `--strict`. Use `required` for handoff:

```bash
cad mjcf validate path/to/scene.xml --compile required
cad mjcf validate path/to/scene.xml --compile required --strict --json
```

When the reader and the compiler disagree, the compiler is right about the model; the reader's findings say what the viewer will draw.

## Model health

After a compile passes, the validator checks the compiled model for what MuJoCo's modelling guide ("Model tuning") says to rule out before tuning anything, at `qpos0` and at the key named `home` where there is one (the message says which). The thresholds are heuristics, chosen to be sure rather than complete. A warning here is a modelling error: fix it before changing any solver setting ([mujoco-environment.md](mujoco-environment.md#tuning)).

| Code | Severity | What it means | What to do |
|---|---|---|---|
| `contacts_at_rest` | warning | geoms of two bodies intersect at rest, deeper than 0.1 mm (1 mm for a free-floating object resting on a static geom); the deepest pairs by name and depth in mm | Move the parts apart where they stand (a generated model: in the CAD, or where the scene attaches it); for a pair that touches by design (a joint's two sides), exclude it, `<contact><exclude body1 body2>` (`scene.add_exclude`); a visual geom in the pair is the next row's error |
| `visual_geoms_collide` | warning | a geom in groups 0-2 collides on a body that has group-3 collision geoms | Give visuals `contype="0" conaffinity="0"`, through the `visual` default class |
| `inertia_from_visuals` | warning | a body with no `<inertial>` takes mass from visual and collision geoms both, so its mass counts twice | A generated model: give the link's parts materials, so the kernel writes its inertial. By hand: an explicit `<inertial>` ([inertials.md](inertials.md)), or `density="0"` on the visual class |
| `scale_suspect` | warning | the moving geometry spans over 50 m or under 5 mm, or a mesh over 100 units after its `scale` | Millimetres read as metres: `scale="0.001 0.001 0.001"` on a millimetre mesh ([meshes.md](meshes.md)); a generated file is metres already, so look at what the scene added |
| `joint_limits_at_rest` | warning | a limited hinge or slide sits outside its range at `qpos0` or at `home` | At `home`: fix the key. At `qpos0` only: start the simulation from `home` (Menagerie's Panda does this), or, where the model is yours, build it within its limits. Check `<compiler angle>` when a range looks like radians read as degrees |
| `defaults_not_recommended` | info | Euler, a pyramidal cone, the default `solref 0.02 1`, `solref[0]` under 2 x timestep, or a timestep over 5 ms with contacts | Set them once in the scene: `implicitfast`; `elliptic` with `impratio` 10 for manipulation; a timestep of 0.5-2 ms; `solref[0]` 0.004-0.01 and at least twice the timestep. Expected on a robot file alone, whose scene sets them |
| `home_key` | info | no key named `home`, the Menagerie convention | Add one of the model's length: a `mechanism_state(..., "home", ...)` in the CAD, or `add_key(name="home", ...)` in the scene |
| `mass_summary` | info | moving mass, moving bodies, `nv`, `nu` and the extents, one line | Read it against the robot: a mass off by a power of ten is a unit or a density; a count off by one is a missing joint or actuator |
| `check_unavailable` | info | a check failed inside and was skipped; it names the check | Report that check as skipped |

The warnings block under `--strict`.

## Reading a snapshot

```bash
cad mjcf snapshot path/to/scene.xml home.png --pose home
cad mjcf snapshot path/to/scene.xml elbow.png --pose '{"joint4": -90}'
```

`--pose` names a keyframe (`home`), or gives joint values over the opening pose in degrees for a hinge and metres for a slide, as the other formats' snapshots do (a keyframe's own numbers are radians). The model opens at `qpos0`, every joint at its `ref`, as MuJoCo opens it; a key is a pose to ask for, `home` included. A joint that is no control -- a `ball` or `free` joint, or the follower of an `<equality>` coupling -- is refused by name.

Check in the still:

- the robot stands on the floor at `home`, not through it or above it: the root body's `pos` and the floor's height agree;
- each link sits where the ledger puts it: a link at the origin, or a limb at right angles, is an orientation or `angle` units error;
- meshes are at sane scale: ~1000x too large or small is a mesh `scale` bug ([meshes.md](meshes.md));
- no collision geom is drawn: one that is sits in groups 0 to 2;
- each joint, moved by `--pose`, moves its link the way the ledger's positive motion says.

The still draws what [mjcf-authoring.md](mjcf-authoring.md#what-the-viewer-draws) lists, not the compiled model; it cannot show contacts, dynamics, actuators or a simulation.

## When to stop

Stop and fix the model when:

- bundled validation has errors;
- the compile fails or warns under `--compile required`;
- a model-health warning stands (tune nothing until it is cleared or explained);
- a keyframe is the wrong length;
- a joint moves opposite from the documented positive direction;
- collision geoms are drawn, or visuals are missing, in the snapshot.

Report each check as run, passed, failed or skipped, and which compile mode ran ([guardrails.md](guardrails.md#the-report)).
