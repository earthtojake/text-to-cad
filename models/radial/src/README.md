# radial models

`models/radial` on cadgen 0.8: a nine-cylinder, single-row, supercharged,
air-cooled radial aircraft engine, modelled as a museum restoration of the 1930s-40s
archetype, unbranded, with a sectioned cylinder and a front crankcase window. One
script, `radial.py`, holds one model:

| Model | | What it is |
| --- | --- | --- |
| `radial` | `XBF/radial.xbf` | The engine: eighteen systems, their mechanism, the `drive` coupling, two configurations, the `running` motion and the `explode` and `exploded-running` GLB animations |

Build from this folder: `python radial.py`. The model declares its xbf (`@xbf`), this
corpus's example of a slow model's result kept across runs and engine restarts: a cold
build takes most of an hour (52 min on 2026-10-24). Every body replays (20: the root, the
18 systems and the propeller's blade, `lib/propeller.py`'s `blade_proto`), so a no-op
without the file is 5.6 s, nearly all of it the `running` motion sampled again (`collect`,
5.0 s); a run whose closure the xbf holds takes the file instead: 0.2 s, and after an
engine restart the file spares the cold build.

```
python radial.py
cadgen snapshot "$ID" radial.png                      # ID: the id: line the run printed
cadgen snapshot "$ID" bdc.png --pose cylinder1_bdc
cadgen export "$ID" GLB/radial.glb                    # the three clips, baked
```

## How it is built

`lib/` holds the system builders and the shared modules (`spec.py`, the source of
truth for the frame and every number, with its sources; `kin.py`, every motion;
`geo.py`, `castings.py`, `fasteners.py`, `palette.py`), unchanged but for
`import build123d as bd`, colours as the sRGB hex a shape takes, and the two changes below.

The old project was nineteen models: one per system, each with its own STEP and
worker, which `radial.py` called. Here the systems are `@memo` stages of the one model,
in occurrence (and explode) order:

    crankcase  crankshaft  rods  pistons  barrels  heads  valvetrain  cam  pushrods
    nose  reduction  propeller  blower  intake  accessory  ignition  exhaust  mount

Each is `lib/<system>.py`'s `build()`. An edit that does not reach a system's code
replays it from the worker's memory, so an edit costs its system and the root (measured
2026-10-24: an edit of `lib/nose.py` ran `nose` and the root, 42 s, every kernel call a
hit, and replayed the other 18 bodies). The propeller blade is OCCT's own construction
(a hand-interpolated B-spline surface, sewn): `blade_proto` is a `@memo` function
returning the solid as OCCT made it, so the call keys it.

Measured on 2026-10-22 (one machine, its load 4-17 from other work): cold 3,195 s
(53 min; 19 bodies, 28,105 kernel calls; the xbf 70 MB: 473 parts in 2,400 placements,
122 pairs). A no-op takes 0.4 s and rewrites nothing. An edit to the mount ring's tube
radius (`lib/mount.py`, 14 -> 14.5 mm) then ran `mount`, the root and the three bodies
that could not replay before 2026-10-24 (`barrels`, `cam`, `propeller`), 48.8 s.

- **Materials.** Every part has one of the palette's colours, and its system gives it
  the finish that colour names: `lib/palette.py`'s `FINISHES`, a catalogue material
  (aluminium 6061, steels 1018 and 4140, spring steel, stainless 304, copper, brass, NBR)
  in the original finish's look -- its metalness, roughness and clearcoat as
  `metallic`, `roughness`, `coat` and `coat_roughness`, its name the description, no
  grain -- or the project's own where the catalogue has none (section paint, bronze,
  gasket, alumina). Assignments restore each authored colour after setting the native
  material. The original grouped each system's parts by finish
  (`<system>__<finish>` compounds) for its decorator's `materials=` to target; the parts
  sit directly under their system now.
- **The heads' STEP check.** `heads.py` checks that its section cut and every head
  casting survive a STEP round trip (a cut face once came back from STEP as a
  metre-long runaway surface). The original wrote a temporary file and read it back with
  build123d's `import_step`, a read past the engine that would run the heads on every
  build; the same writer writes to a buffer now, and OCCT's reader reads it back from
  there.

## Kinematics

`lib/mechanism.py` authors build123d joints on the built systems' parts, chosen by the
original's label contract (`BUILDING.md`, "Moving parts: labels are the contract"):
every part labelled `<group>:<part>` whose group is a motion group (`crank`, `master`,
`artrod2`-`9`, `piston1`-`9`, `camring`, `camidler`, `tappet<k><v>` and its roller,
`pushrod<k><v>`, `rocker<k><v>`, `valve<k><v>`, `planet1`-`6`, `propshaft` and the
propeller, `impeller`, `blowergear1`-`3`) moves with that group. Each group is a link:
its first part carries the joint, paired by label with a joint on the link it turns or
slides on. Everything stands at 0 as built, the authored rest: crank angle 0, cylinder 1
at firing TDC. `lib/mechanism.py`'s `assemble` makes the engine, its joints, coupling,
configurations and motions.

- The gear train is linear in the crank angle, so it is one coupling, `drive`, in
  degrees of crank, its range the crank's limits (-1 to 721): the crank 1, the cam ring
  -1/8, the idler -2/3, the tappet rollers 3/2, the propeller shaft (the carrier, the
  propeller riding it) 2/3 and its planets 4/3, the impeller 10, the blower gears -3. A
  coupling is a constraint: its joints move through it alone, so every motion and
  configuration sets `drive`, never a gear.
- The crank train and the valvetrain are not linear in it. The master rod turns on the
  crankpin, each articulating rod on its knuckle pin, each piston slides in its bore,
  each tappet in its guide, each pushrod turns on its tappet's axle, each rocker on its
  shaft and each valve slides in its head's guide: joints of their own, each with the
  travel one cycle takes it through.
- Two configurations, each a crank angle with every joint where `kin.py` puts it:
  `cylinder1_bdc` (180 degrees, the bottom of cylinder 1's power stroke) and
  `cylinder1_overlap` (360: its TDC between exhaust and intake, both valves open).
- One motion, `running`, the 720-degree four-stroke cycle in 8 s: `drive` and every free
  joint from `kin.py` (`mechanism.running_values`), a function of time stored as its
  samples. Two GLB animations join it (below): `explode`, the original's teardown, 24 s
  from the rest pose with nothing turning, and `exploded-running`, `running` with the
  engine held partly apart. A GLB exported from the model carries all three as clips of
  their names (the original looped `running` and `exploded-running`; a player repeats a
  clip).

Two approximations, where `kin.py` is exact: a pushrod turns about one fixed axis
through its tappet socket (normal to its rest and full-lift directions; it turns about
0.6 degrees), where `kin.py` turns it about the axis between its rest and current
directions; and the valve springs, which `kin.py` compresses as tubes, stay as built in
their cylinder.

### The exploded clips

The original played `explode` and `exploded-running` as JavaScript translating parts by
label. Their data is `lib/explode_plan.json`, verbatim from the original's generated
`lib/anim_js.py`: the teardown `lib/explodeplan.py` planned (1,360 units -- a part, or
parts leaving together -- each a track of smoothstep-eased straight moves, a fastener's
its own moves after its host's) and the layout `lib/explodedrun.py` made (25 groups at
constant offsets over the running cycle: the cylinders 205 mm out along their bores,
their rocker covers 60 mm further, the crankcase halves, cam section, nose and
propeller forward, the blower and accessory case back). `lib/explode.py` plays them as
GLB animations (`cadgen.gltf`), exactly:

- **`explode`**: each unit's translation, its whole track (its host's moves and its
  own) sampled every 0.05 s as LINEAR keys, from the rest pose. Every part is a
  reference of its own in the engine's tree, so a unit moves by its own track alone,
  whatever joint holds it.
- **`exploded-running`**: the running cycle posed every 0.02 s (1.8 degrees of crank),
  each layout group held at its offset after the pose, and the 466 parts the original
  hid (the propeller blades, the ignition, exhaust, intake, mount, pushrod tubes,
  crankcase through-bolts and fuel line) hidden (`.hide`: a GLB has no visibility
  channel, so a part is scaled to 0).

The mechanism takes no part in either: no joint exists for the explode. A rocker turns
with its needle bearing, a tappet with its axle, a planet with its bearing and a blower
gear with its bushing, as the original's label contract moved them.

- The springs' compression and the old clips' display labels ("Exploded view
  (teardown)") have no engine equivalent.

The original's `lib/explodeplan.py`, `explodegeo.py`, `explodelayout.py`,
`explodedrun.py` and `explodecheck.py` (the planner that made the data, from the old
pipeline's built geometry, and its checks) are not ported: the data is kept as they
left it.

## Not ported

- The valve springs' compression (a tube deformation, no joint's).
- The clips' looping: neither a motion nor an animation has a loop, a player repeats a clip.
- The validation tools (`lib/gate.py`, the interference gate; `lib/animcheck.py`, the
  clips against `kin.py`) and `tools/` (`engine.py`, which serialised builds and
  renders; `critic_pack.py`): they read the old pipeline's stored documents and
  animation bake. `lib/clips.py` and `lib/systems.py` (the clip contract and the
  systems' order) live on in `lib/mechanism.py` and `radial.py`.
- The systems' own STEP files, and `render/presentation.json` (the old renderer's rig).

The original's hand-off notes are kept beside this folder: [`REPORT.md`](../REPORT.md),
[`BUILDING.md`](../BUILDING.md), [`GAUNTLET.md`](../GAUNTLET.md), [`BUGS.md`](../BUGS.md).
