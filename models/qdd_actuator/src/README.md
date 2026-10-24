# qdd_actuator models

| Script            | Model                                      | Description                                                   |
|-------------------|--------------------------------------------|---------------------------------------------------------------|
| qdd_actuator.py   | `qdd_actuator` (`@model`)                  | Quasi-direct-drive actuator, 4.5:1 planetary, 153 occurrences |

Build from this folder: `python qdd_actuator.py`.

The makers (`make_stator`, `make_rotor`, `make_cross_roller_bearing`,
`make_torque_sensor`, `make_driver_pcb`, `make_encoder_pcb`, `make_retainer_screws`)
are plain functions in one body, like the repeated helpers (`make_ball_bearing(z)`,
the gears): the kernel memo caches their kernel calls, and a `@memo` on the seven
saved under 0.1 s of an edit (see "When to use `@memo`" in `models/README.md`).

Materials: `_label(shape, name, *details, color=, material=)` gives every part a
material beside its colour, from the concept materials under the palette, each a
catalogue entry in the finish its colour names, with `color=None` so the palette
shows: bead-blasted, hard-anodised Aluminum 6061-T6 (housing, retainer, rear cover),
machined 7075-T6 (carrier, output flange), anodised 6063-T5 (cable tube); Steel
4140 black oxide (screws), ground (gears) and as bearing steel (races, balls,
rollers); Steel 1018 (laminations under varnish, rotor bell, connector collars);
enamelled Copper C110 (windings); Neodymium magnet N42 (rotor magnets, both pole
colours); FR4 (boards); ABS (FETs, MCU, encoder IC); a drawn 5052 can
(capacitors); Nylon PA6 (connector bodies); NBR 70A (o-rings); gold-plated Brass
C360 (contacts); Titanium Ti-6Al-4V (flexure); and two of the project's own, a
sintered `Ferrite magnet` (encoder ring) and `Polyimide film` (strain gauges).

Joints (build123d, placed with `connect_to` at their as-built pose, every value
0 as built):

- Every mount of the original and the old fastened mates the mounts do not
  already state (`rear_race`, `front_race`, `flange_mount`, `xroller_inner`) is a
  pair of `RigidJoint`s, one per side, under the mount's own labels. A rider that
  turns with its member (the inner races, sun and encoder ring on the rotor; the
  torque sensor and flange on the carrier) is fastened to the member, so it turns
  with it.
- The old revolute mates are `RevoluteJoint`s, each with the range of the
  closed drive cycle at its member's rate: `rotor_spin` on the housing,
  `rear_cage` and `front_cage` on their rotor-bearing modules (each ball ring on
  the module that carries its outer race), `output` and `roller_cage` on the
  cross-roller bearing (the carrier on the bearing's outer ring), and
  `planet1_spin`..`planet3_spin` on the carrier.

The `drive` coupling is the gear train: one control in input revolutions,
`gear_pair(actuator, "drive", rotor_spin=360, output=80, ...)`, and a constraint,
so the rotor, cages, carrier and planets turn only through it. Its range is
the joints' limits over their rates, 0..4.5. The old `quarter_output` and
`full_output` poses are configurations naming it (`rest` is as built):
`cadgen snapshot "$ID" q.png --pose '{"drive": 2.25}'` (ID: the id: line the run prints).

The old `ANIMATION_JS` clips by name (`cadgen export "$ID" GLB/qdd_actuator.glb` bakes
all three). The old clips looped; neither a motion nor an animation has a loop, and a
player repeats it:

- `drive` (12 s), a motion: `drive` swept 0 -> 4.5, linear: one closed cycle, 4.5
  input turns, seamless at tooth and pole phase.
- `inspect` (12 s), a GLB animation (`cadgen.gltf`): the same cycle (`drive`, posed)
  while every module moves to its station by `sin(pi * phase)`, the ring, sun and
  planets meshed at 210 mm (`GEAR_CLUSTER`), the connectors fixed and the housing
  rising 82 mm (`FLOOR_LIFT`), as the old `frame()` had them.
- `teardown` (10 s), a GLB animation: no drive; every module moves to its own station
  by `sin(pi * phase)`, and the planets spread 14 mm radially
  (`PLANET_EXPLODE_RADIAL`).

Each module is a reference of its own in the actuator's tree, so each moves by its own
translation, sampled every 0.1 s (`_explode_animation`); the mechanism needs no joint
for the explode, and every module stands where the old clips put it.

Other deliberate difference: the flange's seat on the flexure rim
(`rim_face`/`mount_rear`) is datums only, not connected: the flange rides the carrier
on `flange_mount`, the old fastened mate, and a second seat would close a loop.
