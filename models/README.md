# Models

The corpus of models built with cadgen 0.8: plain files, one flat level of
self-contained projects, built by running their scripts; nothing installs it.
Automated tests never read, build or import anything here: they make their own
fixtures in fresh temporary directories. The manual-validation cases live in
[tests/](tests/README.md).

Each project has one layout, the cad skill's: its sources in `src/` (shared modules in
`src/lib/`), each model a `@model` function its script calls under `if __name__ ==
"__main__":`. A run writes nothing: it builds the model in the engine and prints its
document's `id:` and page (`view:`), which every later run updates. A file is written
on request, `cadgen export <id> STEP/<name>.step`, into the project's root-level
`STEP/`, `STL/`, `GLB/`, `3MF/` or `DXF/`, which each project's `.gitignore` keeps out
of Git. `tom` also reads vendor STEP from a local, gitignored `tom/STEP/imported/` (its
`src/README.md` says how to populate it); `examples/vendor/` holds the two STEP inputs
`electronics_enclosure_base_import.py` reads. `juno` and `lyra` carry an authored URDF
and SRDF beside `src/`; the link meshes they reference are written by each project's
`exports.py` (`3MF/<link>.3mf`), so run it before loading either URDF.

Every model of the old corpus is ported, but for tendon_hand's 56 review models (reviews
and clearance studies on frozen STEP snapshots, not the hand: dropped, in Git history).
One file is no model: `tests/unported/joint_playground.urdf`, named nowhere, kept with
its README.

**Where does a new model go?** A standalone part that is one script goes in
`examples/src/` (a `@model`), an assembly gets a group in `assemblies/`
(`src/<group>/`), and a 2D drawing a script in `drawings/src/`, its DXF added to
`drawings/src/exports.py`. A model that needs helper modules, several scripts or notes
of its own gets a project of its own here.

Commit sources (`*.py`, `*.urdf`, `*.srdf`, the JSON a body reads, docs) and the
inputs a model reads that nothing builds (`examples/vendor/`); never what a run or an
export writes, review media (`.gitignore` keeps images and video out of this tree) or
runtime debris.

## The files the corpus writes

Most models write nothing. A few keep files on purpose, as examples of each way a
project delivers them and because something outside the model reads them:

| Project | Files | How | Why |
| --- | --- | --- | --- |
| `assemblies` (`planetary_gear_assembly`) | `apps/docs/public/hero/planetary.glb` | `apps/docs/scripts/sync-hero-glb.mjs`, which calls `cadgen.export(model, path)` | the docs site's hero plays its `meshCycle` clip; `check-hero-glb.mjs` gates it in CI |
| `examples` (`mounting_plate`, `spur_gear_blank`) | `STL/`, `3MF/`, `GLB/<name>.*` | `@stl`, `@threemf`, `@glb` on the model | the example of declared files: a print part whose files every run writes |
| `branding` (the three logos) | `STEP/logo_*.step` | `src/exports.py` | the STEP deliverable, kept current by an `exports.py` |
| `drawings` (all eight) | `DXF/<name>.dxf` | `src/exports.py` | the DXF deliverables, flat patterns among them; a drawing exists for its DXF |
| `juno`, `lyra` (every link model) | `3MF/<link>.3mf` | `src/exports.py` | the URDFs reference them |
| `tom` (`rev3_parts.py`) | `STEP/imported/parts/<occurrence>.xbf` | `export(part, path)` in its `__main__` | the xbf handed to another model: Tom rev3's parts, converted once from the 354 MB vendor STEP and read by the `tom2` stage with `read_xbf` |
| `examples` (`electronics_enclosure_base_drawing`) | `PDF/electronics_enclosure_base_drawing.pdf` | `@eng_drawing` | an engineering drawing is its PDF |
| `radial` | `XBF/radial.xbf` | `@xbf` | the slow model's result kept across runs and engine restarts: a cold build takes most of an hour; every body replays, and a no-op takes the file (0.2 s) instead of sampling the running motion again (5.6 s without it) |

## Build and snapshot

From a model's `src/` folder, with the engine's environment (cadgen on the path):

```
python SCRIPT.py                         # the models its __main__ calls: each prints id: and view:
cadgen snapshot "$ID" OUT.png            # drawn by OCCT
cadgen export "$ID" GLB/NAME.glb         # a file of it, on request
```

A model script is Python and takes no options: running it asks the engine to build each
model its `__main__` calls, in the script's warm worker (the engine starts on demand;
`cadgen stop` stops it), so a second run of an unchanged model replays it from memory.
A script's models count as one run of the memo's last four, however many it builds, so a
robot and its links replay together. Nothing is written beside a model: no sidecar, no
cache.

## The port

The migration a user makes (`docs/migrations/migrating-0.7-to-0.8.md`), and nothing more:

- `from cadgen import step` -> `from cadgen import model` (and `memo`, `Material`,
  `materials`, `paint`, `read_step`, `read_xbf`, `read_mesh`, `export`); cadgen's
  build123d proxy -> `import build123d as bd`; `cadgen.ap242` for the mechanism and
  `cadgen.gltf` for a GLB's animations.
- `@step(out=...)` -> `@model`, and nothing else, but where the table above keeps a file.
  Every script calls its models under `__main__`; a module of `@memo` stages or plain
  helpers calls nothing there.
- `materials=` finishes -> `Material` values set on the parts (`part.material = ...`) and
  `paint(part, faces, material)` for a face finish; colours as sRGB hex.
- Mates (`AssemblyHelper` frames, `KINEMATICS` revolute/fastened) -> build123d joints
  (`RigidJoint`, `RevoluteJoint`, ...) placed with `connect_to`, or paired by label where
  `connect_to` cannot place a part in a nested assembly. The as-built pose is where the
  joints connect the parts. A coupling, named after the pair it is written as
  (`gear_pair`, `rack_and_pinion_pair`, `screw_pair`), is a real mechanical relation and a
  constraint: the gear trains (the moonwatch's `running` and `chrono`, the qdd, planetary
  and radial `drive`), the mars rover's differential (`rocker_split`) and the tendon
  hand's curls. Poses are `mechanism_state(...)`.
- Animation (`animation=` JavaScript, `cadgen.clip`) -> two layers. The mechanism's own
  motion (a gait, a door, an engine running) is a `configuration_sequence`, kept in the
  document. A showcase (an explode, a teardown, a reveal, a part hidden) is a
  `cadgen.gltf` `animation()`, baked into every GLB exported from the model: parts
  translated, turned or hidden after the mechanism's pose, and the mechanism posed at
  its keys where the old clip ran it. No joint exists only to slide a part apart. Every
  old clip keeps its name and duration in one or the other; what neither can say (an
  opacity fade, a tube deformation, a chain link riding its loop, a body that leaves the
  ground) is written in each project's README as a deliberate difference.
- `@dxf` -> `@model` returning the drawing's 2D geometry, a compound of labelled
  children a layer each; `drawings/src/exports.py` writes the DXFs.

### When to use `@memo`

Rarely. The engine already replays every kernel call of any model, so `@memo` only saves
the Python cost of the memo hits a replayed function avoids (0.1-0.4 ms per hit). It
pays only where a function holds seconds of kernel work that an edit elsewhere leaves
untouched: roughly a thousand kernel calls or more. Measured here: the movement's 3
layers halve an edit (a leaf edit runs in about 4.5 s), and tom's 6 stages save 1.3-3 s
per edit. It does not pay on small pieces: the motorbike's 21 part markers and qdd's 7
makers saved under 0.1 s, and the movement's 19 part groups added nothing beyond its 3
layers, so those models carry none of them. A `@memo` function must also return an
assigned result (it names what its `return` statement makes in itself, so one returning
`a - b` would rename those elements), and a marker costs a model body that is no longer
one piece.

## The models

| Model | Source | What it exercises |
| --- | --- | --- |
| `dfm-process-comparison` | 5 single-part trays | per-part catalogue materials (PLA, aluminium, ABS); lofts, fillets, drafted cones |
| `qdd_actuator` | one file, 153 occurrences | a 102-part assembly, modules as nested compounds; one body (no `@memo`: its makers save under 0.1 s); build123d joints (each module fastened, the drive train's revolutes); the drive train one coupling, `drive` (a constraint), two configurations, the old clip `drive` a motion and `inspect` and `teardown` GLB animations at the old stations, the planets' radial spread restored |
| `motorbike` | 21 part models + the assembly | each part a `@model` the assembly calls, a child of its run and a page of its own, a part placed twice; revolute and rigid joints across parts; the old poses as three configurations (`stand_down`, `turned_left`, `bump`) and one motion, `steer` (a GLB export carries it as a clip) |
| `moonwatch` | `case.py`, `dial.py`, `bracelet.py`, `finishing_sampler.py`, `movement.py` (3 `@memo` layers), and `moonwatch.py`, the full watch composing case, dial, movement and bracelet in one body | finishes as materials on every part: catalogue entries in each finish's look (coat, grain, transmission), own materials (sapphire, ruby, print ink, lacquer, lume), a painted face finish, transparent parts; the full watch (258 parts, 301 instances): its mates as 17 joints paired by label (the hands, going train, escapement, chronograph, crown and pushers) and rigid fastenings, its gear trains as two couplings (`running`, `chrono`: constraints its wheels and hands move only through), 7 configurations, the `running` motion and the `reveal`, `showcase` and `grand_tour` GLB animations (the escapement posed at every key, the parts translated, the movement turned about X with its tiers fanned inside it) |
| `tom` | tom-cad `main` (7f79c52): 119 files, one model, 6 `@memo` stages and parts (each earns it) | a 619-part arm built from stages, 8 occurrences of Tom rev3's arm extracted once to xbf by `rev3_parts.py`'s models (`read_xbf`, never the 354 MB STEP) and 11 `read_step` vendor files (139 MB of local, uncommitted inputs: see its `src/README.md`); mates kept as data and authored as build123d joints, their 4 old poses as configurations and the showcase's 3 clips (`showcase`, `wrist`, `approach`) as motions playing the old beat table; materials by finish; many-body retention |
| `examples` | all 29 scripts: 27 parts and assemblies, a `read_step` import and an `@eng_drawing` | fillets, chamfers, swept blades; assemblies placed by joints (the fixture's `connect_to` moving parts, the print-in-place hinges' pivots revolute joints paired by label); `read_step` of a part and of an assembly (imported naming), from STEP inputs committed in `examples/vendor/`; STL, 3MF and GLB declared on the model (`mounting_plate`, `spur_gear_blank`); an `@eng_drawing` PDF of the enclosure, calling its model; the hinged box's motion and its showcase `animation()` |
| `hypercar` | 13 system files (`@memo` stages, 1,250-24,000 kernel calls each) + one model | a 706-part car whose panels share one master surface; a placed wheel prototype per axle; doors as cylindrical joints on the chassis paired by label across systems' groups, riders fastened by rigid-joint pairs; a configuration (`open`), the motion `doors`, and the `showcase` tour and `explode` as GLB animations of the old groups, each door with its flank and each rider with its own group |
| `f1` | 32 part files, `stages.py` and one model; 12 `@memo` stages (990-11,400 kernel calls each) | an 833-part car of 28 children grouped in stages by the builders they share; two closed-loop mechanisms (the DRS four-bar, the steering) authored as their tree of joints -- revolute, prismatic and ball -- paired by label, every pose solved in Python: 3 configurations, the `drs` and `steering` motions, and the `showcase`, `teardown` and `engine` explodes as GLB animations |
| `drawings` | all eight scripts of the old `drawings`, and `exports.py` | drawings as models of planar documents, their DXFs written by `exports.py`: a layer per part (`CUT`, open `BEND` and `ENGRAVE` lines, a layer of several shapes one part of them all), bend fixtures in every orientation, `bd.Text` outlines engraved, a workshop drawing of three views and eleven dimensions, and a profile laid out from a solid's top face; byte-for-byte the old emitter's for the gasket |
| `juno` | one script: the robot and its 28 URDF links, 29 models | 27 revolute joints connected at the athletic stance (absolute angles, the URDF's travel as ranges) and the SRDF's five group states as configurations and the seven gait clips as motions of time (a root-held vertical slide, `pelvis_lift`, for the bounce); each link a model whose 3MF `juno.urdf` references `exports.py` writes; one `@memo` stage, `links()`, shared by all 29 (30.8 s cold against 56.2 s without it) |
| `assemblies` | 23 models in 21 groups | the demo assemblies: `AssemblyHelper` frames as build123d joints, the planetary gear's `drive` coupling, its `meshCycle` motion (its GLB, the docs hero) and `inspectExplode` animation, the mars rover's joints, its differential's coupling (`rocker_split`), 4 configurations, three motions and the `explodedAssembly` animation; no `@memo`, no model calling another |
| `tendon_hand` | 56 of the 112 one-model scripts, folded into 5 scripts by subsystem | the research hand's components, phalanges, routing, guide mounts and forearm, each model a `@model`; four shared `@memo` stages (each finger's guide combs, the forearm frame, its guide banks, the R5 supports) placed by several models; a STEP round trip made in memory, a `@memo` call that keys what OCCT's reader made; `anatomy_layout`'s finger joints with a curl coupling per finger and two configurations; the other 56, reviews on frozen STEP snapshots, dropped |
| `radial` | 19 scripts -> one model, 18 `@memo` system stages | a sectioned nine-cylinder radial, 473 parts in 2,400 placements: finishes as catalogue materials on every part; the old animation's label contract made its joints (revolute and prismatic, fastened links), the gear train one coupling (`drive`, a constraint), two configurations, the `running` motion, and `explode` and `exploded-running` as GLB animations of the old plan, `lib/explode_plan.json` (the teardown's 1,360 units, the running layout and its 466 hidden parts) |
| `lyra` | one script: the hand and its 17 URDF links, 18 models | 16 revolute joints connected at the relaxed pose (absolute angles, the URDF's travel as ranges), the SRDF's seven group states as configurations and the five clips as motions of time (joint-space already); each link a model whose 3MF `lyra.urdf` references `exports.py` writes; one `@memo` stage, `links()`, shared by all 18 (7.7 s cold against 11.1 s without it) |
| `falcon_heavy` | 3 scripts -> one script, 3 models | the full stack, a 270° cutaway and an exploded view of one vehicle library: 85 parts in 2,142 placements, 27 engines as `moved` placements of one Merlin; two `@memo` stages, `engine_prototype()` (one Merlin per build, not nine) and `build_vehicle(cutaway)` (the exploded view's vehicle a placement of the stack's): 7.1 s cold with none, 5.0 s with both |
| `branding` | `logo_c`, `logo_cad`, `logo_texttocad`, and `exports.py` | plain models with the STEP each delivers (`exports.py`), extruded from a JSON input the body reads (`profiles.json`, a change to which rebuilds them); colours as sRGB hex |
| `tests` | the three manual cases the old `tests/README.md` listed (`joint_playground.urdf`, no model and named nowhere, kept in `unported/`) | manual-validation fixtures, never CI input: the Render floor, a 32-part rebuild during a load, and materials (a catalogue steel with `color=None`, a paint with its colour), a revolute and a prismatic joint (the shaft's lift, which the fixture's motion drives), a configuration and a motion on 11 parts |
| `w16` | 13 system files (`@memo` stages, 10-281 s cold each) + one model | a 2,575-occurrence (794-part) quad-turbo W16 whose museum cutaway is its own geometry; finishes as catalogue materials by colour (`color=None`); OCCT's fuzzy booleans run through build123d's, so the memo keys them; the crank train as 180 joints paired by label (prismatic pistons and valves; revolute crank, rods, cams, sprockets, followers, pump, pulleys, rotors) and rigid fastenings, the slider-crank and valve loops solved in Python: the `crank` motion, one 720-degree cycle, and the `explode` and `running_reveal` GLB animations, the old tables' translations on top of the running engine and the crankcase hidden |
| `f14d` | 10 system files (9 `@memo` stages, 2.4-574 s cold each; `nozzles` a plain function) + one model | a 2,392-occurrence (903-part) F-14D: one lofted skin cut by the diverter slots and the cockpit opening (574 s of a 644 s cold build); instanced fastener, wick and perforation rows as placed prototypes; `lib` made a package (a namespace package is never imported afresh: see its README); colours; the `teardown` and `explodedHold` clips as GLB animations of the systems and their act-2 groups |

Each model's `src/README.md` says what was ported and what was dropped.

`falcon_heavy` is an educational, non-functional public-source reconstruction, not
suitable for manufacture, propulsion, testing, or operational engineering.

## Builds (2026-10-23, one machine, 10 cores, one engine, its load 8-90 from other work)

Cold is a script's first run on a fresh worker; no-op its next run, unchanged, as `python
SCRIPT.py` waits for it. Parts are prototypes / placements. Peak is the largest worker's
resident memory during the cold build.

| Project | Models | Parts | Cold | No-op |
| --- | --- | --- | --- | --- |
| `dfm-process-comparison` | 5 trays | 1 each | 2.6-2.9 s | 0.12-0.13 s |
| `examples` | 31 in 30 scripts | 1-10 | 2.9-6.0 s | 0.10-0.14 s |
| `drawings` | 8 | 1-2 layers | 3.2-4.6 s | 0.11-0.13 s |
| `branding` | 3 | 1-8 | 3.3-6.1 s | 0.12-0.13 s |
| `tests` | 3 | 3-32 | 3.4-3.8 s | 0.11-0.12 s |
| `assemblies` | 23 | 2-427 | 3.0-70 s (sculpted humanoid 70 s, iris 56 s, turbofan 34 s; the rest under 11 s) | 0.11-0.50 s |
| `falcon_heavy` | 3 | 270 | 6.6 s | 0.53 s |
| `motorbike` | the bike and its 21 parts | 38 / 46 | 9.8 s | 0.23 s |
| `qdd_actuator` | 1 | 42 / 153 | 6.6 s | 0.21 s |
| `lyra` | 18 | 92 / 111 | 8.7 s | 1.3 s |
| `juno` | 29 | 246 / 363 (the robot) | 32 s | 4.9 s |
| `tendon_hand` | 56 in 5 scripts | | 20-257 s a script | 1.0-2.5 s |
| `moonwatch` case, dial, bracelet, finishing sampler | 4 | 8-54 | 5.7-49 s | 0.14-0.36 s |
| `moonwatch` movement | 1 | | 178 s | 0.45 s |
| `moonwatch` (the full watch) | 1 | 258 / 301 | 255 s | 4.3 s |
| `tom` | 1 | 221 / 628 | 103 s (peak 2.9 GB) | 3.9 s |
| `tom` `rev3_parts.py` | 8 | | 460 s, the eight exports | |
| `hypercar` | 1 | 706 / 1,450 | 183 s | 1.5 s |
| `f1` | 1 | 833 / 853 | 492 s (2.3 GB after) | 1.2 s |
| `f14d` | 1 | 903 / 2,392 | 689 s (peak 17.2 GB, 2.4 GB after) | 1.0 s |
| `w16` | 1 | 794 / 2,575 | 927 s (peak 3.9 GB) | 5.9 s |
| `radial` | 1 | 473 / 2,400 | 3,238 s (peak 6.0 GB) | 2.9 s, its xbf taken (8.3 s without, every body replayed) |

A no-op whose body replays reuses its motions' samples, kept beside the body's run in the
worker (`tom`'s `collect` 1.50 s to 0.03 s, its run 2.47 s to 1.01 s, 2026-10-24; the rows above
predate it). A GLB of a model with long motions or
animations is large (`juno` 109 MB, `tom` 99 MB, `w16` 83 MB, `radial` 79 MB): every
moving part carries keys at its motions' sample times.
