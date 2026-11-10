# Galatea

A 1.76 m humanoid robot, designed here from a blank page and then redrawn in the manner
of current production humanoids: pearl panels over a black under-body, black joints, and
a helmet with one smoked face. 58.3 kg, 44 driven degrees of freedom and two sprung toe
hinges. Its 33 drives are real ones, RobStride quasi-direct drives modelled to their
maker's drawings at their maker's mass, and the brackets, bolt circles and joint spacings
follow from them. Every joint is a joint of the document, so the model stands, crouches,
bows, balances on one leg, walks on the spot and closes its hands, and its checks say what
a picture cannot: that no two parts share volume as built, in any pose, along any motion
or through any joint's travel (measured by the kernel, by a check that is itself
checked), that every part is held by something, that the poses balance, that the
linkages close, and what holding each pose asks of each drive against its datasheet.

| Script | Models | What it is |
| --- | --- | --- |
| `galatea.py` | `galatea` | the robot: 707 placements of about 180 parts in 73 links, 72 joints, 14 couplings, 10 configurations, 8 motions |
| `stances.py` | `galatea_ready`, `_stride`, `_contrapposto`, `_reach`, `_wave`, `_present`, `_poise`, `_crouch`, `_bow` | the robot at each standing pose, set down on the ground |
| `styling.py` | `galatea_styling` | the outside alone, as plain solids on the joint layout: where the look was settled before the skins were built |
| `leg_study.py` | `galatea_leg` | the left leg alone, with its hip drive: the page to study the knee and ankle linkages on |
| `head_study.py` | `galatea_head` | the neck and head alone |
| `actuators.py` | `galatea_actuators` | the five actuator models on a bench, each on a mounting plate with its output hub through it |
| `fit.py` | none | does each skin hold the mechanism under it, through its travel, and with how much air: arithmetic on the sections, no kernel, seconds |
| `renders.py` | none | the presentation stills (posed, close up, and with the skins left off) and the walk as a clip, into `tmp/renders/`, which Git ignores; the clip needs ffmpeg |
| `review.py` | none | every link alone from four sides, dressed and with its skins off, into `tmp/review/`: what to look at before the whole robot |
| `sheet.py` | none | the robot, or a region of it by height, from five sides round it in one picture, into `tmp/sheets/`: what a look is judged on |
| `checks/*.py` | none | interference (and `planted`, the test of it), attachment, balance, linkages, loads |

```
cad run src/galatea.py                       # about two minutes cold; 25 s after an edit to one link; unchanged 0.1 s
cad run src/stances.py                       # the nine poses: the first builds the robot, the rest take 2 s each
cad run src/fit.py                           # every skin against its mechanism
cad run src/checks/interference.py --poses   # and the other checks, below
cad run src/sheet.py waist 1040 1300         # a region from five sides in one picture
cad run src/renders.py hero stride walk      # stills and clips by name; all of them without names
```

A run writes nothing. Files are written on request, into folders Git ignores:
`cad model export <id> GLB/galatea.glb` carries the eight motions as animation clips.

`links()` in `galatea.py` is the one `@memo` stage: all 73 links at the zero pose, which
the robot and the nine standing models share, so an edit to a pose rebuilds in under a
second.

## Conventions

Millimetres, +Z up, the robot faces -Y (the viewer's `front`), its left is +X, the origin
is on the ground between the feet. The zero pose is standing straight, arms hanging, palms
toward the thighs. `lib/` authors the centre and the left side in world coordinates at the
zero pose; the right side is its mirror image (`kit.mirror_tree`: a part symmetric about
its own mid-plane is the same prototype placed again, a handed one is reflected). A joint's
positive direction is the same anatomical motion on both sides.

Hip centres 164 apart at 920 above the ground, knees at 500, ankles at 90, the toe hinge
118 ahead of the ankle; shoulders 424 apart at 1420, elbows at 1130, wrists at 924; the
waist's centre at 1150, 32 behind the hips; the crown at 1764.

## The mechanism

- **Hip**, three drives whose axes meet at one point: yaw upright in the pelvis casting,
  roll on the back of the yoke it turns, pitch on the outside of the cradle. The leg's
  inverse kinematics (`kin.leg`) is exact because they meet.
- **Knee**. The drive is not at the knee: it sits 280 above it in the thigh and turns the
  shin through a crank and a 12 mm titanium pushrod. Crank and horn are both 55 long and
  the rod as long as the pivots are apart, so the linkage is a parallelogram and the knee
  follows the drive one to one (the coupling `knee` is its three joints at 1 : 1 : -1).
  The 1.4 kg drive rides high in the thigh, 140 under the hip: far enough for its can to
  pass under the hip's roll drive when the leg swings back.
- **Ankle**. Pitch comes from a drive across the calf, on a bracket between the shin
  rails, through one crank and one 9 mm steel rod to the ankle gimbal: a parallelogram
  again, 255 long on 45 mm levers. The drive stands 12 behind the leg's axis, so the shin
  is straight in front and has a calf behind, and the rod runs down the back of it like a
  tendon. The gimbal's own axle is the roll drive, lying along the foot, and the two axes
  cross.
- **Toe**: a sprung hinge under its own cap, 0 to 50 degrees, for heel-off. Not driven.
- **Waist**, three axes through one point: yaw in the pelvis, then a spider whose
  fore-and-aft shaft is the roll axis (its drive behind, a bearing plate on a raked strut
  in front) and whose cross shaft is the pitch axis, a drive at each end with its stator
  on the chest.
- **Arm**, seven: shoulder pitch in the chest wall, roll on the yoke, yaw inside the upper
  arm's head (the three meet at one point); an in-line hinge at the elbow; forearm roll
  under it; wrist pitch and yaw, 51 apart: two 46 mm cans, crossed.
- **Neck**, three: yaw under the chest's top, roll at the neck's root, pitch at the
  helmet's base.
- **Head**, no joint of its own: a helmet with one face. The pearl helmet covers the
  crown, the back and the sides; the face is a single smoked shield from the brow round
  the temples to under the chin, flush with the helmet and parted from it by one shut
  line. Behind the glass, 7 mm back, a black fascia carries what the head sees with: four
  camera windows in a row under the brow and a line of light over them, which show through
  the smoke only faintly. A slot at each temple and three vents across the nape are the
  helmet's only other marks. It ends higher at the nape than at the chin, as a helmet
  does, so the neck has room when the head looks up.
- **Hand**, six: four fingers of three phalanges on barrel hinges, each one tendon-driven
  degree of freedom (a coupling per finger closes its knuckles 85, 100 and 70 degrees for
  a curl of 1), and a thumb on an opposition pivot with a coupled curl of its own.

Travel, degrees. The side joints carry `l_` or `r_`; the axis is the left one's at the
zero pose. A name in italics is a coupling: the control a pose sets, with its joints.

| Control | Axis | Travel | Positive | Drive |
| --- | --- | --- | --- | --- |
| `waist_yaw` | Z | -50 to 50 | the chest turns left | RS06 |
| `waist_roll` | Y | -15 to 15 | leans left | RS06 |
| `waist_pitch` | X | -20 to 40 | bows forward | 2 x RS06 |
| `neck_yaw` | Z | -75 to 75 | looks left | RS00 |
| `neck_roll` | Y | -25 to 25 | tilts left | RS05 |
| `neck_pitch` | X | -25 to 40 | nods down | RS00 |
| `hip_yaw` | Z | -25 to 20 | the toes turn out | RS06 |
| `hip_roll` | -Y | -20 to 16 | the leg swings out | RS04 |
| `hip_pitch` | -X | -30 to 100 | the thigh swings forward | RS04 |
| *`knee`*: `knee_pivot`, `knee_crank`, `knee_rod` | X | 0 to 125 | the heel goes back | RS04, in the thigh |
| *`ankle_pitch`*: `ankle_pitch_pivot`, `ankle_crank`, `ankle_rod` | -X | -45 to 30 | the toes lift | RS04, in the calf |
| `ankle_roll` | -Y | -20 to 20 | the sole turns out | RS00 |
| `toe` | -X | 0 to 50 | the toes lift | none: sprung |
| `shoulder_pitch` | -X | -60 to 180 | the arm swings forward and up | RS03 |
| `shoulder_roll` | -Y | -12 to 120 | the arm lifts to the side | RS06 |
| `shoulder_yaw` | -Z | -90 to 90 | the elbow's pit turns inward | RS00 |
| `elbow` | -X | 0 to 140 | folds | RS06 |
| `wrist_roll` | -Z | -90 to 90 | the palm turns to the back | RS05 |
| `wrist_pitch` | Y | -70 to 70 | the palm folds toward the forearm | RS05 |
| `wrist_yaw` | X | -25 to 35 | the hand tips toward the little finger | RS05 |
| *`index_curl`*, *`middle_curl`*, *`ring_curl`*, *`little_curl`*: `_mcp`, `_pip`, `_dip` | Y | 0 to 1 | closes: 85, 100, 70 | a tendon each |
| `thumb_opp` | -Z | 0 to 80 | the thumb swings across the palm | not modelled |
| *`thumb_curl`*: `thumb_mcp`, `thumb_ip` | X | 0 to 1 | closes: 55, 75 | a tendon |

One travel depends on another. The hips' roll drives stand behind them and swing inward
as the feet turn out, and the two cans must not meet on the centre plane: both feet turn
out 10 degrees together, or one 20 with the other straight. `kin.check_limits` holds every
pose to that (`dims.hip_can_reach`).

### The drives

RobStride quasi-direct drives: a frameless motor, a 7.75 to 10 : 1 planetary stage, an
encoder and the driver in one housing, 48 V, CAN. `lib/dims.py` holds each model as its
maker gives it (`ACTUATORS`) and which joint has which (`DRIVES`; `Hardware.actuator`
refuses another model under that name). `actuators.py` sets the five on a bench.

| Model | Body | Rear cover | Mounting holes | Output holes | Rated | Peak | Mass | Where |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RS04 | 120 x 39 | 94 x 13.2 | 10 x M4 on 106 | 9 x M5 on 36 | 40 N m | 120 N m | 1.42 kg | hip roll, hip pitch, knee, ankle pitch |
| RS03 | 98 x 39.5, 106 over its ears | 79.5 x 12.1 | 8 x M4 on 98 | 6 x M4 on 30.4 | 20 N m | 60 N m | 0.88 kg | shoulder pitch |
| RS06 | 80 x 33, 88 over its ears | 70 x 14.5 | 8 x M3 on 82 | 6 x M4 on 24 | 11 N m | 36 N m | 0.62 kg | hip yaw, waist yaw, roll and pitch (two), shoulder roll, elbow |
| RS00 | 57 x 51 overall | | 6 x M3 on 50 | 6 x M3 on 27 | 5 N m | 14 N m | 0.31 kg | ankle roll, shoulder yaw, neck yaw and pitch |
| RS05 | 46 x 44 overall | | 4 x M3 on 41.5 | 6 x M4 on 24 | 1.6 N m | 5.5 N m | 0.19 kg | forearm roll, wrist pitch and yaw, neck roll |

How one is held. Its mounting face is the front of its body, where the tapped mounting
holes are. An 8 mm plate of the parent link lies on that face and is screwed to it from
the far side, on the maker's bolt circle, the heads sunk flush (`hardware.mount_bores`
cuts the register's hole and the counterbores). The output flange is in the middle of
the face; a steel hub bolted to it stands through the plate and 9 proud, and the child
link's lug bolts to the hub on the output flange's own bolt circle. The two small cans
are held by countersunk screws, which show no heads. A housing and its rear cover carry
one homogenised density, so that the unit weighs what its maker says.

What is the maker's and what is not. Diameters, lengths, bolt circles, torques and masses
are from RobStride's product pages and its Product Specification Document of 26 June 2025
(links under *Sources*). Three things are mine: the main-body diameters of the RS03 and
the RS06, which their drawings show but do not dimension (98 and 80, scaled from the
drawings; the diameters over the ears are given); the step to the rear cover of the RS00
and the RS05, of which only the overall size is given; and the ears, drawn as ribs the
length of the body. The RS05's output circle is read as 24 from a drawing that also
dimensions 19. None of these drives has a hollow shaft, so cables pass a joint beside
it; no harness is modelled. The hub is this robot's part, not RobStride's.

What real drives changed. They are up to 20 mm larger across than the drives first
invented for this skeleton. The knee's drive moved down 20 so that it passes under the
hip's roll drive; the wrist's two axes moved apart to 51 and the neck's to 55 so that
their cans cross; the shoulders moved out 7 each; the waist's yoke grew 12 longer; the
ankle's double-ended drive, which nobody makes, became one RS04 with one crank and one
rod; and the hips' toe-out became the coupled travel above. Covering them cost travel
too: the waist leans 15 degrees to a side, not 20, because the abdomen that hides its
drives has to clear the pelvis.

Where the 58.3 kg is: the chest 11.4 kg, each thigh 4.0, each shin 3.5, the pelvis 3.4,
each hip's yoke and cradle 4.1; the legs 28.6 kg in all, 11.1 kg of it below the knees.
The 33 drives are 22.5 kg of it.

### Skins

A skin is two layers over one lofted form (rows of superellipse sections, `lib/skin.py`).
The panel is pearl, 2.6 mm, the outside; it is cut into panels by regions drawn in a side
or front view. The liner is black, 1.8 mm, under all of it: where no panel lies it is the
outside, the under-body that shows at the flanks, between a leg's front and back plates
and in every shut line. The frame carries the liner on pads that grow to its inner
surface. No screw shows on a panel. What shows between the skins is black as well: the
drives' housings, and the frames, which are 7075 aluminium anodised black, so that a joint
reads as one dark mass and not as its brackets.

The mechanism stands inside the liner with 3 mm of air round it, through the travel of
whatever moves under it. `fit.py` measures that from the sections and the meshes, without
the kernel, so a form is drawn and redrawn in seconds; every form is entered in
`skin.FORMS` with the links it has to hold and the poses to hold them at.

The pelvis is a black band round its casting, arched over each hip, with one pearl plate
in front and two round openings behind, on the charge and data ports. The shin's two
plates end over the ankle in a point: the form cannot narrow there, because the ankle's
fork is under it, so the pearl does and leaves the liner's black at the hem's corners.

Where a skin meets a joint it ends on the line the joint needs. The thigh's ends at the
knee on a slant, the line the calf's back comes up to at full flexion; it is notched
behind the hip, where the roll drive's can comes down when the leg swings back, and
raked in front, lower toward the groin than at the outside of the hip: the plane under
every point of the skin that would otherwise come up under the pelvis with the thigh
raised and the leg turned in. Nothing hangs between the hips for the same reason. The upper
arm's ends on the slant the forearm folds up to. The chest's liner runs on down round the
waist as the abdomen, a black shell over the waist's three drives: wide enough for the
pitch drives, which ride on the chest's lugs, and deep enough behind for the roll drive's
can, which the chest swings past as it leans. It ends in a hem drawn as a V in the side
view, its point under the pitch axis, where a bow does not move it, and its ends high,
where a bow swings them down: leaning 40 degrees forward, 20 back, 15 to a side or two of
those at once, the hem stays 6 mm off the pelvis. That hem is what ends the waist's roll
at 15 degrees. Under it in front, a small shield (a piece of a sphere about the waist's
centre, on the yoke) closes the gap between the chest's lugs. The shoulder's pod is a
capsule about the roll axis, so that it turns with the arm round the yoke and the roll
drive behind it; a slot round it lets the yoke's arm through. The hip's cap is a cup about the pitch axis,
over the pitch drive's can, and turns with the thigh.

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
| `lib/dims.py` | the skeleton in numbers: joint centres, axes and travel, linkage geometry, the actuators as their maker gives them, which drive turns which joint. No kernel |
| `lib/kin.py` | the joint tree, the couplings, forward kinematics, the leg's inverse kinematics, standing a pose on the ground, the limits a pose is held to. No kernel: poses, motions and checks compute with it |
| `lib/poses.py` | the configurations and motions, as numbers |
| `lib/finish.py` | the finishes: a `bd_materials` grade (or a homogenised density for an assembly the model does not open) and a scalar PBR look |
| `lib/geo.py` | the geometry vocabulary: superellipse sections, lofts, plates from hulls of circles, turned parts; and four booleans (`common`, `cut`, `carve`, `fuse`) that refuse an answer the kernel got wrong, re-measuring by adaptive integration before they do |
| `lib/skin.py` | how a skin is made (a form at several insets, its panel and liner layers, regions drawn in a view) and the register of forms `fit.py` reads |
| `lib/kit.py` | parts, prototypes and their placements, groups, `mirror_tree` |
| `lib/hardware.py` | screw heads, the actuators, their mounting and output patterns, pivot caps, pushrods, pins |
| `lib/leg.py`, `torso.py`, `arm.py`, `hand.py`, `head.py` | the links, part by part, each with its skin |
| `lib/rig.py` | joints, couplings, configurations and motions, written on the assembled links |

## Checks

Each prints what it measured and exits non-zero when it fails. Those that need the
geometry read it as the engine exports it and pose it with `lib/kin.py`; none asks the
engine to move anything.

| Check | Asks | Result |
| --- | --- | --- |
| `interference.py` | do two parts share volume? As built: inside every link and link against link | none in the 484 pairs near enough to measure, of 1,200 whose boxes meet |
| `interference.py --poses` | the same, link against link, at each configuration | none in the ten configurations, 135 to 139 pairs measured in each |
| `interference.py --limits` | each control swept alone through its travel in eight steps, against the links within three joints of it | none: the 26 controls of the centre and the left side, which stands for the right |
| `interference.py --corners` | the joints that share a centre, moved together: waist, neck, hip, shoulder, wrist and ankle, each at every corner of its travel and the middle of every edge | none in the 104 poses |
| `interference.py --motions` | each motion at its waypoints and between them | none in the eight motions |
| `planted.py` | does that check find a plate planted through a 2.6 mm skin, clear one 0.3 mm from it, and pass a pin in its bore? | it does |
| `fit.py` | does each skin hold its mechanism with 3 mm of air, through the travel under it? | it does. The least air: 3.1 mm round the upper arm and the pelvis, 3.3 the shin, 3.5 the chest, 3.8 the thigh, 5.3 the forearm, 15 the head |
| `attachment.py` | does every part touch another part of its own link, or else a part of a link it is jointed to (a pushrod on its pin)? | every part is held, eight of them by a joint's pin alone |
| `balance.py` | is the centre of mass over the support polygon in each standing pose, and by how much? | standing straight 51 mm inside, ready 77, contrapposto 55, reach 72, wave 72, present 94, crouch 32, bow 90, poise 30 (on one sole), fists 77; the stride is a gait frame |
| `linkages.py` | do the pushrods' far eyes stay on their pins through the travel, and do the axes that should meet, meet? | gaps under 1e-12 mm; hip, ankle, waist and shoulder axes meet exactly |
| `loads.py` | statics: the torque each drive holds in thirteen cases, against its rated and its peak torque; each pushrod's force against its Euler load | below |

How interference is judged. The verdict is the kernel's: two parts interfere when their
solids share more than 0.5 mm3 (`overlap_volume` on the model's own solids; parts that
only touch share none). The meshes only choose which pairs it is asked about, and choose
generously. A volume is believed when the pair gives it both ways round, because the
kernel's intersection has been seen to differ with the order of its two solids; when the
two differ, what a cut takes decides and the pair is named. A pair the kernel cannot
intersect is reported unmeasured, which fails the check.

What holding asks (`loads.py`). A drive holds its rated torque for as long as one likes
and its peak briefly. A pose counts as held while every drive is within its rated torque,
and as held briefly while every drive is within 75 % of its peak.

- Standing straight asks 6 N m of each ankle; `ready`, `contrapposto` and `wave` are
  within every rated torque (the stance hip's roll drive at 87 % in contrapposto).
- Held briefly: the crouch (64 N m at each knee, 159 % of an RS04's rated torque and 53 %
  of its peak; 46 N m at the waist's pitch pair), the bow, standing on one leg (52 N m at
  the stance hip's roll drive, 129 % of rated), and the carried loads: 4 kg in each hand
  with the elbows square, 2.5 kg on each palm presented, 2 kg at the end of a reach, 1.5
  kg in each hand with the arms out level. The wrists (an RS05 gives 1.6 N m rated) and
  the waist's pitch pair are what limit them: a level palm carries about 1 kg for as long
  as one likes.
- Walking adds what a foot can lever. The whole weight on one forefoot is 68 N m at the
  ankle's pitch drive, 56 % of an RS04's peak, which is why that drive is an RS04 and not
  the RS03 first fitted (60 N m peak). The whole weight on one sole's edge would be 25 N m
  at the ankle's roll drive, and an RS00 gives 14: Galatea cannot stand on the edge of a
  foot. Its ankle steers the centre of pressure 24 mm either side of the roll axis, and
  balance sideways is the hips' work.
- The knee's pushrod (12 mm titanium, 280 long) buckles at 14.1 kN; the crouch pushes it
  with 1.8 kN, and the drive at its peak with the lever at its shortest with 4.7 kN: a
  factor of 3.0. The ankle's rod (9 mm steel, 255 long) buckles at 9.8 kN and keeps
  2.6 on the same measure.

Limits of the checks: a sweep moves one control at a time, and joints are taken to their
limits together only within a group that shares a centre (`--corners`), so an arm swung
into a leg, or a knee folded with the hip at a corner, is covered only where a pose or a
motion covers it; the loads are static; `fit.py` interpolates the sections linearly where the loft is a spline,
and is a design aid whose word the exact check confirms.

## Reviewing a change

The order this model is now reviewed in, after an earlier version passed its checks with
rails standing through a shin guard: a part alone, then its link alone from four sides,
dressed and bare (`review.py`), then a joint at both ends of its travel, then the
assembly, then the poses. A skin is drawn with an intended relation to what it covers
(`fit.py` holds it to that). A check is trusted only after it has failed on a planted
example of what it guards against (`planted.py`). The look is settled on a styling
model, sent for an opinion, before it is detailed (`styling.py`), and judged from every
side, the back included (`sheet.py`): a first restyle passed every check here with three
bare drives still showing behind the waist.

## Not modelled

The inside of a drive (motor, gear set, bearings, encoder, driver: one homogenised
housing and cover), the cable harness, the finger tendons and their motors, the toe's
spring, bearings at the passive pivots (their caps are there), screw shanks and the
threads and holes they run in (heads only), the clips that hold a panel on its liner, the
battery's cells and the electronics' boards (blocks at a homogenised density). The walk
is a kinematic gait under a fixed pelvis, not a controller's: `balance.py` and `loads.py`
say what statics allow.

## Sources

- RobStride product pages, RS00 to RS06: https://www.robstride.com/products/robStride00
  (and `robStride03`, `robStride04`, `robStride05`, `robStride06`).
- RobStride Product Specification Document, 26 June 2025, with the dimension drawings, as
  hosted by a distributor:
  https://files.seeedstudio.com/products/RobStride/%E7%81%B5%E8%B6%B3%E6%97%B6%E4%BB%A3%E4%BA%A7%E5%93%81%E8%A7%84%E6%A0%BC%E4%BB%8B%E7%BB%8D%20RobStride%20Product%20Specification%20Document%2020250626.pdf
- Manuals and STEP files: https://github.com/RobStride/Product_Information
