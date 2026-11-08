# WidowX AI (follower): Trossen's STEP to a MuJoCo description

`src/wxai.py` reads `upstream/wxai/wxai_follower.step` and returns the articulated arm. Its `__main__`
builds the arm and writes `out/wxai/wxai.xml`, `wxai.urdf` and `wxai.sdf`, with meshes beside them.
The axis and travel measurements are in `src/lib/step_axes.py`. Every number in the model comes from the
STEP's geometry or from Trossen's published specification. The model uses only the official link and
joint names and the sign conventions of Menagerie's `trossen_wxai` and Trossen's URDF.

## The STEP

The file was exported from Fusion ("Autodesk Translation Framework", AP214, 2025-07-01). It has 15
top-level occurrences, one per link, and each one is a simplified "dummy" B-rep. Every part is a closed
solid (link_2 is a compound of 3 solids). OCCT flags link_3's solid as invalid, but it measures fine.

| occurrence | what it is | link | volume (cm^3) | area (cm^2) |
| --- | --- | --- | --- | --- |
| `base_link dummy:step:1:1` | base and joint_0 actuator, filled | base_link | 190.0 | 233 |
| `link_1 dummy.step:1` | shoulder yoke | link_1 | 68.1 | 241 |
| `link_2 dummy.step:1` | upper arm (3 solids, **no material**) | link_2 | 733.1 | 760 |
| `link_3 dummy.step:1` | forearm | link_3 | 470.1 | 598 |
| `link_4 dummy.step:1` | wrist pitch body; its motor can stands up | link_4 | 220.8 | 333 |
| `link_5:1` | wrist yaw body | link_5 | 160.9 | 221 |
| `link_6 standard dummy.step:1` | wrist roll and gripper body: rails, end stops, motor | link_6 | 255.2 | 393 |
| `gripper_leader_right:1` / `:2` | linear-guide carriage with a rack arm across (`:2` is turned 180 deg about X, at +Y) | carriage_right / carriage_left | 13.7 each | 61 |
| `103107032_01.step:1` / `103107033_01` | fingers, +Y / -Y | carriage_left / carriage_right | 24.8 each | 87 |
| `gripper sock left/right.step:1` | fingertip pads, touching at Y=0 | with their finger | 3.6 each | 48 |
| `camera mount dummy.STEP:1` (nested `103107027_01`) | saddle plate clamped on link_6 (**no material**) | link_6 | 11.5 | 64 |
| `103107028_03 v2:1` | D405 shroud, tilted 20 deg (3 shells). The camera itself is **not** in the STEP | link_6 | 29.5 | 150 |

All 15 parts total 2223.5 cm^3. Every part's material is "Steel" (7850 kg/m^3 declared) except link_2
and the saddle, which have none. In both cases that is a CAD default, not the real material.

**Pose.** Every part stands at the zero pose that Menagerie and Trossen's URDF use (the arm folded back
over itself, the driver's sleep pose), and the gripper is closed with its pads touching. So the STEP pose
IS the simulator's zero. No part is rotated, and every link placement sits on its joint, to the
0.01 mm: link_1 at z = 57.25, joint_1 at (20, 0, 103.5), joint_2 at (-244, 0, 103.5), joint_3 at
(1, 0, 163.5), joint_4 at (68.75, 0, 209) and joint_5 at (97.7, 0, 163.5). The exception is link_4,
whose placement is at (1.07, 0.02, 163.90).

**Interference as drawn** (`lib/step_axes.overlap`):

| pair | interference (mm^3) |
| --- | --- |
| link_2 / link_3 | 264 |
| link_3 / link_4 | 16 (the 0.4 mm offset) |
| link_6 / saddle | 1514 |
| each carriage / link_6 | 644 (its rack runs inside the dummy housing) |
| finger / pad | 55 |

These overlaps double-count about 3 cm^3 of mass, which is under 0.2 %.

## Joints from geometry

**Method** (`lib/step_axes.shared_axis`). List each part's cylindrical faces by the line they turn
about. A joint is the line that the parent and child both have bearing faces about (at least 50 mm^2
each, parallel lines within 1 mm). The occurrence origin is the hint used to choose among candidate
lines, and the along-axis anchor is that origin projected onto the line.

**Cross-check.** The two methods agree as follows:

| joint | bearing line (parent radii / child radii, mm) | occurrence origin from the line |
| --- | --- | --- |
| joint_0 | Z through (0, 0): base 28.5, 18.5 / link_1 17.5 | 0.000 mm |
| joint_1 | Y through (20, 103.5): 11, 17.5 / 17.5, 18.5, 28.5 | 0.000 mm |
| joint_2 | Y through (-244, 103.5) | 0.000 mm |
| joint_3 | Y through (1.0, 163.5) on link_3 | link_4's own bore and origin are at (1.065, 163.897): **0.40 mm** off |
| joint_4 | Z through (68.75, 0) on link_5 | link_4's bore is at (68.815, 0.017): 0.07 mm off |
| joint_5 | X through (y 0, z 163.5): 28.5, 22.5, 17.5 / 28.5, 21.5, 16.75 | 0.000 mm |

link_4 is the only part that is off the chain: it sits 0.40 mm high against both its bearings. joint_3
therefore takes link_3's bore and joint_4 takes link_5's bore, which are the lines that the
neighbouring parts agree on. link_4 stays where the STEP has it, and its visual is offset 0.4 mm in the
MJCF.

**Slides.** `lib/step_axes.free_directions` moves each carriage 2 mm along each candidate direction
against link_6. Its interference changes by 34 mm^3 along Y, 427 mm^3 along Z and 937 mm^3 along X, so
the slide is Y. The anchor is the carriage's occurrence origin (y = +-22.81). Menagerie's carriage
anchor is at y = 23.00, so its zero is 0.19 mm more open.

**Signs.** The CAD fixes the line of each joint, not its sign.
- joint_0, joint_3, joint_4 and joint_5 have symmetric ranges, so their signs are a convention. The
  model uses Trossen's, so values compare by name.
- joint_1 (0..180) and joint_2 (0..135) are asymmetric from a folded zero, so the geometry decides
  their signs. +Y lifts link_2, and -Y unfolds link_3 upward. The opposite sign drives each link
  through the one below it.
- On the carriages, positive opens, because they are closed at zero.

**Result in MuJoCo at qpos0** (world, vs Menagerie): all six hinge anchors and axes are identical to
0.00 mm and 0.000. The only deviation is joint_3's anchor, which is 0.02 mm off in Y along its own
axis, so it does not matter. The slide axes are identical too. The carriage frames sit 8.5 mm from
Menagerie's along X, which does not matter for a slide.

## Limits

The revolute limits come from Trossen's WidowX AI specification,
<https://docs.trossenrobotics.com/trossen_arm/main/specifications/wxai.html> (read 2026-11-08):

| joint | range (deg) |
| --- | --- |
| joint_0 | -180..180 |
| joint_1 | 0..180 |
| joint_2 | 0..135 |
| joint_3 | -90..90 |
| joint_4 | -90..90 |
| joint_5 | -180..180 |

The v1.5 page (<https://docs.trossenrobotics.com/trossen_arm/v1.5/specifications.html>) says +-175
for joint_0 and 0..270 for joint_2. Menagerie uses +-175 and 0..135.

The gripper limit was measured on the CAD: `wxai.measure_gripper()` runs
`lib/step_axes.free_travel`, which sweeps each carriage with its finger and pad along its slide against
link_6. The interference stays flat (the rack slides in its channel) until the carriage reaches the
rail's end stop at **22.0 mm** per side, and the result is the same on both sides. The sweep takes 66 s
of booleans, so the model holds the number with this citation instead of running the sweep.

- 2 x 22 = 44 mm between the fingers, which matches v1.5's "gripper stroke 0.044 m". The current page
  says 0.04 m.
- Trossen's URDF and Menagerie give each carriage 0..0.044 (Menagerie -0.01..0.045), which is twice
  what the CAD allows. It looks like the URDF took the spec's stroke as each carriage's travel.
- The closing limit is 0, where the pads touch: in the STEP, the fingers alone collide at 3 mm of
  closing.

**Self-collision check** (MuJoCo hulls, sweeping each joint alone from shoulder 90 / elbow 90): joint_0,
1, 2 and 5 are free over their whole spec range. joint_3 at -85..-90 brings the link_3 and link_5 hulls
together (Menagerie excludes this pair). joint_4 at its +-90 ends brings link_6's hull (its rails and
end stops reach +-90 mm in Y) 3.5 mm into link_4's hull. Both are hull effects at the range's ends.

## Mass: the main finding

The dummies are filled envelopes, so their volume says nothing about the hollow castings and dense
motors inside. The table compares each approach per link, against Menagerie (that is, Trossen's URDF).
Menagerie's link_6 is shown with camera_mount_d405 (0.600 kg), and its carriage with its finger
(0.081 kg). Ratios are ours / reference.

| link | reference | A: STEP steel, as declared | A': as the engine reads it | B: aluminium + plastics, unscaled | C: one density, scaled to 4 kg | **D: plain parts + one effective link density (shipped)** |
| --- | --- | --- | --- | --- | --- | --- |
| base_link | 0.460 | 1.491 (3.2x) | 0.0015 | 0.513 (1.12) | 0.342 (0.74) | **0.345 (0.75)** |
| link_1 | 0.153 | 0.535 (3.5x) | 0.0005 | 0.184 (1.20) | 0.123 (0.80) | **0.124 (0.81)** |
| link_2 | 1.153 | 0 (no material) | 0 | 1.979 (1.72) | 1.319 (1.14) | **1.329 (1.15)** |
| link_3 | 0.687 | 3.691 (5.4x) | 0.0037 | 1.269 (1.85) | 0.846 (1.23) | **0.853 (1.24)** |
| link_4 | 0.458 | 1.733 (3.8x) | 0.0017 | 0.596 (1.30) | 0.397 (0.87) | **0.400 (0.87)** |
| link_5 | 0.367 | 1.263 (3.4x) | 0.0013 | 0.435 (1.18) | 0.290 (0.79) | **0.292 (0.80)** |
| link_6 + camera mount | 0.600 | 2.235 (3.7x) | 0.0022 | 0.751 (1.25) | 0.533 (0.89) | **0.525 (0.87)** |
| carriage + finger + pad | 0.081 | 0.330 (4.1x) | 0.0003 | 0.066 (0.82) | 0.076 (0.93) | **0.066 (0.82)** |
| **total** | 4.040 (4.111 with the D405) | 11.61 (17.4 with link_2) | 0.0116 | 5.86 | 4.00 | **4.00** |

- **A (the STEP as given)** is useless. Everything is "Steel" at 3 to 5x the reference, and link_2 and
  the saddle are massless. Worse, text-to-cad reads Fusion's 7850 kg/m^3 as 7.85 kg/m^3 (A', see
  Gaps), so the as-read arm weighs 12 g.
- **B (plausible catalogue materials on filled dummies)** is 45 % heavy overall and 1.7 to 1.85x on the
  long, hollow, pocketed arm links. Menagerie's meshes show the X-ribbed pockets that the dummies fill.
- **C and D** use the spec's 4 kg ("Weight 4 kg", same page as the limits), taken as everything in the
  STEP: the arm and gripper, without the D405.
  - D gives the plain parts their catalogue materials: aluminium carriages and saddle, PA12 fingers,
    TPU pads, an ABS shroud (0.195 kg in all). The seven actuated links share the rest as one
    effective density of **1813 kg/m^3**.
  - C and D are within 1 % of each other per link. The total is right by construction.
  - Per link, the error is -25 % to +24 %, with a geometric-mean error of 22 %.
- The reference implies **1460 to 2420 kg/m^3** per link: dense where the big motors sit (base 2420,
  link_5 2280, link_1 2240) and light on the long hollow links (link_3 1460, link_2 1570). No uniform
  rule can give that spread from envelope solids.
- **Area weighting** (mass proportional to surface area, thin-walled housings) was tried too. It is
  worse, with a 41 % geometric-mean error, because link_1 is a thin yoke with a large area. The missing
  information is where the motors are, which a dummy STEP does not carry. The next refinement would
  put each actuator's datasheet mass at its joint and spread the rest over the shell area. Trossen
  does not publish its actuators' masses.
- **Centres of mass** (world, qpos0, D vs reference) are within 2.7 to 6.2 mm for every link but
  link_3, which is 16 mm off: its mass sits at the elbow motor, and the dummy has it spread along the
  bar.
- **Principal inertias** are 0.55 to 0.95x the reference for the arm links: uniform density in an
  envelope puts too little mass at the joint ends. The carriages are 2 to 4x, because their rack arm
  spreads mass across the gripper.

## Collision

Every part is a mesh, which MuJoCo collides as its convex hull. The dummies are already blocky convex-ish
envelopes, so a hull is close for most of them. A primitive fitted to the oriented bounding box is worse
for the L-shaped and yoke links.

Two hulls are poor:
- link_6's hull spans the rails and end stops (+-90 mm in Y), so it fills the gripper's throat behind
  the fingers.
- link_2's hull fills the step under its shoulder end.

Menagerie decomposes both into 3 to 5 convex pieces. text-to-cad would need the part split into convex
parts in the model.

The **carriages collide as nothing**. Each one's rack arm reaches across, so the two hulls overlap by
18.5 mm as built and would jam the gripper. The fingers and pads carry every grasp contact.

Two pairs still touch at rest. In both cases the solids do not touch; only the hulls do:
- base_link / link_1, by 3 mm. MuJoCo does not filter this pair because base_link is welded to the
  world.
- link_2 / link_5, by 1.4 mm in the folded pose.

Menagerie excludes base_link/link_1 and link_3/link_5 by hand. Here that is the scene's `<exclude>`,
which text-to-cad cannot declare (Gaps).

## Frames and states

- **`ee_gripper_link`** (site on link_6): on the roll axis (joint_5), at the fingertips' far end (the
  pads' extreme X, 253.48 mm). The pads' and fingers' occurrence frames sit there too. Menagerie's site
  is at 253.76, a 0.28 mm difference.
- **`camera_link`** (site on the shroud, in link_6): the shroud's two r1.62 screw holes for the camera
  are the only tilted cylinders. They give the optical axis direction, (0.940, 0, -0.342), which is 20
  deg down. Midway between them is a line on it, and the frame stands where that line leaves the
  shroud's front, at (162.8, 0, 215.7).
  - Menagerie's camera_link has the same direction, at (156.4, 9, 217.8).
  - Its y = 9 is the D405's left-imager offset. Along the look direction the two differ by 6.5 mm:
    shroud front against camera origin.
- **States:** only `gripper_open` (both carriages at the measured 22 mm), which follows from the
  limits. No `home` state: Menagerie's keyframe comes from system identification, and Trossen's docs
  give no home pose I could cite.

## Gripper coupling

text-to-cad cannot couple two prismatic joints. `rack_and_pinion_pair(asm, "grip", left=1, right=1)`
fails with "rack and pinion pair 'grip' of slides drives 'left' and 'right', both prismatic: a rack and
pinion pair relates its first joint, 'left', to joints of the other kind". `gear_pair` fails with "...
drives the prismatic joint 'left': a gear pair turns revolute joints". The two slides are therefore
independent joints (2 controls where Menagerie has 1 plus an equality).

**Workaround tried and working** (`tmp/wxai/couple_test.py::pinion_racks`, not shipped): the real
mechanism is one pinion driving both racks. The v1.5 page gives its pitch radius as 0.00875 m in the
gripping-force formula.

- A revolute `pinion` joint plus `rack_and_pinion_pair(asm, "gripper", pinion=1, left=0.15272,
  right=0.15272)` exports `<equality><joint joint1="left" joint2="pinion" polycoef="0 0.00875 ..."/>`
  for both racks. The URDF gets matching `<mimic>`s.
- It was not shipped because it needs a pinion part that the STEP does not draw (the "no helper
  joints" rule), and it adds a control joint that Menagerie and the URDF do not have.

## Validation

- `cad mjcf validate out/wxai/wxai.xml --compile required`: OK. It compiles under MuJoCo 4.0.0 with 9
  bodies, 8 joints, 28 geoms, 14 meshes and 1 key; the moving mass is 3.656 kg (4.000 with the base).
  - One warning, `contacts_at_rest`: the base_link/link_1 and link_2/link_5 hulls (above).
  - Info notes: pyramidal cone and default solref (the consumer's choice), and no `home` key.
- `cad urdf validate out/wxai/wxai.urdf`: OK. Root base_link, 11 links, 10 joints (8 movable), total
  mass 4 kg.
- `cad sdf validate out/wxai/wxai.sdf`: OK. 9 links, 9 joints; `collision_reuses_visual_mesh`
  warnings; `gz` is not installed.

## Snapshots

- `out/wxai/wxai.png`: the qpos0 (sleep) pose.
- `out/wxai/wxai_pose.png`: joint_0 30, joint_1 60, joint_2 60, joint_4 45, gripper open.
- `tmp/wxai/menagerie_pose.png`: Menagerie at the same pose. The two match link for link. Menagerie's
  meshes show the pocketing and the D405 that the dummies lack.

The shared daemon was started without a display, so its `cad mjcf snapshot` fails with "no X
display". The pictures were drawn in-process instead, with `xvfb-run -a python -c "from cad.engine
import api; api.snapshot('out/wxai/wxai.xml', ..., daemon=False)"`.

## Timings

- `python src/wxai.py` through the daemon:
  - Cold build 7.5 s (the STEP read about 6 s of it).
  - Export of the MJCF, URDF and SDF in 3.7 s.
  - Warm rebuild 0.03 s, with the export saying "unchanged" in 2.4 s.
- In-process (`api.export(wxai.wxai, ..., daemon=False)`): 13 s.
- `measure_gripper()`: 66 s.
- The axis search: 1.4 s for six joints.

## Gaps in text-to-cad

1. **The density of a vendor STEP is read 1000x too small.**
   - The STEP declares `POSITIVE_RATIO_MEASURE(7850.)` in `DERIVED_UNIT(kg, m^-3)`.
   - `step.read` gives `part.material.material.density == 7.85`, so as read the arm weighs 12 g.
   - Reproduce it with `read_step_shape("upstream/wxai/wxai_follower.step").children[0].material.material.density`.
   - The cause is `cad/engine/document.py::_label_material`, which does `physical.GetDensity() *
     1000.0`. That assumes g/cm^3, but OCCT returns this file's density as 0.00785.
   - A STEP that text-to-cad wrote itself round-trips (mild steel reads back 7800). Its writer puts
     the density in an odd `DERIVED_UNIT((g^3, cm^2))`.
2. **No prismatic-prismatic coupling** (above). A symmetric two-slide gripper is common. MuJoCo's
   `<equality><joint>` and URDF's `<mimic>` both express it, but there is no AP242-named function that
   makes it.
3. **kinematics.md's revolute recipe turned a STEP part 90 degrees at angle 0.**
   - With `bd.RigidJoint(name, child, bd.Plane(origin=axis.position, z_dir=axis.direction).location)`
     and a Y-axis hinge on the STEP-read link_1, `connect_to(angle=0)` turned link_2 by 90 deg about Y.
   - First cause: axis directions from `face.axis_of_rotation` carry 1e-17 noise, and
     `bd.Plane(z_dir=(1e-17, 1, 0)).x_dir` is X where `bd.Plane(z_dir=(0, 1, 0)).x_dir` is Z.
   - After snapping the direction, the hinge's own frame (`parent.location *
     hinge.relative_axis.location`) still had X = (1, 0, 0) where the Plane had (0, 0, 1). link_1's
     Location carries 1.7e-15 translation noise; a hand-made Location with that noise does not
     reproduce it.
   - Workaround (in the model): build the RigidJoint from the hinge's own frame, and assert that every
     child stays where the STEP has it.
   - The engine did not catch it: a turned child would simply have been "as built". kinematics.md
     could say that the RigidJoint must share the hinge's X.
4. **No contact exclusion** can be declared, so a hull pair that touches at rest (base_link/link_1
   across a coaxial bearing) can only be excluded in the scene. Menagerie hand-writes the same
   `<exclude>`s.
5. **A part fixed to a link cannot stay a body of its own.** Menagerie and the URDF keep
   camera_mount_d405 and gripper_left/right as fixed child bodies. Here they merge into link_6 and the
   carriages. A jointless part in a sub-assembly beside a jointed part goes to the ground link, not to
   its sibling (`tmp/wxai/fixed_test.py`: `cam` landed in `base`), so fastening by RigidJoint pairs is
   the only way, and it merges. A comparison has to merge Menagerie's fixed bodies.
6. **URDF joint limits are written with `effort="0" velocity="0"`.** The spec gives both (27/7 N*m;
   6.28 and 9.42 rad/s), but there is no declaration for them, and a ROS controller reads 0 velocity
   literally.
7. **One collision hull per part, no decomposition**: link_6 and link_2 (above).
8. **URDF renames a joint that shares a link's name** (`pinion_racks`: joints `left`, `pinion` written
   as `left_2`, `pinion_2`, and the `<mimic>` names follow). URDF keeps joints and links in separate
   namespaces, so a mimic or a controller config that names the joint breaks. The WXAI's names are
   distinct, so it is not affected.

## Notes on the code

- `src/lib/` has no `__init__.py`, and the model imports `lib.step_axes` as a namespace package. The
  models README warns that a namespace package is not imported afresh by a warm worker, so after an
  edit to `step_axes.py`, `cad stop` (or `daemon=False`) picks it up.
- The model copies every occurrence with `.located(...)` before labelling or jointing it. The STEP
  reader's objects are memoised per worker and must not be mutated.
