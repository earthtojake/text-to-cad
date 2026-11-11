---
title: Mechanisms and animation
description: Joints, poses and motion for assemblies, how joint stops and collisions are checked, and how motion and animations reach a GLB.
---

A mechanism is an assembly whose parts move relative to each other: a hinge, a slide, a gripper, a robot arm. Your agent describes the joints in the model script, names the poses and motions, and checks that the parts neither collide nor run past their stops. You end up with a model you can pose and play in the CAD Viewer, and a GLB that carries the motion into Blender or a web page.

## What to ask

- "Add a hinge to the lid of the enclosure, 0 to 110 degrees, and name two poses, shut and open."
- "How far can each joint of this arm turn before the parts meet? Write the stops into the model."
- "Check the arm for collisions in the folded and reach poses."
- "Make a 4 second explode animation of the hinged box and export it as a GLB."

## What your agent does

1. **Writes the joints into the assembly body.** Joints are build123d's: `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`, `BallJoint` and `RigidJoint`, joined with `connect_to`. The value a joint is connected at is the as-built pose, the one every exported file shows. Values are in degrees and millimetres, and `angular_range` or `linear_range` set a joint's limits.
2. **Names poses and motions** with functions from `cad.build123d`. A mechanism state is a named pose, and a configuration sequence is joint values over time, written as waypoints:

   ```python
   import build123d as bd
   from cad import model
   from cad.build123d import configuration_sequence, mechanism_state

   ELBOW = ((40, 0, 20), (0, -1, 0))   # origin and direction: +angle lifts the arm


   @model
   def hinge():
       base = bd.Box(100, 60, 20, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
       arm = bd.Pos(40, 0, 20) * bd.Box(120, 20, 10, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
       base.label, arm.label = "base", "arm"
       elbow = bd.RevoluteJoint("elbow", base, axis=bd.Axis(*ELBOW), angular_range=(-10, 120))
       bd.RigidJoint("elbow", arm, elbow.location)
       elbow.connect_to(arm.joints["elbow"], angle=30)   # as built: elbow at 30
       assembly = bd.Compound(children=[base, arm], label="hinge")
       mechanism_state(assembly, "closed", elbow=0)
       mechanism_state(assembly, "open", elbow=90)
       return configuration_sequence(assembly, "cycle", [(0, "closed"), (2, "open"), (5, "closed")])
   ```

   Couplings (`gear_pair`, `rack_and_pinion_pair`, `screw_pair`) make joints move together by a ratio, with one slider in the viewer.
3. **Looks at the poses.** For example `cad model snapshot "$ID" tmp/open.png --pose open`, or `--pose cycle@2.5` for a sequence at a time, or joint values as JSON.
4. **Finds the joint stops.** `cad model ranges "$ID"` turns or slides each joint alone, a degree or a millimetre at a time each way, until its parts meet. It writes nothing. Your agent reads each finding, with the two parts that met, and writes the stops into `angular_range` or `linear_range`. Add `--joint NAME` to sweep one joint.
5. **Checks for collisions.** `cad model interference "$ID"` answers exactly, on the parts' own solids, which pairs share volume. It checks the poses it is given and chooses none, so your agent passes each state and each sequence at the times that matter:

   ```bash
   cad model interference "$ID" --pose open --pose cycle@2.5
   cad model interference "$ID" --fit pin base
   ```

   A pair meant to overlap, such as a pin in a bore, is named with `--fit`. Exit 0 is clear, 1 means a pair shares volume, and 3 means a pair could not be measured, which is not a pass.
6. **Adds an animation when the motion is not the mechanism's.** An explode, a reveal or a showcase is `animation()` from `cad.build123d`, a set of glTF channels on parts. It is no part of the mechanism, so a helper joint is never added to fake an explode.

   ```python
   show = animation(box, "showcase", duration=4)
   show.pose(at={0: "shut", 1.5: "open", 3.5: "shut"})
   show.stagger("feet/*", by=(0, 0, -20), step=0.5, start=0.5)
   ```

7. **Exports on request**, for example `cad model export "$ID" GLB/hinge.glb`.

## What you get

- **A posable model.** The model page has a Position panel: a slider for each coupling and for each joint no coupling moves, and your mechanism states as presets.
- **Playback.** The playbar under the model plays, pauses and scrubs configuration sequences (the page calls them motions), with loop and speed. Animations play on an exported GLB's page; the model's page shows nothing of them.
- **A GLB with the motion in it.** Every configuration sequence becomes a glTF animation clip with its own name, and every `animation()` is baked in. Blender, three.js and the CAD Viewer play them. STEP, STL and 3MF carry placements only, and animations exist only in a GLB.

## Limits

- A linkage that closes a loop (a four-bar, a slider-crank) is kept in the document but not posed, because there is no solver. Its pairs are not swept by `ranges`, and a state or sequence that moves one is refused or left out.
- `ranges` finds the stops where parts meet. It does not sweep a cylindrical or spherical joint. A stop that comes from a pair that does not really limit the joint in hardware is not the range, so your agent reads each one against the geometry or the datasheet.
- Interference checks only the poses it is given, not one between two of them.
- A sequence moves joints under one fixed link. A robot grounded at its pelvis crouches by lifting its feet, so a motion that looks right says nothing about what a floor would hold.
- This is kinematics, not dynamics. Simulating a robot is covered in [Robots](/docs/guides/robots).

## Go deeper

- [Parts and assemblies](/docs/guides/parts-and-assemblies) covers the model script and exports this builds on. [Stress studies](/docs/guides/stress-studies) check a part under load.
- [CAD Viewer](/docs/guides/cad-viewer) describes the Position panel and the playbar.
- Document types: [model](/docs/document-types/model) and [GLB](/docs/document-types/glb). Integration: [build123d](/docs/integrations/build123d).
- In the repository: [the cad skill](repo:skills/cad/SKILL.md), [kinematics](repo:skills/cad/references/kinematics.md), [animation](repo:skills/cad/references/animation.md), [joint stops](repo:skills/cad/SKILL.md#joint-stops), [interference](repo:skills/cad/references/inspection-and-validation.md#interference) and [the library README](repo:packages/cad/README.md).
