# Galatea

A 1.76 m humanoid robot, designed here from a blank page and then redrawn in the manner
of current production humanoids: pearl panels over a black under-body, black joints, and
a helmet with one smoked face. What it adds of its own is small. Every hem is a shallow
V, the status light on the breastplate is a chevron on the same slope, and a hairline of
champagne marks the collar, the sleeves' rims, the hips' caps and the knees. 57.4 kg, 44
driven degrees of freedom and two sprung toe hinges. Its 33 drives are real ones,
RobStride quasi-direct drives, in the model as their maker's own STEP solids at their
maker's mass, and the brackets, bolt circles and joint spacings follow from them. Every
joint is a joint of the document, so the model stands, crouches, bows, balances on one
leg, walks on the spot and closes its hands, and its checks say what a picture cannot: that no two parts share volume as built, in any pose, along any motion
or through any joint's travel (measured by the kernel, by a check that is itself
checked), that every part is held by something, that the poses balance, that the
linkages close, and what holding each pose asks of each drive against its datasheet.

| Script | Models | What it is |
| --- | --- | --- |
| `vendor.py` | none | fetches RobStride's STEP models of the five drives into `vendor/` and converts them: run it once, first |
| `galatea.py` | `galatea` | the robot: 689 placements of about 170 parts in 73 links, 72 joints, 14 couplings, 11 configurations, 10 motions |
| `stances.py` | `galatea_ready`, `_stride`, `_contrapposto`, `_reach`, `_wave`, `_present`, `_poise`, `_crouch`, `_bow` | the robot at each standing pose, set down on the ground |
| `styling.py` | `galatea_styling` | the outside alone, as plain solids on the joint layout: where the look was settled before the skins were built |
| `leg_study.py` | `galatea_leg` | the left leg alone, with its hip drive: the page to study the knee and ankle linkages on |
| `head_study.py` | `galatea_head` | the neck and head alone |
| `actuators.py` | `galatea_actuators` | the five actuator models on a bench, each on a mounting plate with its output hub through it |
| `fit.py` | none | does each skin hold the mechanism under it, through its travel, and with how much air: arithmetic on the sections, no kernel, seconds |
| `renders.py` | none | the presentation stills (posed, close up, and with the skins left off) and the walk as a clip, into `tmp/renders/`, which Git ignores; the clip needs ffmpeg |
| `review.py` | none | every link alone from four sides, dressed and with its skins off, into `tmp/review/`: what to look at before the whole robot |
| `sheet.py` | none | the robot, or a region of it by height, from five sides round it in one picture, into `tmp/sheets/`: what a look is judged on |
| `film.py` | none | the film: a studio, its shots and the cut, rendered with Blender from the robot's GLB into `tmp/film/` (below) |
| `views.py` | none | the robot as the CAD viewer draws it, as frames for the film: solid on the grid, parts exploded, the walk in x-ray |
| `checks/*.py` | none | drives, interference (and `planted`, the test of it), attachment, balance, linkages, loads |

[`../FEEDBACK.md`](../FEEDBACK.md) is what building, filming and simulating it taught
about the tooling: bugs, gaps that cost time, and what worked well.

`../sim/` is the robot in MuJoCo ([its README](../sim/README.md)): the same links, joints,
couplings, masses and drives, written from this model by a script, standing on a floor
under gravity with a position servo for each drive. It is where the motions below were
found wanting and put right. It stands, lands from a small drop, bows, waves, reaches,
looks about, closes its hands and squats on its own feet; on one leg it stands only
with its pelvis held.

```
cad run src/vendor.py                        # once: RobStride's five STEP files, 53 MB, into vendor/ (Git keeps no CAD file)
cad run src/galatea.py                       # four minutes cold; a pose or a motion changed 2 s; unchanged 0.1 s
cad run src/stances.py                       # the nine poses: the first builds the robot, the rest take 12 s each
cad run src/fit.py                           # every skin against its mechanism
cad run src/checks/interference.py --poses   # and the other checks, below
cad run src/sheet.py waist 1040 1300         # a region from five sides in one picture
cad run src/renders.py hero stride walk      # stills and clips by name; all of them without names
```

A run writes nothing. Files are written on request, into folders Git ignores:
`cad model export <id> GLB/galatea.glb` carries the ten motions as animation clips, and
the exploded view (`lib/show.py`) as an eleventh.

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
waist's centre at 1150, 32 behind the hips; the crown at 1763.

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
  the smoke only faintly. A slot at each temple, filled flush by a champagne grille over a
  microphone, and three vents across the nape are the helmet's only other marks. It ends
  higher at the nape than at the chin, as a helmet does, so the neck has room when the
  head looks up.
- **Hand**, six: four fingers of three phalanges on barrel hinges, each one tendon-driven
  degree of freedom (a coupling per finger closes its knuckles 85, 100 and 70 degrees for
  a curl of 1), and a thumb on an opposition pivot with a coupled curl of its own. A
  phalanx is a bar with its long edges rounded, a fingertip one with a round end.

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
encoder and the driver in one housing, 48 V, CAN. Their shapes are RobStride's own: the
STEP file of each model from the maker's repository, fetched by `vendor.py` at a named
commit and checked against a checksum, converted once to an xbf and read by
`lib/hardware.py`. `lib/dims.py` holds what the brackets and the checks need of each
(`ACTUATORS`: where its mounting face lies in the maker's file and how the file is
turned, its bolt circles, torques and mass) and which joint has which (`DRIVES`;
`Hardware.actuator` refuses another model under that name). `actuators.py` sets the five
on a bench.

| Model | Body | Rear cover | Mounting holes | Output holes | Rated | Peak | Mass | Where |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RS04 | 120 x 39 | 94 x 13.2 | 10 x M4 on 106 | 9 x M5 on 36 | 35 N m | 120 N m | 1.51 kg | hip roll, hip pitch, knee, ankle pitch |
| RS03 | 96.4 x 39.5, 106 over its lobes | 79.5 x 14.6 | 8 x M4 on 98 | 6 x M4 on 30.4 | 21 N m | 60 N m | 0.928 kg | shoulder pitch |
| RS06 | 83.2 x 33, 88 over its lobes | 70 x 16 | 8 x M3 on 82 | 6 x M4 on 24 | 11 N m | 36 N m | 0.615 kg | hip yaw, waist yaw, roll and pitch (two), shoulder roll, elbow |
| RS00 | 57 x 35.8 | 55 x 15.3 | 6 x M3 on 50 | 6 x M3 on 27 | 5 N m | 14 N m | 0.31 kg | ankle roll, shoulder yaw, neck yaw and pitch |
| RS05 | 46 x 44 overall | | 4 x M3 on 41.6 | 6 x M4 on 24 | 1.8 N m | 5.5 N m | 0.243 kg | forearm roll, wrist pitch and yaw, neck roll |

How one is held. Its mounting face is the front of its body, where the tapped mounting
holes are. An 8 mm plate of the parent link lies on that face and is screwed to it from
the far side, on the maker's bolt circle, the heads sunk flush (`hardware.mount_bores`
cuts the register's hole and the counterbores). The output flange is in the middle of
the face; a steel hub bolted to it stands through the plate and 9 proud, and the child
link's lug bolts to the hub on the output flange's own bolt circle (the RS04's nine
holes are not evenly spaced, and the hub is relieved over its locating pins). The
two small cans are held by countersunk screws, which show no heads. The maker's solid
carries one homogenised density, so that the unit weighs what its maker says.

What is the maker's and what is not. The solids are RobStride's, unchanged. Measured on
them here: the height of each mounting face and output flange in its file, the turn that
puts its mounting holes where `dims.py` says, and the plain envelope the checks use.
Torques and masses are from RobStride's Product Specification of 9 October 2026, in the
same repository. A rated torque is continuous on the maker's aluminium heat sink, whose
size the table in `dims.py` gives: an RS04 holds 40 N m on a plate of 345 x 345 and 35
on one of 220 x 200, and 35 is what this robot's brackets can claim. None of these
drives has a hollow shaft, so cables pass a joint beside it; no harness is modelled, but
each drive is turned so that its cable connector points at free space (the hips' pitch
drives and the calves' with theirs underneath). The hub is this robot's part, not
RobStride's.

What real drives changed. They are up to 20 mm larger across than the drives first
invented for this skeleton. The knee's drive moved down 20 so that it passes under the
hip's roll drive; the wrist's two axes moved apart to 51 and the neck's to 55 so that
their cans cross; the shoulders moved out 7 each; the waist's yoke grew 12 longer; the
ankle's double-ended drive, which nobody makes, became one RS04 with one crank and one
rod; and the hips' toe-out became the coupled travel above. Covering them cost travel
too: the waist leans 15 degrees to a side, not 20, because the abdomen that hides its
drives has to clear the pelvis. The maker's own solids, in place of cans drawn from the
datasheet, then found five interferences the cans had hidden: a connector through the
hip's cap (the cap now stands on the cradle, slotted), a can 1 mm longer than its sleeve
in the upper arm, lobes through the pelvis's wall, a rear cover against the foot's stub,
and a connector against the shin's wishbone.

Where the 57.4 kg is: the chest 11.4 kg, each thigh 3.9, each shin 3.6, the pelvis 3.6,
each hip's yoke and cradle 4.3; the legs 28.2 kg in all, 11.0 kg of it below the knees.
The 33 drives are 23.7 kg of it.

### Skins

A skin is two layers over one lofted form (rows of superellipse sections, `lib/skin.py`).
The panel is pearl, 2.6 mm, the outside; it is cut into panels by regions drawn in a side
or front view. The liner is black, 1.8 mm, under all of it: where no panel lies it is the
outside, the under-body that shows at the flanks, between a leg's front and back plates
and in every shut line. The frame carries the liner on pads that grow to its inner
surface. No screw shows on a panel. What shows between the skins is black as well: the
drives' housings, and the frames, which are 7075 aluminium anodised black, so that a joint
reads as one dark mass and not as its brackets.

Its own marks, and there are few. Every hem is a shallow V: the breastplate's and the
back's over the waist, the abdomen's in the side view, the shin plates' over the ankle,
the thigh's raked top. The status light is let into the breastplate as a chevron on the
front hem's slope. The battery comes out through a hatch in the back, cut free by one
shut line whose lower edge runs parallel to the hem under it; the hatch carries three
vents, the nape's three again, and the robot's name, set in Inter and standing 0.35 mm
proud. And a hairline of champagne-anodised aluminium marks a few joints: a ring round
the neck on the chest's deck, the upper rim of each sleeve (upper arm and forearm), a
ring let flush into each hip cap's end, one round each knee's caps, the grilles at the
temples. Each is flush with what it sits in or lies clear of everything that moves, so
none of them costs travel.

A form that ends in a point (the helmet's crown, the toe cap's tip, the heel) is lofted
to that point and then mended there: the kernel's loft arrives at a point as a cusp a
millimetre high, or overshoots it and leaves a dimple, and rows added near the point make
its surface ring along the whole form. `geo.smooth_tip` drills the end out round its
axis and fills the mouth with a surface held tangent to the loft's own face
(`Face.make_surface_patch`: one of build123d's own calls, so the engine's memo keeps
the result; the same cap made with the kernel's classes directly cost every later
build two and a half minutes).

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
drive behind it; a slot round it lets the yoke's arm through. The hip's cap is a cup about
the pitch axis that stands on the cradle's cheek, over the pitch drive's can and, stepped
in, over its rear cover (the step is what lets the leg swing out under the pelvis),
slotted where the drive's connector stands out. The thigh's form is drawn close to what
it holds: 123 wide at the top, where the knee's drive sits outside the femur, squarer
there than below (a can seen end on fills a rectangle), and 98 at mid-thigh.

## Poses and motions

Configurations: `ready`, `stride`, `contrapposto`, `reach`, `wave`, `present`, `crouch`,
`bow`, `poise` (balanced on the left leg), `fists` and `rest` (asleep on its feet, the
head bowed). Motions: `walk` (one gait cycle of 2 s, the feet treading under a fixed
pelvis: heel strike, roll-over, heel-off on the toe hinge), `wave`, `bow`, `crouch`,
`reach`, `poise`, `look` and `grasp`, and the film's two: `wake` (from `rest` to `ready`)
and `settle` (from `ready` into `contrapposto`).

The pelvis is the mechanism's fixed link, and a robot on a floor is the other way round:
its feet stay and its pelvis moves. So the standing poses are written that way. `ready`
sets the stance (the feet 220 mm apart, turned out 7 degrees, the left 16 mm ahead), and
`rest`, `reach`, `bow` and `crouch` say where the pelvis goes over feet that have not
moved (`kin.standing` solves each leg's six joints for it: the knee from the triangle
hip, knee, ankle, the other five by Newton's iteration, to a nanometre). A motion that
moves the pelvis is a path of such poses, sampled ten times a second, because joints
eased one by one between two poses that keep the feet do not keep them on the way. The
squat was the lesson: `ready` balances by 77 mm and the old `crouch` did by 32, and the
path between them, each joint eased on its own, carried the hips three quarters of the
way back while the chest had leaned half of the way forward, and passed within 8 mm of
going over backward. In the simulation (`../sim/`) it went over. Now the hips go back
and down along a path the pelvis is given, the arms come out in front as a
counterweight, and the least margin of the whole motion is 62 mm, at the bottom. The
crouch is as deep as two limits allow with the weight over the middle of the feet: the
rear ankle is half a degree from its 30 of dorsiflexion and the hips two from their
100, the pelvis 325 mm down and tipped 26 degrees.

Where a foot is re-placed, the weight goes first. `poise` carries the pelvis 126 mm over
the left foot with both feet down, lifts the right foot straight up, sole level, and
folds the leg as it clears the floor; `settle` carries the weight over the right foot,
lifts the left 16 mm, sets it down 67 mm ahead and 48 mm nearer, and only then eases
into contrapposto and shares the weight out. The shift takes three seconds: while the
body is braked the floor's push stands ahead of the centre of mass, by the braking
times the height over gravity, and the foot it arrives over is 60 mm wide. In a second
and a half that lead is 30 mm and leaves the centre of pressure 11 mm inside the sole's
edge; in three it is 8 mm and leaves 19.

`checks/balance.py` holds every motion but the gait to all of this, followed in time on
the foot it never moves: a foot that is down does not move (the most is 0.05 mm, the
sampling's), no sole goes below the floor, the centre of mass stays at least 20 mm
inside what is down, and the centre of pressure (the links' weights and accelerations,
each link a point mass) at least 15. The squat's least are 62 and 60 mm, the bow's 76
and 62, the reach's 70 and 66; on one foot `poise` has 27 and 19 and `settle` 27 and 24.
What the checks do say is that a robot which follows the path exactly stands. What
they do not say is that drives will follow it. In the simulation every motion on two
feet is followed and stands (`../sim/README.md`), and the two that stand on one foot
are not: the loaded leg's servos give under the weight as it arrives (the leg 1.7 mm
short, the pelvis a degree over), the centre of mass ends 7 mm outside the ankle's axis
where the path has it 16 mm inside, and the ankle's roll drive, which steers the push
24 mm either side of its axis and no further, cannot make that up. With drives that
hold their angle under load (stiffer loops, or the load's torque fed ahead), an ankle
roll loop stiffer than the 484 N m/rad at which the robot topples over it, and half the
pace, the simulation does stand on one leg, with nothing in hand. Balance with feedback
is what would give it margin, and that is not in this model.

One thing moves that is not the mechanism's: `explode`, an animation of the GLB
(`cad.build123d.animation`, in `lib/show.py`), in two stages with a hold after each.
First the links go apart up the robot and each skin slides off what it covers; then
every piece goes off on its own, each part well away from its link's middle, the whole
wider than it is tall; and all come back. The document's joints and a STEP know nothing of it; the viewer's playbar and
`film.py` play it from the GLB. In a picture or a posed model the pelvis stays and the
feet move, as in the document; `stances.py` sets each posed robot back on the ground,
and `film.py` each frame.

## Source

| Module | What it holds |
| --- | --- |
| `lib/dims.py` | the skeleton in numbers: joint centres, axes and travel, linkage geometry, the actuators as their maker gives them, which drive turns which joint. No kernel |
| `lib/kin.py` | the joint tree, the couplings, forward kinematics, the leg's inverse kinematics, standing a pose on the ground, the limits a pose is held to. No kernel: poses, motions and checks compute with it |
| `lib/poses.py` | the configurations and motions, as numbers |
| `lib/finish.py` | the finishes: a `bd_materials` grade (or a homogenised density for an assembly the model does not open) and a scalar PBR look |
| `lib/geo.py` | the geometry vocabulary: superellipse sections, lofts (a pointed end mended by `smooth_tip`), plates from hulls of circles, turned parts; and four booleans (`common`, `cut`, `carve`, `fuse`) that refuse an answer the kernel got wrong, re-measuring by adaptive integration before they do |
| `lib/skin.py` | how a skin is made (a form at several insets, its panel and liner layers, regions drawn in a view), lettering, and the register of forms `fit.py` reads |
| `lib/kit.py` | parts, prototypes and their placements, groups, `mirror_tree` |
| `lib/hardware.py` | screw heads, the actuators (the maker's solids stood in a frame, and the envelopes the checks use for them), their mounting and output patterns, pivot caps, pushrods, pins |
| `lib/leg.py`, `torso.py`, `arm.py`, `hand.py`, `head.py` | the links, part by part, each with its skin |
| `lib/rig.py` | joints, couplings, configurations and motions, written on the assembled links |
| `lib/show.py` | the exploded view, an animation of the GLB: where each link, part and skin goes, and when |

## Checks

Each prints what it measured and exits non-zero when it fails. Those that need the
geometry read it as the engine exports it and pose it with `lib/kin.py`; none asks the
engine to move anything.

| Check | Asks | Result |
| --- | --- | --- |
| `drives.py` | do this robot's brackets meet RobStride's drives? On the maker's solids: every mounting screw over a tapped hole, no plate or hub in a drive, each envelope round its drive | they do, on the bench and for the 20 drives held by cap screws on the robot; the envelopes are 6 to 42 % larger than the drives they hold |
| `interference.py` | do two parts share volume? As built: inside every link and link against link | none in the 482 pairs near enough to measure, of 1,136 whose boxes meet |
| `interference.py --poses` | the same, link against link, at each configuration | none in the eleven configurations, 134 to 140 pairs measured in each |
| `interference.py --limits` | each control swept alone through its travel in eight steps, against the links within three joints of it | none: the 26 controls of the centre and the left side, which stands for the right |
| `interference.py --corners` | the joints that share a centre, moved together: waist, neck, hip, shoulder, wrist and ankle, each at every corner of its travel and the middle of every edge | none in the 104 poses |
| `interference.py --motions` | each motion at its waypoints and between them (`--motions crouch bow`: those) | none in the ten motions |
| `planted.py` | does that check find a plate planted through a 2.6 mm skin, clear one 0.3 mm from it, and pass a pin in its bore? | it does |
| `fit.py` | does each skin hold its mechanism with 3 mm of air, through the travel under it? | it does. The least air: 3.0 mm round the upper arm, 3.2 the pelvis, 3.3 the shin, 3.5 the chest, 4.0 the thigh, 5.3 the forearm, 15 the head |
| `attachment.py` | does every part touch another part of its own link, or else a part of a link it is jointed to (a pushrod on its pin)? | every part is held, six of them by a joint's pin alone |
| `balance.py` | is the centre of mass over the support polygon in each standing pose (heels and balls: the sprung toe carries nothing), and by how much? Can each motion be followed on a floor: do the feet that are down stay, and do the centre of mass and the centre of pressure stay over them? | standing straight 51 mm inside, ready 77, contrapposto 55, reach 70, wave 72, present 82, crouch 62, bow 77, poise 30 (on one sole), fists 77, rest 75; the stride is a gait frame. The nine motions that stand on a floor can be followed (above); the gait is trodden under a fixed pelvis |
| `linkages.py` | do the pushrods' far eyes stay on their pins through the travel, and do the axes that should meet, meet? | gaps under 1e-12 mm; hip, ankle, waist and shoulder axes meet exactly |
| `loads.py` | statics: the torque each drive holds in seventeen cases, four of them instants of a motion, against its rated and its peak torque; each pushrod's force against its Euler load | below |

How interference is judged. The verdict is the kernel's: two parts interfere when their
solids share more than 0.5 mm3 (`overlap_volume` on the model's own solids; parts that
only touch share none). The meshes only choose which pairs it is asked about, and choose
generously. A volume is believed when the pair gives it both ways round, because the
kernel's intersection has been seen to differ with the order of its two solids; when the
two differ, what a cut takes decides and the pair is named. A pair the kernel cannot
intersect is reported unmeasured, which fails the check. A drive is measured as its
envelope: plain cans, lobes and a sector for its connector, drawn round the maker's
solid, which `drives.py` holds to containing it. The maker's solid is one shrink-wrapped
skin of some 3,000 faces, and the kernel takes seconds to intersect anything with it;
the envelope answers at once, and errs toward finding an interference.

What holding asks (`loads.py`). A drive holds its rated torque for as long as one likes
and its peak briefly. A pose counts as held while every drive is within its rated torque,
and as held briefly while every drive is within 75 % of its peak.

- Standing straight asks 6 N m of each ankle; `ready`, `contrapposto`, `wave` and `rest`
  are within every rated torque. Contrapposto is at the edge of it: 34 N m at the stance
  hip's roll drive, 98 % of what an RS04 holds on the heat sink its bracket can be.
- Held briefly: the crouch (54 N m at the rear foot's knee and 49 at the other, 154 % of
  an RS04's rated torque and 45 % of its peak; 49 N m at the waist's pitch pair, 68 % of
  its peak, which the arms held out in front cost), the bow, standing on one leg (51 N m
  at the stance hip's roll drive, 145 % of rated, and 55 as the other foot leaves the
  floor), and the carried loads: 4 kg in each hand
  with the elbows square, 2.5 kg on each palm presented, 2 kg at the end of a reach, 1.5
  kg in each hand with the arms out level. The wrists (an RS05 gives 1.8 N m rated) and
  the waist's pitch pair are what limit them: a level palm carries about 1 kg for as long
  as one likes.
- Walking adds what a foot can lever. The whole weight on one forefoot is 66 N m at the
  ankle's pitch drive, 55 % of an RS04's peak, which is why that drive is an RS04 and not
  the RS03 first fitted (60 N m peak). The whole weight on one sole's edge would be 25 N m
  at the ankle's roll drive, and an RS00 gives 14: Galatea cannot stand on the edge of a
  foot. Its ankle steers the centre of pressure 24 mm either side of the roll axis, and
  balance sideways is the hips' work.
- The knee's pushrod (12 mm titanium, 280 long) buckles at 14.1 kN; the crouch pushes it
  with 1.2 kN, and the drive at its peak with the lever at its shortest with 4.7 kN: a
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
bare drives still showing behind the waist. And it is looked at close in a path tracer
before it is called finished (`film.py still`): the kernel's shaded stills had not shown
the pimple on the helmet's crown, the dimple in the heel or two open holes in the pelvis's
deck, and a render in Cycles showed all three at once.

## The film

`film.py` is the robot's film: a dark cove, a rig of lamps, the shots and the cut. It
renders the robot's GLB with Blender's Cycles (the `render` skill; `cad run` gives a
script that imports `bpy` its Blender), on the CPU where there is no GPU.

```
cad model export <id> GLB/galatea.glb --tolerance 0.08 --angle 8    # 78 MB; again after every change to the model
cad run src/film.py list                         # the cut: its pieces and their lengths
cad run src/film.py still knee 20 --draft        # one frame, 960 x 540, in a few seconds: framing and light
cad run src/film.py shot knee --preview --step 2 # a shot's motion, small and quick
cad run src/film.py shot knee                    # its frames, 1600 x 900, into tmp/film/knee/; kept, so a run can be resumed
cad run src/views.py                             # the plain CAD views, into tmp/film/views/
cad run sim/run.py --film crouch                 # the simulation's clip, tmp/sim/film_clip.mp4 (../sim/README.md)
cad run src/film.py take sim tmp/sim/film_clip.mp4   # its frames, into tmp/film/sim/
cad run src/film.py take end wake 22             # the end card: one rendered frame, held
cad run src/film.py cut                          # tmp/film/galatea.mp4 (needs ffmpeg)
```

The cut is 39 seconds, about the model being a CAD file and about its mechanism, and
gets inside it in three: it wakes; the camera goes round it and, in the same shot, the
whole assembly comes apart (the GLB's `explode`: links and skins, a hold, then all 689
pieces, a longer hold); then the mechanism with its skins left off, a joint at a time
as it moves (the knee's linkage, the ankle, the hip, the waist, the arm, the hand, the
neck and the head's cameras), and all of it crouching; the skins are wiped back on and
it walks; then the same document with no studio at all, as the CAD viewer draws it
(`views.py`: solid on the grid, parts exploded, the walk in x-ray); then the
simulation (`../sim/`): MuJoCo's own picture of the robot let go over a floor, landing
and squatting on its own feet, the floor's push drawn at its soles; the title.

What the script does that the GLB alone does not. The pelvis is the mechanism's fixed
link, so an exported clip crouches and treads in the air: `plant` moves the whole robot,
frame by frame, so that the foot it stands on stays where it is on the floor, and a walk
goes forward as fast as its feet go back. Camera points are written where the part they
look at stands at the zero pose and ride on a link, so a close-up finds its part in any
pose, and a target can follow a link through a shot. Three looks are changed for the
film's sake: the face shield is drawn as smoked glass (the GLB carries it opaque, and a
path tracer then shows nothing behind it), the two status lights are keyed, and for the
wipe every skin gets a shader that is clear above a height, with a lit edge. A cut's
piece is a list of a shot's frames, so a rendered shot can be used in part, faster or
backwards (the wipe is rendered taking the skins off and played putting them on). The
captions and the title are laid over by ffmpeg, so the words can change without a frame
being rendered again. A caption is a few words, because a close-up is on the screen for
a second and a half, and stands on a dark plate, because half the shots have a lit
floor where it stands and pale words are lost on it. A little grain is added last,
without which an 8-bit encoder turns the studio's dark gradients into bands.

On a machine with four cores and no GPU a frame takes 14 to 30 s at 14 to 20 samples
with the denoiser. Its picture has no texture in it, only flat looks and edges, which
is what the denoiser is best at: at 8 samples a frame is already hard to tell from one
at 24. EEVEE does not run there at all (it needs a GPU's context), so drafts are Cycles
too, at 960 x 540 and 10 samples, 4 to 10 s each.

## Not modelled

The inside of a drive (motor, gear set, bearings, encoder, driver: one homogenised
housing and cover), the cable harness, the finger tendons and their motors, the toe's
spring, bearings at the passive pivots (their caps are there), screw shanks and the
threads and holes they run in (heads only), the clips that hold a panel on its liner, the
battery's cells and the electronics' boards (blocks at a homogenised density), the
hatch's latches. The walk is a kinematic gait under a fixed pelvis, not a controller's:
`balance.py` and `loads.py` say what statics allow.

## Sources

- RobStride's repository of product information, with the STEP models, the manuals and
  the Product Specification of 9 October 2026: https://github.com/RobStride/Product_Information
  (`vendor.py` names the commit and each file's checksum).
- RobStride product pages, RS00 to RS06: https://www.robstride.com/products/robStride00
  (and `robStride03`, `robStride04`, `robStride05`, `robStride06`).
