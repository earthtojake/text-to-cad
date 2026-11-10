# Galatea in MuJoCo

The robot of `../src/` as a MuJoCo model, and what it does when the model's own motions are fed to
its drives under gravity, with its feet on a floor and nothing holding it. `build.py` writes the
model from the CAD model, `check.py` holds what MuJoCo compiled to the CAD model's own numbers, and
`run.py` simulates the motions, measures them and renders them.

The short of it: on position servos alone, with no balance controller, Galatea stands, lands from a
small drop, wakes, bows, waves, reaches, looks round, closes its hands and squats, and its feet stay
where they stand to a millimetre. It cannot stand on one leg that way. `poise` and `settle`, the two
motions that lift a foot, carry the weight over the other foot first and still fall over its outside:
one ankle's roll drive cannot keep the robot over itself without something that feels where the
weight is. Those two are shown twice, falling and with the pelvis held, and the gait held only.

This is the second run. The first, on the motions as they were first written, found three falls (the
squat, contrapposto, the one-leg pose) and two motions that dragged their feet over the floor (the
reach, the bow): each a path between two sound poses that a robot on a floor cannot follow. The
model's motions were rewritten for that (`../src/README.md`, "Poses and motions"). What the
simulation found the first time and what it finds now are both below.

| File | What it is |
| --- | --- |
| `build.py` | reads the CAD model and writes `galatea.xml` and `meshes/`: links, joints, couplings, inertials, servos, collision shapes, keyframes. `--poses`: the keyframes alone, from `lib/poses.py`, with no CAD model |
| `check.py` | the compiled model against `lib/dims.py` and `lib/kin.py`: mass, joints, couplings, forward kinematics; each motion's balance by geometry; whether it stands where it is put |
| `run.py` | the clips: simulates each, reports it, renders it with MuJoCo's own renderer, and cuts the clips together. `--film`: the showcase film's clip alone |
| `galatea.xml`, `meshes/` | what `build.py` writes: the MJCF (122 kB) and 270 OBJ meshes (26 MB). Build output, so Git ignores both |

```
cad run sim/build.py              # from models/galatea; half a minute while the engine holds the robot's document
cad run sim/build.py --poses      # only lib/poses.py has changed: the keyframes alone, written again. Two seconds, no CAD model
cad run sim/check.py              # ten seconds, no CAD kernel
cad run sim/run.py --dry          # simulate every clip and report: a quarter of a minute
cad run sim/run.py                # and render: half an hour on four busy cores with no GPU
cad run sim/run.py bow wave       # the named clips
cad run sim/run.py --cut          # the clips' videos as they are, cut together again
cad run sim/run.py --film crouch  # the showcase film's clip alone, tmp/sim/film_clip.mp4, from that motion
                                  # (the bow unless one is named): two minutes
cad run sim/run.py --film crouch --dry   # its report and no picture; --stills 0,70,119: those frames as PNG files
cad run sim/run.py --friction 1   # an experiment, reports only: another floor; also --stiffness 4, --still-legs
```

`build.py` calls the model, so it builds the robot first if its sources have changed since the engine
last built it: six minutes in an environment whose worker has not built it before, which may also cost
another session its warm worker. The poses reach nothing in `galatea.xml` but its keyframes, so when
`lib/poses.py` is all that has changed, `build.py --poses` writes those again and neither calls nor
imports the CAD model. It refuses a file whose joints or couplings are not `lib/kin.py`'s, and
`check.py` holds the rest of the file as before. `check.py` and `run.py` need only `galatea.xml`.
`run.py` starts a clip from a keyframe (`ready`, or `rest` for the motion that wakes it) and refuses
a file whose keyframe is not the pose as it is now; `check.py` says so of all twelve. The picture
needs an OpenGL context and ffmpeg. With no GPU, Mesa's software renderer serves through either of
two libraries: `apt-get install libegl1` (`MUJOCO_GL=egl`, what `run.py` asks for unless told
otherwise) or `libosmesa6` (`MUJOCO_GL=osmesa`). Without one, `run.py` still writes the simulated
trajectories and says that it drew nothing.

## What is modelled

- **Links.** The model's 73, each a body whose frame has its origin at the centre of the joint that
  carries it and stands parallel to the world at the zero pose, so no body is written with a rotation
  and a joint's axis is `dims.py`'s as it stands. The pelvis is the floating base (a free joint), its
  frame midway between the hip centres, 0.92 m over the floor. Metres, kilograms, seconds, radians.
- **Joints.** The 72 revolute joints of `kin.all_joints()`: centre, axis, travel. A joint's positive
  direction is the one `dims.py` names, the same on both sides.
- **Closed chains.** Each knee's and each ankle's linkage is a parallelogram, so its crank turns with
  the joint and its rod turns back by as much: two joint equalities at `kin.couplings()`'s ratios
  (1 : 1 : -1) close it. A finger's knuckles (85 : 100 : 70) and a thumb's (55 : 75) follow their first
  joint the same way. 26 equalities in all.
- **Inertials.** A link's mass, centre of mass and inertia tensor are summed over its parts as
  `checks/balance.py` weighs them: a part is its mesh's volume at its material's density, a drive is
  its maker's mass at the middle of its box (its own centre of mass lies up to 5.2 mm from there).
  A drive's tensor is that of the maker's solid at one density, which is how the CAD model carries it.
  57.38 kg; the build refuses a total more than a per cent from the 57.4 kg of `checks/balance.py`.
- **Servos.** One on each of the 44 driven controls, limited to its drive's peak torque
  (`dims.ACTUATORS`, `dims.DRIVES`; the waist's pitch pair to twice an RS06's). A knee's and an ankle's
  act on the pivot, which the linkage follows one to one. A servo's torque is
  stiffness x (angle wanted - angle) + damping x (rate wanted - rate): `run.py` feeds it the motion's
  angle and its rate, so a joint does not lag a moving target, only sags under its load. A motion
  given as a sampled path (ten poses a second, straight between them) is fed as the engine plays it,
  with a rate that goes smoothly through the samples: each step's own rate jumps at every sample, and
  would reach the servo as a blow ten times a second.
- **The toe.** A passive sprung hinge, 0 to 50 degrees.
- **Contact.** 64 boxes and capsules fitted to the parts' boxes at the zero pose: a box under each
  heel pad, ball pad and toe pad, boxes for the foot's shell, the toe cap, the hip, the pelvis, the
  abdomen, the chest, the shoulder, the wrist, the palm and the head, capsules for thigh, shin, upper
  arm, forearm and every phalanx. They meet the floor. The meshes collide with nothing.
- **The look.** Each link's parts are written as one mesh per finish, in the link's frame, with the
  finish's colour: pearl panels, the black under-body, frames and drives, steel, the champagne
  accents, the smoked face. MuJoCo's renderer shades by Phong's model, so `build.py` turns a finish's
  metalness, roughness and clear coat into a highlight's strength and width, and its transmission into
  transparency; the PBR values themselves are written beside them for a renderer that reads them. The
  drives' own solids are 83 % of the model's 2.55 million triangles: a mesh finer than a 5 mm mean
  edge is decimated to it, which leaves 413,000.
- **Keyframes.** `zero`, and each of the model's eleven named poses set on the floor as `stances.py`
  sets it, with the servos' targets.

## What is assumed

The CAD model does not hold these, so they are assumptions of the simulation, set at the top of
`build.py` and named in `galatea.xml`:

| What | Value | Why this |
| --- | --- | --- |
| a servo's stiffness | its drive's rated torque per degree of error: an RS04 2005 N m/rad, RS03 1203, RS06 630, RS00 286, RS05 103 | a stiff position loop: a drive sags a degree at its rated torque and reaches its peak at about three |
| a servo's damping | stiffness x 0.03 s | well damped on the links' own inertia |
| a rotor's inertia at its joint | RS04 0.040, RS03 0.018, RS06 0.010, RS00 0.0025, RS05 0.0006 kg m2 | the size a quasi-direct drive of each frame has; the maker's specification gives none |
| the hand's servos | 2 N m/rad, limited to 0.6 N m | the fingers' tendon drives and the thumb's opposition are not in the CAD model |
| the toe's spring | 20 N m/rad | stiff enough to carry the cap, soft enough for heel-off; the CAD model leaves the spring out |
| the floor's friction | 0.7 | TPU soles on a sealed hard floor |
| the time step | 1 ms | a contact's time constant is 5 ms |

## What is not modelled

- **A balance controller.** Each servo follows its own joint's angle and rate. Nothing reads the
  floor's reaction, the pelvis's attitude or the centre of mass, and nothing plans where a foot goes.
- **The linkages' loads.** The joint equalities move the cranks and rods; the servo's torque acts at
  the pivot, so no rod carries a force. `checks/loads.py` has the rods' forces.
- **Contact between the robot's own parts.** The collision shapes are boxes and capsules round whole
  links and would touch their neighbours at rest. The CAD model's own interference checks cover its
  motions; a fallen robot's limbs may pass through each other here.
- **A drive's limits beyond its peak torque:** its speed, its heating (a drive holds its rated torque
  for as long as one likes and its peak briefly; `run.py` reports peaks, and where a clip leaves a
  drive far over its rated torque the notes below say so), friction, backlash, the structure's
  stiffness.
- **The hand's grip.** The fingers close in the air.

## What the simulation found

`cad run sim/run.py` on the model's own floor (friction 0.7). A clip starts from a keyframe (`ready`;
`rest` for `wake`), stands 1.5 s unseen, and is fed its motion from 0.6 s on; times below count from
where the motion begins. Heights are the pelvis frame's, 907.5 mm in `ready` by the pose's geometry.

| Clip | Free-standing, it | Pelvis | Feet | Servos |
| --- | --- | --- | --- | --- |
| `ready` (let go 30 mm over the floor) | lands, settles, stands | lowest 905.7 mm, then 906.9; tilted 0.5 degrees back | 0.2 mm from where they landed | knees and the waist's pitch pair at their peak for 5 and 2 ms in landing; standing, knees 17 N m, waist 10 |
| `wake` | completes | from 916.3 mm in `rest` to 906.9, tilt at most 0.5 degrees | do not move | waist pitch 11.9 of 72 N m (17 %) |
| `bow` | completes | tilts 25.6 degrees (the pose: 24.0), ends at 0.7 | scrub 0.2 mm and do not turn; each bears 272 to 295 N throughout | waist pitch 43.3 of 72 N m (60 %), hips' pitch 30.5 of 120 (25 %), hips' yaw 0.7 of 36 |
| `wave` | completes | within 0.5 mm, tilt at most 1.5 degrees | do not move | waist roll 11.6 of 36 N m (32 %) |
| `reach` | completes | 904.0 to 907.0 mm (the pose: 904.5), tilt at most 1.0 degree | do not move (0.1 mm) | waist pitch 24.6 of 72 N m (34 %), hips' roll 2.2 of 120 |
| `look` | completes | still | do not move | knees 17.9 of 120 N m (15 %) |
| `grasp` | completes | still | do not move | knees 17.9 of 120 N m (15 %) |
| `crouch` | completes | down to 571.5 mm (the pose: 582.5), tipped 25.2 degrees (the pose: 25.8), back to 906.9 | scrub 1.1 mm; each bears 256 to 300 N throughout | waist pitch 51.9 of 72 N m (72 %), knees 57.6 of 120 (48 %), hips' pitch 34.9 (29 %) |
| `settle` | falls over the outside of its right foot: a hand meets the floor at 3.97 s | | the left off the floor from 2.67 s, a third of a second before the motion lifts it | the right ankle's roll drive at its 14 N m from 2.61 s |
| `poise` | falls over the outside of its left foot: a hand meets the floor at 3.63 s | | the right off the floor from 2.59 s, 0.4 s before the motion lifts it | the left ankle's roll drive at its 14 N m from 2.37 s |

Held (`settle_held`, `poise_held`, `walk_held`): the weld `hold_pelvis` on, the pelvis 0.1 m over
where it is at the zero pose, the feet in the air. The legs' linkages, the servos and gravity are the
same; the balance is the weld's. The two one-leg motions are held because free-standing they fall
(below), and held they can be seen whole, as they are written. The gait is held because it is a gait
under a fixed pelvis: its feet tread back under the pelvis and nothing carries the pelvis over a
foot, so there is no walk in it to stand on, and walking wants a controller this model does not have.
Held, nothing works hard: the gait asks 26 and 20 N m of the hips' pitch drives and 15 of the knees,
the one-leg pose 21 N m of the lifted leg's hip, contrapposto's step 16 N m of the stepping leg's.

The first run, on the motions as they were first written, is why the model's motions are what they
are now. Each paragraph says what the motion was, what the simulation found, what was changed in the
model, and what the simulation finds now.

**The squat.** `crouch` was two poses with each control eased on its own between them. Both balanced,
by 79 and 30 mm, and the path did not: half-way down the thighs had carried the hips three quarters
of the way back while the trunk had leaned half of the way forward, and by geometry alone the margin
was 8 mm at 1.25 s of the 2 s descent. In the simulation each joint also sags under its load, which
left the trunk more upright and the weight further back: the balls and toes bore nothing from 0.75 s,
the robot went over its heels, and its hip yokes were on the floor at 1.9 s. Servos four times as
stiff only delayed that to 2.3 s, and the floor's friction made no difference; released in the crouch
itself, the robot held it. So the pose was sound and the path was not. The squat is now a path the
pelvis is given, back and down over feet that stay where they stand, the arms out in front as a
counterweight, sampled ten times a second (`squat` in `lib/poses.py`). The crouch at its end is 79 mm
less deep, the pelvis 582 mm over the floor where it was 504, and tipped 26 degrees. Its least margin
by geometry is 64 mm, at the bottom (check 7). The simulation follows it down and back up. The pelvis
reaches 571.5 mm, 11 mm under the pose, because the knees give 1.7 degrees under 57 N m and the waist
2.4 under 52; the feet scrub 1.1 mm; each foot bears 256 to 300 N throughout and the balls and toes
never less than 15 % of the weight; the hardest-worked drives are the waist's pitch pair at 72 % of
their peak, which is what the arms held out cost, and the knees at 48 %. Released in the crouch it
stands (check 8).

**The reach.** The pose also re-placed the feet, 62 mm each fore and aft and 29 mm each inward, and
the motion brought them back. Under a fixed pelvis a foot slides there. On the floor they scrubbed 64
and 52 mm and did not come back: they ended 93 mm closer together, each hip's roll servo left pushing
103 and 95 N m against the floor's friction (105 at the most, 88 % of an RS04's peak and three times
its rated torque). With the legs' controls left at `ready` the same reach was clean. Now the feet
stay, and the pelvis goes 10 mm forward and turns 4 degrees with the chest (`reach`). The feet move
0.1 mm, the hips' roll drives hold 2.2 N m at the most, and the hardest-worked drive is the waist's
pitch pair at 34 % of its peak.

**The bow** had the same trouble in small. The pose turned the feet from 7 degrees out to straight
and brought them 29 mm in; the floor let them turn 2.8 and 1.8 degrees, they scrubbed 7 and 15 mm,
the hips' yaw drives reached 75 % of their peak pushing against it (26.9 of 36 N m), and on the way
up the right foot bore nothing for an instant. Now the hips ease 87 mm back over feet that stay as
the chest goes forward (`bend`). The feet scrub 0.2 mm and do not turn, each bears 272 to 295 N
throughout, and the hips' yaw drives hold 0.7 N m. The weight still travels along the feet as the
hips start and stop, the balls and toes carrying 95 % of it 1.1 s in and the heels 90 % as the robot
comes back up, and neither sole leaves the floor.

**Contrapposto.** The pose stands the left foot ahead of the right and nearer to it than `ready`
does. `settle` eased every joint there with both feet down: on the floor both scrubbed (40 and 58
mm), the left came off at 2.7 s, the whole weight stood on the right foot, and the robot was down at
4.6 s. On floors of friction 0.4 and 0.5 the same motion completed, so the outcome turned on how two
loaded feet happened to scrub. Now the weight goes first: the pelvis is carried over the right foot
in three seconds, the left foot is lifted 16 mm, carried 67 mm ahead and 48 mm nearer and set down,
and only then does the pelvis ease into the pose (`settle`). By geometry the centre of mass is never
less than 31 mm inside what is down (check 7). The robot still falls, and now for one reason alone,
which it shares with the one-leg pose: the left foot is off the floor from 2.67 s, a third of a
second before the motion lifts it, the right ankle's roll drive is at its limit from 2.61 s, and a
hand is on the floor at 3.97 s.

**One leg.** In `poise` the right foot began to lift with the motion's first instant, while the hip
that carries the weight across was still on its way. By geometry the centre of mass was 34 mm outside
the left sole 0.9 s in, with the right foot already off the floor, and the robot fell toward the foot
it had lifted, a hand on the floor at 1.7 s. Now the pelvis is carried 126 mm over the left foot
first, with both feet down, in three seconds; then the right foot is lifted straight up, its sole
level, and the knee folds as it clears (`poise`). By geometry the least margin is 29 mm, on the one
sole (check 7). The robot now falls the other way, over the outside of the foot it stands on: the
right foot bears nothing from 2.2 s and is off the floor for good from 2.59 s, 0.4 s before the
motion lifts it, the left ankle's roll drive is at its limit from 2.37 s, and a hand is on the floor
at 3.63 s.

**Why a path does not keep it on one foot.** Sideways, all that holds the robot over one foot is that
ankle's roll drive. It is an RS00: at its peak, 14 N m, it carries the 56 kg that stand on it with
their weight no further than 25 mm from its axis. And a position servo is a spring. The one assumed
here is as stiff as its drive's rated torque per degree, 286 N m/rad (What is assumed), and that
mass, its centre 0.85 m over the axis, topples at 470 N m/rad: over one ankle the robot is a pendulum
stood on its head on a spring too soft to hold it, whatever torque the spring has. So as the weight
arrives the ankle gives, the lean carries the weight further out, and nothing answers. In `poise` the
left ankle has given 1.1 degrees by 2.0 s, which is 16 mm at the centre of mass, and 1.8 by 2.2 s,
when the right foot has already come unloaded; at 2.4 s the drive is at its limit and the centre of
mass 29 mm outside its axis. `settle` goes the same way over its right foot.

Stiffer servos get further and not there (`--stiffness 4`: 1146 N m/rad at that ankle, more than it
topples at). `poise` then arrives over its foot, lifts the other at 3.2 s as it is written, and
stands on one leg. It sways 14 mm inward as the knee comes up, the roll drive at its limit that way,
then outward, the drive at its limit the other way from 4.9 s; at 5.2 s the weight is 25 mm outside
the axis and still going, and a hand is on the floor at 7.1 s. `settle` makes its step in the air and
comes down on the stepping foot at 3.9 s, 0.2 s early and with 167 N, which pushes it over the other
foot; it is down at 5.3 s. Nor is it the pace. The rewrite first took 1.5 s over the shift, which by
the model's own check put the centre of pressure 11 mm from the sole's edge, and the simulation fell
at 2.4 and 2.6 s. At 3 s that check has 19 mm for `poise` and 24 for `settle`, and the simulation
falls 1.3 and 1.4 s later, no more.

So `checks/balance.py` is right that the path can be followed, and it can be only by a robot that
corrects its lean as it goes: one that measures where the floor pushes, or how its pelvis leans, and
drives the ankle and the hip from that. That is balance feedback, which neither the CAD model nor
this simulation has. Until one of them does, these two motions are shown held, and the free-standing
clips show what happens without.

What the first run's three falls and two scrubs shared: the poses were written with the pelvis fixed
and the feet free, which is right for a document's mechanism and for a picture, and a robot on a
floor is the other way round. The rewrite turned them round: poses that say where the pelvis goes
over feet that stay, paths sampled so that the feet stay on the way, a foot lifted only once the
weight has left it, and a check that follows every motion in time. What is left is what no path can
do.

## Checks

`cad run sim/check.py`, every line `ok`:

1. **The model.** 73 links and 72 revolute joints, the joint tree's; one free joint; 26 joint
   equalities for the 14 couplings; 44 servos for the 44 driven controls; the weld `hold_pelvis`
   inactive as compiled. Its twelve keyframes are the zero pose and the eleven poses of
   `lib/poses.py` as they are now: a file written before the poses last changed fails here, and
   `build.py --poses` mends it.
2. **Mass.** 57.38 kg against the 57.4 of `checks/balance.py`; the heaviest links are the chest
   11.43 kg, a thigh 3.86, the pelvis 3.60, a shin 3.59, as there. The centre of mass at each of the
   twelve poses, set on the floor as that check sets it: zero (0.0, 19.0, 929.4), ready (0.2, -4.5,
   921.9), crouch (-26.5, 28.5, 674.0), bow (-31.1, -8.8, 875.9), poise (-11.8, -28.4, 948.1) mm, and
   the other seven. (The crouch and the bow are set flat on the left foot where the zero pose stands
   it, and their feet stand where `ready` has them, 29 mm further out and turned 7 degrees: that is
   their 27 and 31 mm to the right, not a lean.) At the first run all twelve were that check's own
   printout to the 0.1 mm it prints. `rest`, `reach`, `bow` and `crouch` have been rewritten since,
   and theirs here are this check's numbers alone, by the same masses and the same kinematics (check
   6). The margins count the heels' and the balls' boxes, as that check now counts support (the toe is
   sprung and carries nothing while the foot is flat): zero 49.0, ready 79.1, crouch 64.1, bow 82.9,
   reach 75.4, poise 36.5 mm, where that check has 51, 77, 62, 77, 70 and 30 on its sole points. A
   box has corners where a pad is round, and is as wide at its back as at its front.
3. **Joints.** All 72 centres within 3e-5 mm of `dims.py`'s, axes exact, travel within 3e-7 degrees.
   For instance `l_knee_rod` at (82.0, 25.4, 731.2) about +X from -125 to 0, `r_hip_roll` at
   (-82.0, 0.0, 920.0) about +Y from -20 to 16, `r_thumb_opp` at (-212.0, -40.0, 826.0) about +Z from
   0 to 80.
4. **Couplings and servos.** Every coupled joint follows its coupling's first joint at
   `kin.couplings()`'s ratio, to 5e-12; every drive's servo is limited to its drive's peak: 8 RS04 at
   120 N m, 2 RS03 at 60, 8 RS06 at 36 and the waist's pair at 72, 6 RS00 at 14, 7 RS05 at 5.5.
5. **The soles.** At the zero pose the six boxes' undersides are on the floor, to 1e-4 mm. The left
   heel's is x 53 to 113, y -18 to 68 mm; the ball's x 44 to 126, y -110 to -25; the toe's y -173 to
   -127; `kin`'s sole points span x 44 to 126, y -176 to 70.
6. **Forward kinematics.** At the zero pose and the eleven named poses, all 73 links stand where
   `kin.link_transforms` puts them, within 3.3e-5 mm and 1e-15 of a rotation matrix's entry. In the
   crouch the right palm's frame is at (-264.026, -535.712, 1326.075) mm and the left foot's at
   (111.310, -402.934, 567.756) by both, the pelvis where it is at the zero pose.
7. **Each motion's margin by geometry**, the pose fed at each instant set flat on the foot it stands
   on, the support its heels and the balls of its feet: wave 73.6 mm at the least, bow 79.1, reach
   75.4, look 78.8, grasp 78.9, wake 77.0, crouch 64.1 (at the bottom), settle 30.6 (at 3.32 s, on
   the right foot alone), poise 29.2 (at 3.48 s, on the left foot alone), walk -73.6 (a gait under a
   fixed pelvis). At the first run this line had the squat at 8.2 mm (at 1.25 s) and the one-leg pose
   at -34.1 (at 0.91 s). A report, not a verdict: `checks/balance.py` is the model's own verdict on
   the same question, on its sole points and with the centre of pressure beside the centre of mass
   (`../src/README.md` has its numbers), and for what the drives make of it the simulation has the
   last word, above.
8. **Standing where it is put.** Released at `zero` it holds 6.6 N m at each ankle (the statics of
   `checks/loads.py`: 6; it leans 0.5 degrees back on its servos). In `crouch` 51.4 N m at the left
   knee, 49.7 at the waist's pitch pair and 32.6 at the left hip (the statics: 49 at that knee, 49 at
   the waist), 11 mm lower and 0.7 degrees more upright than the pose. In `ready`, left 30 s, the
   feet move 0.08 mm after the first second. It stands where it stood if after the first second its
   feet move less than 1 mm and its pelvis less than 5, and its pelvis is tilted within 5 degrees of
   what the pose itself tilts it.

## The picture

MuJoCo's own renderer (4.0.0, the classic one), offscreen, 1600 x 900 at 24 frames a second, through
EGL on Mesa's llvmpipe: no GPU, 0.8 s a frame beside another render. A dark floor with no highlight,
in a backdrop of the lit floor's own colour so that no horizon shows; three lamps, of which the key
casts the shadow; the floor mirrors a little. The camera goes a few degrees round the robot in each
clip. `run.py` darkens the corners when it encodes, and writes `pelvis held over the floor` into the
picture of every clip that is, so that the label cannot be lost from the file. `galatea-sim.mp4` adds
three lines to each clip: the motion, what it shows, and how the robot stood for it, a fall's time
taken from the simulation.

**The film's clip** (`cad run sim/run.py --film`, `film_clip.mp4`) is for the showcase film, and is the
same simulation drawn so that it reads as one. It is exactly 120 frames, five seconds, with nothing
written on it and no darkened corners. The robot is let go 30 mm over the floor and lands; from 0.8 s
it performs one motion, free-standing: the bow unless another is named (`--film crouch`; any motion
but the gait, which is shown held and labelled or not at all). It is let go in the pose its motion
begins from: `rest` for `wake`, `ready` for the others. A motion longer than the 4.2 s that leaves has
its hold played shorter, down to 0.2 s (the squat's 5 s fits so), and what is still too long ends with
the clip; a robot that falls is shown falling to the clip's end. The camera stands at chest height,
three quarters in front, and goes six degrees round; the robot is in the middle and 0.8 of the picture
high, and the lower left is left to the floor, for the film's own caption. What makes it a simulator's
picture:

- **A grid on the floor**, a line each 100 mm and a heavier one each 500 mm, a crossing at the world's
  origin between the feet. The heavy lines are in the floor's texture and run to the horizon; near the
  robot both are drawn again as lines a pixel or two wide, fading by 2.6 m, because a texture seen from
  chest height does not hold a 100 mm line.
- **The floor's push**, as MuJoCo itself draws it (`mjVIS_CONTACTFORCE`, `mjVIS_CONTACTPOINT`): an arrow
  at each point of contact, 0.30 m for 35 N. That is a sixteenth of the robot's weight, nearly all of
  which stands on the sixteen lower corners of its heel and ball pads' boxes, so standing still those
  arrows are 0.2 to 0.4 m. The landing is one frame of arrows taller than the picture: the soles bear
  3.6 kN in that frame, six and a half times the weight, and the weight alone in the next. Each frame
  is drawn from the simulation's whole state at its instant, so the arrows are the forces the
  simulation had. (MuJoCo draws an arrow at half the length its own scale gives: `run.py` allows for
  it.)
- **The centre of mass**, as a ring with a cross through it on the floor under it.

`film_clip.json` is the clip's report, as `run.py` says it, and `film_clip.npz` its trajectory. The
clip there now is the squat (`--film crouch`): the robot lands, goes down to 571.6 mm and comes back
up on feet that scrub 1.4 mm, the hold at the bottom played 0.8 s shorter so that the whole of it
fits.

In `tmp/sim/`, which Git ignores:

| File | What |
| --- | --- |
| `<clip>.mp4` | the thirteen clips: `ready`, `wake`, `bow`, `wave`, `reach`, `look`, `grasp`, `crouch`, `settle`, `settle_held`, `poise`, `poise_held`, `walk_held` |
| `galatea-sim.mp4` | the thirteen in a row, captioned, 80 s |
| `film_clip.mp4` | the film's clip: let go 30 mm over the floor, the landing, then one motion (the bow unless another was named), free-standing; 120 frames, nothing written on it |
| `film_clip.json`, `film_clip.npz` | that clip's report and its trajectory |
| `<clip>.npz` | the clip's state at 24 frames a second (`qpos`, with the joints' names) and what was measured at 100 Hz: the pelvis's height and tilt, the centre of mass, the floor's push on each of the soles' shapes, every servo's torque and error |
| `report.json`, `report.txt` | every clip's numbers, and the same as `run.py` says them |
