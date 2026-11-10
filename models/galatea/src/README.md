# Galatea

> **Work in progress.** The exterior is being restyled (a plainer, two-tone body and a new head) and the drives
> re-based on real actuators. The sections below describe the iteration before that, and its numbers are not all current.

A 1.75 m humanoid robot, designed here from a blank page: ivory lacquered skins over a
gunmetal machined frame, a bronze finned actuator left in view at every joint, and a
helmet of a head with two camera eyes lit amber under its brow. About 48 kg, 44 driven degrees
of freedom and two sprung toe hinges. Every joint is a joint of the document, so the model
stands, crouches, bows, balances on one leg, walks on the spot and closes its hands, and
six checks say what a picture cannot show: that no two parts share volume as built, in
any pose, along any motion or through any joint's travel (measured by the kernel, by a
check that is itself checked), that every part is held by something, that the poses
balance, that the linkages close, and what holding each pose asks of the drives.

| Script | Models | What it is |
| --- | --- | --- |
| `galatea.py` | `galatea` | the robot: 851 placements of 163 parts in 73 links, 72 joints, 14 couplings, 10 configurations, 8 motions |
| `stances.py` | `galatea_ready`, `_stride`, `_contrapposto`, `_reach`, `_wave`, `_present`, `_poise`, `_crouch`, `_bow` | the robot at each standing pose, set down on the ground |
| `leg_study.py` | `galatea_leg` | the left leg alone, with its hip drive: the page to study the knee and ankle linkages on |
| `head_study.py` | `galatea_head` | the neck and head alone: the page to study the face on |
| `actuators.py` | `galatea_actuators` | the actuator family on a bench (five frames, one of them in two lengths), each on a mounting plate with its output through it |
| `renders.py` | none | the presentation stills (posed, close up, and with the skins left off) and the walk as a clip, into `tmp/renders/`, which Git ignores; the clip needs ffmpeg |
| `review.py` | none | every link alone from four sides, dressed and with its skins off, into `tmp/review/`: what to look at before the whole robot |
| `checks/*.py` | none | interference (and `planted`, the test of it), attachment, balance, linkages, loads |

```
cad run src/galatea.py                       # 68 s cold; a pose or motion edit 0.6 s; unchanged 0.1 s
cad run src/stances.py                       # 90 s cold, of which the first model is 72 s
cad run src/checks/interference.py --poses   # and the other checks, below
cad run src/renders.py hero stride walk      # stills and clips by name; all of them without names
```

A run writes nothing. Files are written on request, into folders Git ignores:
`cad model export <id> GLB/galatea.glb` is 9.7 MB and carries the eight motions as
animation clips, `STEP/galatea.step` is 67.5 MB.

`links()` in `galatea.py` is the one `@memo` stage: all 73 links at the zero pose, 64 s of
kernel work that the robot and the nine standing models share. A run builds it once, so
`stances.py` costs 90 s where it cost nine minutes without the marker, and an edit to a
pose rebuilds the robot in 0.6 s.

## Conventions

Millimetres, +Z up, the robot faces -Y (the viewer's `front`), its left is +X, the origin
is on the ground between the feet. The zero pose is standing straight, arms hanging, palms
toward the thighs. `lib/` authors the centre and the left side in world coordinates at the
zero pose; the right side is its mirror image (`kit.mirror_tree`: a part symmetric about
its own mid-plane is the same prototype placed again, a handed one is reflected). A joint's
positive direction is the same anatomical motion on both sides.

Hip centres 164 apart at 920 above the ground, knees at 500, ankles at 90, the toe hinge
118 ahead of the ankle; shoulders 410 apart at 1420, elbows at 1130, wrists at 915; the
waist's centre at 1150, 32 behind the hips; the crown at 1757.

## The mechanism

- **Hip**, three drives whose axes meet at one point: yaw upright in the pelvis casting,
  roll on the back of the yoke it turns, pitch on the outside of the cradle. The leg's
  inverse kinematics (`kin.leg`) is exact because they meet.
- **Knee**. The drive is not at the knee: it sits 300 above it in the thigh and turns the
  shin through a crank and a 12 mm titanium pushrod. Crank and horn are both 55 long and
  the rod as long as the pivots are apart, so the linkage is a parallelogram and the knee
  follows the drive one to one (the coupling `knee` is its three joints at 1 : 1 : -1).
  The 1.3 kg drive rides high in the thigh, 120 under the hip, instead of at the knee. The rod stands
  square to its levers at 62.5 degrees of flexion and at 27.5 degrees at both ends of the
  travel; holding the body up pushes it, which is why it is the thick one.
- **Ankle**. Pitch comes from a double-ended drive between the shin rails, through twin
  cranks and two 7 mm steel rods to the ankle gimbal: a parallelogram again, 255 long on
  45 mm levers. The rods run behind the ankle like a tendon, so push-off pulls them. The
  gimbal's own axle is the roll drive, lying along the foot, and the two axes cross. The
  foot hangs on that drive between two uprights that rise through a well in its shell's deck.
- **Toe**: a sprung hinge under its own cap, 0 to 50 degrees, for heel-off. Not driven.
- **Waist**, three axes: yaw in the pelvis, then a spider whose fore-and-aft shaft is the
  roll axis (its drive behind) and whose cross shaft is the pitch axis, a drive at each
  end with its stator on the chest.
- **Arm**, seven: shoulder pitch in the chest wall, roll on the yoke, yaw inside the upper
  arm's head (the three meet at one point, under the ivory shoulder ball); an in-line
  hinge at the elbow; forearm roll just under it; wrist pitch and yaw, 44 apart.
- **Neck**, three: yaw under the collar, roll at the neck's root, pitch at the skull's base.
- **Head**, no joint of its own: a helmet more than a face. The skull swells into a brow
  over two eye sockets that sweep up toward the temples, and a ridge runs from the nape
  over the crown and down between them as a nasal, a graphite line along it as the
  sternum's runs down the chest. Behind the sockets is one bay, lined in black and closed
  by a smoked visor. In it are two camera eyes, toed out 8 degrees to lie with the face: a
  bronze barrel, a lens set 3.3 back in it, a ring of amber light in eight segments, a
  bronze ring round the pupil. The brow covers the upper inner part of each eye and is
  the only lid they have. A depth sensor is let into the ridge on the forehead, nine slots
  lit from behind show the voice, the antenna turret stands on the crown, and each ear is
  a finned pod (six microphone ports round a status light) with a blade swept up and back.
- **Hand**, six: four fingers of three phalanges on barrel hinges, each one tendon-driven
  degree of freedom (a coupling per finger closes its knuckles 85, 100 and 70 degrees for
  a curl of 1), and a thumb on an opposition pivot with a coupled curl of its own.

Travel, degrees. The side joints carry `l_` or `r_`; the axis is the left one's at the
zero pose. A name in italics is a coupling: the control a pose sets, with its joints.

| Control | Axis | Travel | Positive | Drive |
| --- | --- | --- | --- | --- |
| `waist_yaw` | Z | -50 to 50 | the chest turns left | A86 |
| `waist_roll` | Y | -20 to 20 | leans left | A86 |
| `waist_pitch` | X | -20 to 40 | bows forward | 2 x A70 |
| `neck_yaw` | Z | -75 to 75 | looks left | A70 |
| `neck_roll` | Y | -25 to 25 | tilts left | A40 |
| `neck_pitch` | X | -25 to 40 | nods down | A52 |
| `hip_yaw` | Z | -25 to 40 | the toes turn out | A86 |
| `hip_roll` | -Y | -20 to 25 | the leg swings out | A86 |
| `hip_pitch` | -X | -30 to 100 | the thigh swings forward | A110 |
| *`knee`*: `knee_pivot`, `knee_crank`, `knee_rod` | X | 0 to 125 | the heel goes back | A110, in the thigh |
| *`ankle_pitch`*: `ankle_pitch_pivot`, `ankle_crank`, `ankle_rod` | -X | -45 to 30 | the toes lift | the calf drive |
| `ankle_roll` | -Y | -20 to 20 | the sole turns out | A52L |
| `toe` | -X | 0 to 50 | the toes lift | none: sprung |
| `shoulder_pitch` | -X | -60 to 180 | the arm swings forward and up | A86 |
| `shoulder_roll` | -Y | -12 to 120 | the arm lifts to the side | A70 |
| `shoulder_yaw` | -Z | -90 to 90 | the elbow's pit turns inward | A52 |
| `elbow` | -X | 0 to 140 | folds | A70 |
| `wrist_roll` | -Z | -90 to 90 | the palm turns to the back | A52 |
| `wrist_pitch` | Y | -70 to 70 | the palm folds toward the forearm | A40 |
| `wrist_yaw` | X | -25 to 35 | the hand tips toward the little finger | A40 |
| *`index_curl`*, *`middle_curl`*, *`ring_curl`*, *`little_curl`*: `_mcp`, `_pip`, `_dip` | Y | 0 to 1 | closes: 85, 100, 70 | a tendon each |
| `thumb_opp` | -Z | 0 to 80 | the thumb swings across the palm | not modelled |
| *`thumb_curl`*: `thumb_mcp`, `thumb_ip` | X | 0 to 1 | closes: 55, 75 | a tendon |

### The drives

One design in five frames (`lib/dims.py`, `ACTUATORS`; `DRIVES` says which joint has
which, and `Hardware.actuator` refuses another size under that name). The stator bolts by
its flange to the back of an 8 mm plate of the parent link; the output passes through the
plate and stands 9 proud, where the child's lug bolts on with its screws sunk. The shaft
is hollow: cables cross a joint on its axis. Peak torques are design targets, in line with
strain-wave units of these sizes; masses are the model's (a housing is weighed as the
whole assembly at 3,400 kg/m3).

| Frame | Flange | Body | Hollow shaft | Peak | Mass | Where |
| --- | --- | --- | --- | --- | --- | --- |
| A110 | 110 mm | 44 mm | 20 mm | 160 N m | 1.25 kg | hip pitch, knee |
| A86 | 86 mm | 50 mm | 16 mm | 85 N m | 0.78 kg | hip yaw and roll, waist yaw and roll, shoulder pitch |
| A70 | 70 mm | 44 mm | 12 mm | 42 N m | 0.45 kg | waist pitch (two), shoulder roll, elbow, neck yaw |
| A52 | 52 mm | 36 mm | 8 mm | 16 N m | 0.20 kg | shoulder yaw, forearm roll, neck pitch |
| A52L | 52 mm | 54 mm | 8 mm | 27 N m | 0.25 kg | ankle roll |
| A40 | 40 mm | 28 mm | 6 mm | 7 N m | 0.09 kg | wrist pitch and yaw, neck roll |
| calf drive | 72 mm | 48 mm | | 60 N m | 0.56 kg | ankle pitch, with its 0.30 kg crankshaft |

Where the 47.5 kg is (`cad model inspect`, by material): the frame, 7075 plate and
castings, 18.6 kg; the housings of the 31 family drives and the two calf drives 12.4 kg;
steel (output flanges, axles, pins, crankshafts, the Achilles rods) 6.0 kg; the battery
3.7 kg; the skins 3.3 kg; electronics 1.3 kg; liners, fasteners, pads and the rest 2.2 kg.
By limb: the chest 10.8 kg, the legs 21.4 kg with 8.0 kg of it below the knees, an arm
with its hand 4.2 kg, the head and neck 1.4 kg.

### Casings, and what they cover

Machined links are plates and turned parts, hulls of circles about the axes they carry.
A skin is a 2.6 mm shell lofted through superellipse sections and trimmed by a cylinder
about every axis it borders, so a joint always turns in a round opening; it sits on pads
that grow from the frame to its inner surface, a screw through each. Hardware is drawn as
heads and pins: every screw head is seated on a face, every pin runs in a bore.

A casing either holds the structure under it inside, with air round it, or leaves it in
the open; its edge never runs across a plate. The shin guard holds the tibia's rails
3.7 mm clear down to where it ends above the ankle, and they come out below it as a fork;
the thigh fairing holds the femur's plates 3.1 mm clear between the knee's arch and the
knee drive's window. Both are open to the back, where the pushrods run. This is a rule
the first version broke: its shin guard tapered to 100 mm over rails 96 mm apart, and the
rails came through its flanks (see *Checks*).

## Poses and motions

Configurations: `ready`, `stride`, `contrapposto`, `reach`, `wave`, `present`, `crouch`,
`bow`, `poise` (balanced on the left leg) and `fists`. Motions: `walk` (one gait cycle of
2 s, the feet treading under a fixed pelvis: heel strike, roll-over, heel-off on the toe
hinge), `wave`, `bow`, `crouch`, `reach`, `poise`, `look` and `grasp`. A standing leg is
posed by where its foot goes (`kin.leg` solves hip, knee and ankle and keeps the sole
level), so both feet stand on one floor. The pelvis is the mechanism's fixed link, so a
pose lifts or tilts the feet; `stances.py` sets each posed robot back on the ground.

## Source

| Module | What it holds |
| --- | --- |
| `lib/dims.py` | the skeleton in numbers: joint centres, axes and travel, linkage geometry, the actuator frames, which drive turns which joint. No kernel |
| `lib/kin.py` | the joint tree, the couplings, forward kinematics, the leg's inverse kinematics, standing a pose on the ground. No kernel: poses, motions and checks compute with it |
| `lib/poses.py` | the configurations and motions, as numbers |
| `lib/finish.py` | sixteen finishes: a `bd_materials` grade (or a homogenised density for an assembly the model does not open) and a scalar PBR look |
| `lib/geo.py` | the geometry vocabulary: superellipse sections, lofts and shells, plates from hulls of circles, turned parts, skin mounts; and four booleans (`common`, `cut`, `carve`, `fuse`) that refuse an answer the kernel got wrong, which a lofted solid's sometimes is: valid, silent and the wrong shape |
| `lib/kit.py` | parts, prototypes and their placements, groups, `mirror_tree` |
| `lib/hardware.py` | screw heads, the actuator family, pivot caps, pushrods, pins |
| `lib/leg.py`, `torso.py`, `arm.py`, `hand.py`, `head.py` | the links, part by part |
| `lib/rig.py` | joints, couplings, configurations and motions, written on the assembled links |

## Checks

Each prints what it measured and exits non-zero when it fails. Those that need the
geometry read it as the engine exports it (one GLB, each part a closed mesh) and pose it
with `lib/kin.py`; none asks the engine to move anything.

| Check | Asks | Result |
| --- | --- | --- |
| `interference.py` | does a part sit more than 1.5 mm inside another? As built: inside every link and link against link | 0 among 851 parts |
| `interference.py --poses` | the same, link against link, at each configuration | 0 in 10 |
| `interference.py --limits` | each of the 46 controls swept alone through its travel in eight steps, against the links within three joints of it | 0 |
| `interference.py --motions` | each motion at its waypoints and four frames between each pair | 0 in 8 |
| `attachment.py` | does every part touch another part of its own link, or else a part of a link it is jointed to (a pushrod on its pin)? | all 851 held, 10 of them by a pin alone |
| `balance.py` | is the centre of mass over the support polygon in each standing pose, and by how much? | standing straight 53 mm inside, ready 78, contrapposto 52, reach 72, wave 73, present 94, crouch 27, bow 96, poise 29 (on one sole), fists 78; the stride is a gait frame, 1 mm inside |
| `linkages.py` | do the pushrods' far eyes stay on their pins through the travel, and do the axes that should meet, meet? | gaps under 1e-12 mm; hip, ankle, waist and shoulder axes meet exactly |
| `loads.py` | statics: the torque each drive holds in thirteen cases, against its peak; each pushrod's force against its Euler load | below |

What holding asks, as a share of each drive's peak (a drive holds about half its peak
without strain, and the loads below are the ratings that rule gives):

- The body alone never asks more than 49 %: the stance hip's roll drive on one leg
  (41 N m of 85). The crouch asks 54 N m of each knee (34 %) and 36 N m of the waist's
  pitch pair (43 %); the bow 33 N m of the waist (39 %); standing straight, 5 N m at the
  ankles.
- Carried loads, each with every drive at or under 50 %: 4 kg in each hand with the elbows
  square, 2.5 kg on each palm presented, 2 kg at the end of a reach or overhead, 1.5 kg in
  each hand with the arms out level. The wrists and the waist's pitch pair are what limit
  them.
- Walking adds what a foot can lever: the whole weight on one forefoot is 55 N m at the
  ankle's pitch drive (92 % of its peak), on one sole's edge 21 N m at its roll drive
  (76 %). The ankle is sized to walk and to rise on its toes, not to hop.
- The knee pushrod (12 mm titanium, 300 long) buckles at 12.3 kN; the crouch pushes it
  with 1.5 kN, and the drive at its peak and the lever at its shortest with 6.3 kN: a
  factor of 1.9. An Achilles rod (7 mm steel, 255 long) buckles at 3.6 kN against 0.9 kN
  at the drive's peak: 3.8.

Limits of the checks: a sweep moves one control at a time, so two joints at their limits
together are not covered (both thighs fully adducted do cross); the interference test is
on the meshes, deep enough to find a part 1.5 mm into another and blind to less; the
loads are static.

## Not modelled

The inside of a drive (motor, gear set, bearings, encoder: one homogenised housing), the
cable harness (the hollow shafts and the ports are its route), the finger tendons and their
motors, the toe's spring, bearings at the passive pivots (their caps are there), screw
shanks and the threads and holes they run in (heads only), the battery's cells and the
electronics' boards (blocks at a homogenised density). The walk is a kinematic gait under
a fixed pelvis, not a controller's: `balance.py` and `loads.py` say what statics allow.
