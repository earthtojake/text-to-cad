# MJCF checks

Every created or modified MJCF is checked with `cad mujoco check <file.xml>` before the task is reported complete. Check the file a consumer loads -- `scene.xml`, which includes or attaches the robot's -- and the robot's own file when it is used alone. A generated MJCF (`cad model export`) and a file a MuJoCo function or a scene script saved are checked the same way. The check compiles the model with MuJoCo's own compiler, the one reader that knows every rule of the format, and collects all findings in one pass (severity, code, the file); `--strict` fails on warnings and `--json` emits a machine-readable document.

An MJCF is MuJoCo's own file: `cad` writes one and asks MuJoCo about one, and never draws or opens one. A person looks at it in MuJoCo Studio (`cad run mujoco-studio --model path/to/scene.xml`).

```bash
cad mujoco check path/to/scene.xml
cad mujoco check path/to/scene.xml --strict --json
```

## Check model

The check writes nothing; it prints structured diagnostics and sets the exit status. Severities:

- `error`: MuJoCo refused the model; always blocking, so the run exits 1;
- `warning`: a warning of MuJoCo's own, or a modelling error the health checks found; non-blocking unless `--strict`;
- `info`: context and facts; never blocking.

A clean run exits 0 and its last line is `OK <file>: MuJoCo model '<model>', N bodies, N joints, N actuators, N collision geoms, N meshes, N keys` (the joints as MuJoCo counts them, the actuators those `<actuator>` declares). Read the counts: a robot of seven joints that says 0 joints has its joints in the wrong place, one that says 0 actuators has nothing to drive them yet, and 0 collision geoms means nothing collides. A failed run exits 1 and ends `FAILED <file>: ...`. A command line's own mistake (a file that is not there, one that is no `.xml` or `.mjcf`) exits 2.

It always compiles: there is no mode without MuJoCo. `cad[mujoco]` is MuJoCo's headless core and Studio's web viewer (`mujoco-core` and `mujoco-studio`, about 20 MB, no window system); the `cad` command makes its environment once, the first time the check needs it, and reuses it after. In Python it is `cad.mujoco.check(path, strict=False)`, which answers the same result.

`cad urdf validate` (or `sdf`, `srdf`) given an `.xml` says so: `robot.xml is not a urdf file: cad urdf takes .urdf (cad mujoco check takes .xml and .mjcf)`.

## MuJoCo's compile

MuJoCo's compiler loads the file as MuJoCo's own tools do (`MjModel.from_xml_path`): includes, defaults and assets resolved by the compiler, mesh files read, inertias computed. Each finding has a code; the codes are stable.

| Code | Severity | What it means |
|---|---|---|
| `compile_failed` | error | MuJoCo refused the model, in its words, naming the element and the line: XML that is not well formed, an attribute it does not know, a mesh file that is not there, a mesh too small to hull, a body with no mass to move, a name used twice across an include, a default class that does not exist, an actuator naming a missing joint, a key of the wrong length |
| `compile_warning` | warning | a warning MuJoCo issued while compiling, in its words |
| `compiled` | info | MuJoCo compiled the model: its version and counts |

Nothing else is said of a model that did not compile: fix the error and run the check again.

## Model health

After a compile passes, the check reads the compiled model for what MuJoCo's modelling guide ("Model tuning") says to rule out before tuning anything, at `qpos0` and at the key named `home` where there is one (the message says which). The thresholds are heuristics, chosen to be sure rather than complete. A warning here is a modelling error: fix it before changing any solver setting ([mujoco-environment.md](mujoco-environment.md#tuning)).

| Code | Severity | What it means | What to do |
|---|---|---|---|
| `contacts_at_rest` | warning | geoms of two bodies intersect at rest, deeper than 0.1 mm (1 mm for a free-floating object resting on a static geom); each pair of bodies once, deepest first, by its deepest geom pair's names and depth in mm and how many contacts the two make | Move the parts apart where they stand (a generated model: in the CAD, its collision shapes in its MuJoCo function, or where the scene attaches it); for a pair that touches by design (a joint's two sides), exclude it, `<contact><exclude body1 body2>` (`add_exclude`; a generated model excludes a joint's touching sides itself, and its MuJoCo function excludes any other pair with `s.add_exclude`); a visual geom in the pair is the next row's error |
| `visual_geoms_collide` | warning | a geom in groups 0-2 collides on a body that has group-3 collision geoms | Give visuals `contype="0" conaffinity="0"`, through the `visual` default class |
| `inertia_from_visuals` | warning | a body with no `<inertial>` takes mass from visual and collision geoms both, so its mass counts twice | A generated model: give the link's parts materials, so the kernel writes its inertial. By hand: an explicit `<inertial>` ([inertials.md](inertials.md)), or `density="0"` on the visual class |
| `scale_suspect` | warning | the moving geometry spans over 50 m or under 5 mm, or a mesh over 100 units after its `scale` | Millimetres read as metres: `scale="0.001 0.001 0.001"` on a millimetre mesh ([meshes.md](meshes.md)); a generated file is metres already, so look at what the scene added |
| `joint_limits_at_rest` | warning | a limited hinge or slide sits outside its range at `qpos0` or at `home` | At `home`: fix the key. At `qpos0` only: start the simulation from `home` (some published arms are made this way), or, where the model is yours, build it within its limits. Check `<compiler angle>` when a range looks like radians read as degrees |
| `defaults_not_recommended` | info | Euler, a pyramidal cone, the default `solref 0.02 1`, `solref[0]` under 2 x timestep, or a timestep over 5 ms with contacts | Set them once in the scene: `implicitfast`; `elliptic` with `impratio` 10 for manipulation; a timestep of 0.5-2 ms; `solref[0]` 0.004-0.01 and at least twice the timestep. Expected on a robot file alone, whose scene sets them |
| `defaults_after_include` | warning | a top-level `<default>` after an `<include>` sets defaults the included model's classes do not take (they keep what stood at the include) | Move the `<default>` above the `<include>` |
| `home_key` | info | no key named `home`, the convention for a robot's ready pose | Add one of the model's length: a `mechanism_state(..., "home", ...)` in the CAD, or `add_key(name="home", ...)` in the MuJoCo function or the scene |
| `mass_summary` | info | moving mass, moving bodies, `nv`, `nu` and the extents, one line | Read it against the robot: a mass off by a power of ten is a unit or a density; a count off by one is a missing joint or actuator |
| `check_unavailable` | info | a check failed inside and was skipped; it names the check | Report that check as skipped |

The warnings block under `--strict`.

## What collides, and the excludes

Two more infos say the facts a MuJoCo function's choices change. They judge nothing: read them against what the function meant.

- **`collisions`**: how many geoms collide, by kind; each body's count by kind (`base_link 6 (mesh 3, box 3)`); and the moving bodies that collide as nothing. A geom collides when its `contype` or `conaffinity` is not 0. Check each part against the choice made for it: a servo case fitted as a box is a `box`, a decomposed part is several `mesh` geoms, a part whose collisions were deleted adds none, and a body listed as colliding as nothing was meant to.
- **`excludes`**: each `<contact><exclude>` pair with how its two bodies' collision geoms stand at `qpos0`: `touching at rest`, `N mm apart at rest`, `over 1 m apart at rest`, or `where one has no collision geom`. An exclude is between two bodies whole: it stops every geom of one from colliding with every geom of the other. A pair that is apart at rest is either meant (two hulls that meet in some pose) or left over from a collision since removed, where it now also stops another part of those bodies from colliding. Remove a leftover one (`s.delete(exclude)` in the MuJoCo function).

`--json` has every row, under `measurements`:

- `collisions`: `geoms` (the count), `by_kind` (kind to count), `bodies` (each `{body, geoms: [{name, kind, size}]}`, the size as MuJoCo holds it, a mesh's the half extents of its box) and `silent` (the moving bodies with no collision geom);
- `excludes`: each `{bodies: [a, b], distance_mm, state}`, the state one of `touching`, `apart`, `far`, `no_collision` and `unmeasured` (too many geom pairs to measure).

Read the rows where a function chose by a rule over many parts: a table says exactly which geoms a rule left, which a picture does not.

`cad.mujoco.save` prints the same two lines (`collisions: ...`, `excludes: ...`) after the check's warnings, so a MuJoCo function's run already says them.

## Looking at the model

No `cad` command draws an MJCF. For a picture of the robot's kinematics, snapshot what it was generated from or beside: the CAD model (`cad model snapshot "$ID" out.png --pose home`) or the exported URDF (`cad urdf snapshot robot.urdf out.png --pose '{"elbow": 45}'`), which hold the same links and joints ([snapshots.md](snapshots.md)). For the model as MuJoCo compiles and simulates it -- contacts, dynamics, actuators -- the person opens it in MuJoCo Studio: `cad run mujoco-studio --model path/to/scene.xml`.

## When to stop

Stop and fix the model when:

- the compile fails (`compile_failed`) or warns (`compile_warning`);
- a model-health warning stands (tune nothing until it is cleared or explained);
- the `collisions` line does not match the collision chosen for each part;
- an exclude stands between two bodies that are apart at rest and nobody meant it;
- a joint moves opposite from the documented positive direction (in the CAD model's or the URDF's snapshot).

Report each check as run, passed, failed or skipped ([guardrails.md](guardrails.md#the-report)).
