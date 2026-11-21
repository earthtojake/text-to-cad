# MJCF checks

Read this for what `cad mujoco check` prints and what to do about each finding. Check the file a consumer loads, `scene.xml`, which includes or attaches the robot's, and the robot's own file when it is used alone. A generated MJCF and one a MuJoCo function or a scene script saved are checked the same way.

```bash
cad mujoco check sim/scene.xml
```

```text
warning: defaults_after_include at sim/scene.xml: the top-level <default> after <include file="gripper.xml"> sets geom defaults, which miss the geom elements in its classes (collision, gripper, visual): a class takes its parent's defaults where it is defined, so they keep what stood at the include Hint: move the <default> above the <include>
info: compiled at sim/scene.xml: compiled by MuJoCo 4.0.1: 3 bodies, 2 joints, 7 geoms, 2 meshes, 2 keyframes
...
OK sim/scene.xml: MuJoCo model 'gripper scene', 3 bodies, 2 joints, 1 actuator, 4 collision geoms, 2 meshes, 2 keys
```

Each line is one finding: its severity, its code (the codes are stable), the file, the message and a hint. An `error` is MuJoCo refusing the model, and the last line is then `FAILED <file>: ...`. A `warning` is one of MuJoCo's own or a modelling error the health checks found. An `info` is a fact. Read the counts on the `OK` line (the joints as MuJoCo counts them, the actuators those `<actuator>` declares): a robot of seven joints that says 0 joints has its joints in the wrong place, one that says 0 actuators has nothing to drive them yet, and 0 collision geoms means nothing collides. In Python it is `cad.mujoco.check(path, strict=False)`, which answers the same result.

## MuJoCo's compile

The check loads the file as MuJoCo's own tools do: includes, defaults and assets resolved, mesh files read, inertias computed.

| Code | Severity | What it means |
|---|---|---|
| `compile_failed` | error | MuJoCo refused the model, in its words, naming the element and the line: an attribute it does not know, a mesh file that is not there, a moving body with no mass, a name used twice across an include, a default class that does not exist, a key longer than the model |
| `compile_warning` | warning | A warning MuJoCo issued while compiling, in its words |
| `compiled` | info | MuJoCo compiled the model: its version and counts |

Nothing else is said of a model that did not compile: fix the error and run the check again.

## Model health

After a compile passes, the check reads the model at `qpos0`, and at the key named `home` where there is one (the message says which), for what MuJoCo's modelling guide says to rule out before tuning. A warning here is a modelling error: fix it before changing any solver setting ([tuning](mujoco-environment.md#tuning)). The thresholds are heuristics, chosen to be sure rather than complete.

| Code | Severity | What it means | What to do |
|---|---|---|---|
| `contacts_at_rest` | warning | Geoms of two bodies intersect at rest, deeper than 0.1 mm (1 mm for a free-floating object resting on a static geom). Each pair of bodies once, deepest first, by its deepest geom pair's names and depth in mm and how many contacts the two make | Move the parts apart where they stand (a generated model: in the CAD, its collision shapes in its MuJoCo function, or where the scene attaches it). Exclude a pair that touches by design, a joint's two sides: `<contact><exclude body1 body2>`, `s.add_exclude` in a MuJoCo function (a generated model excludes a joint's touching sides itself). A visual geom in the pair is the next row's error |
| `visual_geoms_collide` | warning | A geom in groups 0-2 collides on a body that has group-3 collision geoms | Give visuals `contype="0" conaffinity="0"`, through the `visual` default class |
| `inertia_from_visuals` | warning | A body with no `<inertial>` takes mass from visual and collision geoms both, so its mass counts twice | A generated model: give the link's parts materials, so the kernel writes its inertial. By hand: an explicit `<inertial>` ([inertials.md](inertials.md)), or `density="0"` on the visual class |
| `scale_suspect` | warning | The moving geometry spans over 50 m or under 5 mm, or a mesh over 100 units after its `scale` | Millimetres read as metres: `scale="0.001 0.001 0.001"` on a millimetre mesh ([meshes.md](meshes.md)). A generated file is metres already, so look at what the scene added |
| `joint_limits_at_rest` | warning | A limited hinge or slide sits outside its range at `qpos0` or at `home` | At `home`: fix the key. At `qpos0` only: start the simulation from `home` (some published arms are made this way), or, where the model is yours, build it within its limits. Check `<compiler angle>` when a range looks like radians read as degrees |
| `defaults_not_recommended` | info | Euler, a pyramidal cone, the default `solref 0.02 1`, `solref[0]` under 2 x timestep, or a timestep over 5 ms with contacts | Set them once in the scene, above its `<include>` ([the scene file](mujoco-environment.md#the-scene-file)); the message names each value the guide recommends. Expected on a robot file alone, whose scene sets them |
| `defaults_after_include` | warning | A top-level `<default>` after an `<include>` sets defaults the included model's classes do not take (they keep what stood at the include) | Move the `<default>` above the `<include>` |
| `home_key` | info | No key named `home`, the convention for a robot's ready pose | Add one of the model's length: a `mechanism_state(..., "home", ...)` in the CAD, or `add_key(name="home", ...)` in the MuJoCo function or the scene |
| `mass_summary` | info | Moving mass, moving bodies, `nv`, `nu` and the extents, one line | Read it against the robot: a mass off by a power of ten is a unit or a density; a count off by one is a missing joint or actuator |
| `check_unavailable` | info | A check failed inside and was skipped; it names the check | Report that check as skipped |

## What collides, and the excludes

Two more infos state what a MuJoCo function's choices change. They judge nothing: read them against what the function meant.

- **`collisions`**: how many geoms collide (a `contype` or `conaffinity` not 0), by kind; each body's count by kind (`base_link 6 (mesh 3, box 3)`); and the moving bodies that collide as nothing. A part fitted as a box reads `box`, a decomposed part several `mesh` geoms, a part whose collisions were deleted adds none, and every body listed as colliding as nothing was meant to.
- **`excludes`**: each `<contact><exclude>` pair with how its two bodies' collision geoms stand at `qpos0`: `touching at rest`, `N mm apart at rest`, `over 1 m apart at rest`, or `where one has no collision geom`. An exclude is between two bodies whole: it stops every geom of one from colliding with every geom of the other. A pair that is apart at rest is either meant (two hulls that meet in some pose) or left over from a collision since removed, where it now also stops another part of those bodies from colliding. Remove a leftover one (`s.delete(exclude)` in the MuJoCo function).

A line names twelve bodies or pairs at most. `--json` has every row under `measurements`, the ones to read where a function chose by a rule over many parts:

- `collisions`: `geoms` (the count), `by_kind` (kind to count), `bodies` (each `{body, geoms: [{name, kind, size}]}`, the size as MuJoCo holds it, a mesh's the half extents of its box) and `silent` (the moving bodies with no collision geom);
- `excludes`: each `{bodies: [a, b], distance_mm, state}`, the state one of `touching`, `apart`, `far`, `no_collision` and `unmeasured` (too many geom pairs to measure).

`cad.mujoco.save` prints the same two lines (`collisions: ...`, `excludes: ...`) after the check's warnings.

## What a clean check does not show

That a joint turns the way meant: pose the CAD model or the exported URDF in a snapshot ([snapshots.md](snapshots.md#an-mjcf)). That a collision shape, a gain or a contact setting suits the hardware: the person watches the model in MuJoCo Studio, against a baseline ([tuning](mujoco-environment.md#tuning)). Report each check as run, passed, failed or skipped ([guardrails.md](guardrails.md#the-report)).
