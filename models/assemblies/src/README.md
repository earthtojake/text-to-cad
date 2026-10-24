# assemblies models

`models/assemblies` on cadgen 0.8: the repo's demo assemblies, one group per
assembly, each model a `@model` that writes nothing. `src/<group>/` holds the group's
scripts and its own `lib/`. A group imports its siblings and its
own `lib/`, and nothing across groups. There are 23 models. The old project had
27 decorated files: `link_robot` and `research_humanoid` were three each, and
each is one model now.

Build a group from its folder; each script builds the models its `__main__` calls and
prints each one's id and page:

```
cd planetary_gear_assembly && python planetary_gear_assembly.py
cadgen snapshot "$ID" gear.png --pose half_cycle      # ID: the id: line the run printed
```

| Script | Model | What it is |
| --- | --- | --- |
| `compact_humanoid/compact_humanoid.py` | `compact_humanoid` | 28-DOF compact humanoid concept; each actuator axis is an unconnected joint on its cartridge, so there is no mechanism (none before either) |
| `cutaway_turbofan_engine/cutaway_turbofan_engine.py` | `cutaway_turbofan_engine` | Labeled multi-body cutaway turbofan |
| `flying_car/flying_car.py` | `flying_car` | Four-rotor flying car concept |
| `link_robot/link_robot.py` | `link_robot` | A base, two placements of `link_arm()` and a spare `link_pin()`: one pin B-rep placed five times, two levels deep |
| `lunar_rover_corner_assembly/lunar_rover_corner_assembly.py` | `lunar_rover_corner_assembly` | Lunar rover corner: wheel, hub motor, suspension |
| `mars_rover_concept/mars_rover_concept.py` | `mars_rover_concept` | Mars rover on terrain: 28 joints, 1 coupling, 4 configurations, 3 motions and an animation |
| `mechanical_iris_aperture/mechanical_iris_aperture.py` | `mechanical_iris_aperture` | Labeled mechanical iris aperture |
| `miniature_spiral_staircase/miniature_spiral_staircase.py` | `miniature_spiral_staircase` | Labeled miniature spiral staircase |
| `motorcycle_fidgets/motorcycle_{helmet,seat,shock,wheel}_fidget.py` | `motorcycle_*_fidget` | Four Cherry MX switch fidgets; the group shares `lib/mx_switch_socket.py` and `lib/color.py` |
| `motorcycle_shock_absorber/motorcycle_shock_absorber.py` | `motorcycle_shock_absorber` | Coilover damper; the rod rides a linear joint, `damper_stroke` |
| `pelican_riding_bicycle/pelican_riding_bicycle.py` | `pelican_riding_bicycle` | Pelican riding a bicycle |
| `photo_coffee_cup/photo_coffee_cup.py` | `photo_coffee_cup` | Photo-inspired takeaway coffee cup |
| `planetary_gear_assembly/planetary_gear_assembly.py` | `planetary_gear_assembly` | The docs site's hero: a gear train driven by one coupling, `drive`, its `meshCycle` motion and its `inspectExplode` animation, which its GLB carries as clips (`apps/docs/scripts/sync-hero-glb.mjs` exports it) |
| `planetary_gear_stage/planetary_gear_stage.py` | `planetary_gear_stage` | Simplified planetary gear stage (`lib/gear_teeth.py`) |
| `research_humanoid/research_humanoid.py` | `research_humanoid` | Adult-scale humanoid: 28 body joints, and 15 per hand from `lib.build_hand(side)` |
| `robotic_hand_end_effector/robotic_hand_end_effector.py` | `robotic_hand_end_effector` | Cybernetic robotic hand end-effector |
| `sculpted_humanoid/sculpted_humanoid.py` | `sculpted_humanoid` | Sculpted humanoid: 58 revolute joints in an athletic pose |
| `six_axis_industrial_robot_arm/six_axis_industrial_robot_arm.py` | `six_axis_industrial_robot_arm` | Six-axis industrial robot arm display assembly |
| `six_blade_open_propeller/six_blade_open_propeller.py` | `six_blade_open_propeller` | Six-blade open propeller |
| `spiral_staircase/spiral_staircase.py` | `spiral_staircase` | Miniature spiral staircase |

## The port

- `@step(out="../../STEP/<group>/<name>.step")` became `@model`. `build123d` is
  imported directly. Nothing else reads these models' STEP, so no model declares
  one; `cadgen export <id> STEP/<name>.step` writes one on demand. The docs hero's GLB
  is the planetary gear's, written by the docs site's `sync-hero-glb.mjs` with
  `cadgen.export(model, path)`.
- No model calls another. `link_robot`'s arm and pin and `research_humanoid`'s
  hands are plain functions called in the one body (the hand models' two scripts
  are gone). The engine places a part used twice as one prototype.
- `AssemblyHelper` and `label_shape` became build123d itself. Each relation is a
  `RevoluteJoint` (or `LinearJoint`) on the fixed part and a `RigidJoint` on the
  moving one, connected at 0 where the parts stand. Every model with joints has
  its pose as the as-built configuration. A pair is named by its joint.
- `research_humanoid` fastens each joint's clevis yoke to the joint's fixed
  side. The old model exported no mechanism, so a yoke left standing when its
  limb posed never showed. Each hand's palm carries `<side>_hand_mount`, and the
  wrist carrier carries its twin; the label pairs them, since the palm sits
  inside the hand's own compound, where `connect_to` cannot place it.
- `motorcycle_shock_absorber` seats its spring on the lower perch only. A second
  rigid seat on the rod's perch would weld the rod to the body and lock the
  stroke.
- `flying_car`, `lunar_rover_corner_assembly`, `mars_rover_concept` and
  `pelican_riding_bicycle` made their `cylinder_between` with OCCT's
  `BRepPrimAPI_MakeCylinder`, a maker the memo does not key. Their calls ran
  uncached and their bodies were never kept. The helper is a placed
  `bd.Cylinder` now, the same cylinder.
- No model is a `@memo`. The kernel memo already replays every call an edit does
  not reach, so 17 of the 23 edits measured cost under a second. The two
  slowest edits land on expensive geometry itself: the sculpted humanoid's
  pelvis (11.7 s, its joint keepouts trimmed again) and the propeller's hub
  height (5.4 s: it sets every blade's root span and height). No function holds seconds of kernel
  work that an edit elsewhere leaves untouched.

## Kinematics, motions and what was dropped

- `planetary_gear_assembly`: the typed mates are build123d joints. `sun` and
  `carrier` turn on the ring (the ground), `pin1..3` are fastened to the
  carrier and `planet1..3` turn on their pins. `drive` is a coupling over the exact fixed-ring ratios (sun 1, carrier
  24/84, planets -(24/18)(60/84)); a coupling is a constraint, so the sun,
  carrier and planets turn only through it, and its range is the sun's limits,
  0..1260 (the old control's range; the old sun mate allowed -1260..1260).
  `quarter_cycle` and `half_cycle` are configurations. `meshCycle` is `drive`
  swept 0 -> 1260 over 6 s, linear, a seamless cycle a player repeats.
  `inspectExplode` is a GLB animation (`cadgen.gltf`): over 5 s it drives `drive`
  through the same sweep (`.pose`) while each planet and its pin move 16 mm out along
  the planet's rest radial and back, the sun lifts 7 mm and the carrier and pins drop
  4 mm, as the old clip did, the translations eased out to 2.5 s and back. A GLB
  exported from the model carries both as clips of their names; the STL and 3MF exports
  are dropped.
- `mars_rover_concept`: its 27 typed mates are build123d joints on its
  top-level groups (26 revolute, one linear: `lid_lift`). Of its 7 couplings
  one is a real linkage and stays: `rocker_split`, the differential bar making
  the rockers counter-rotate and taking half the split, a constraint (the
  rockers and the bar move only through it, over the rockers' +-12 deg). The
  six convenience controls are dropped, each pose and motion setting their
  joints itself:
  - `drive` (all six wheels by one knob): each wheel is driven on its own.
  - `steer` (the Ackermann-ish gearing, 1 / 0.79 / -1 / -0.79): the four
    steer joints set by those ratios (`_steer`).
  - `crab` (every corner to one heading): no pose or clip used it.
  - `bogie_pitch` (both bogies by one knob): the bogies pivot independently.
  - `solar_deploy` (both wings, mirrored): `solar_left` and `-solar_right`
    (`_solar`).
  - `cutaway` (lid 420 mm, panel -75 deg by one 0..1 knob): `lid_lift` and
    `panel_swing` (`_cutaway`).

  Its 4 poses are configurations: `stowed`, `deployed`, `arm_reach`,
  `cutaway_open`. Limits are offsets from the display pose, as before. Its four
  clips keep the old clips' numbers: `driveAround` (18 s), `armCycle` (12 s) and
  `deploySequence` (20 s) are motions, functions of time over the joints, and
  `explodedAssembly` (12 s) is a GLB animation (`cadgen.gltf`), none looped, as
  before:
  - `heave`, a prismatic joint: the chassis rides the terrain, which is the ground
    and stays put while the body heaves over it in `driveAround`; every group the
    chassis carries heaves with it, through its joints or fastened to it.
  - `explodedAssembly`: each group but the terrain and the chassis moves along the
    old clip's vector, 520 mm times its length at the peak, eased out over 6 s and
    back. The groups are siblings in the rover's tree, so each moves by its own
    vector alone, as the old clip moved them, without dragging the groups hung on
    its joints.
  - Deliberate differences: `driveAround` rolls the wheels four turns
    unwrapped, where the old clip wrapped the angle at 360 (a jump a joint's
    curve cannot take), so the six wheel joints range over +-1440 deg, four
    turns each way (+-360 before); the mast pitches about
    its head pivot as it heaves with the body, where the old clip pitched it
    about the unheaved pivot (at most 2.5 mm apart). `deploySequence` also
    thinned the dust layer's opacity as the deck opened; 0.8 has no opacity
    channel, so the dust layer stays as built.
- `miniature_spiral_staircase`: the `_highres` STL, 3MF and GLB at
  `mesh_tolerance=4e-4` are dropped. The engine meshes at one tolerance
  (FreeCAD's), configurable nowhere.
- `motorcycle_fidgets`: `cadgen.srgb(hex, alpha)` -> the `(hex, alpha)` pair, which a shape takes as it is.
