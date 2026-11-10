# Feedback on text-to-cad, from building `models/galatea`

Notes kept while modelling a 851-part articulated humanoid with the cad skill
(`cad-server 0.11.4-dev.0` from this checkout, 4 cores, 15 GB). Each entry says what
happened, where, and what would have helped. Newest findings are appended to each section.

## Review discipline (a note to the agent, and a suggestion for the skill)

**What went wrong.** The tibia rails cut through the shin guard, and the foot frame into
the foot shell, in a model I had reported as checked three times over. A person saw it in
the first renders. Two failures compounded:

1. *The part was never reviewed on its own.* The shin guard tapers to 100 mm at the ankle
   and the rails it covers are 96 mm apart with 8 mm plates, so the guard never could
   enclose them. One side view of the shin alone shows a plate half in and half out of
   a skin. I went from writing a link straight to assembling it and looked at beauty
   renders of the whole robot, where the defect is a few pixels.
2. *The check I trusted had a blind spot I had not tested.* My interference check
   sampled points of each part's mesh (vertices and triangle centres) and asked whether
   they lay inside the other part. A flat plate has vertices only on its outline, and a
   2.6 mm skin has almost no volume for a point to land in, so a plate passing through a
   skin scored nothing. I had validated the check only on gross collisions (crossed legs,
   a hand through the chest), never on the case it existed for. "0 interferences" was
   then repeated in the README and in every later summary.

**The rule from here on.**

- A part is reviewed alone before it is placed: four sides and a section, at a size where
  an edge is visible. A link (the parts that move together) is reviewed alone the same
  way. A joint is reviewed as the two links it connects, at both ends of its travel.
  Only then the assembly, and only then poses.
- A casing and the structure under it are drawn with an intended relationship: inside
  with a stated clearance, or outside, or meeting at a designed edge. "Half covered" is a
  defect even when the overlap volume is zero.
- A check is trusted only after it has failed on a planted example of exactly what it
  guards against. Exact geometry first (`overlap_volume`); a mesh test only as a
  prefilter, and never as the verdict.
- "All checks pass" is reported with what the checks cannot see.
- A boolean on a lofted solid is not trusted either (bug 5 below). The builders now make
  them through four helpers (`lib/geo.py`: `common`, `cut`, `carve`, `fuse`) that refuse a
  result which cannot be right.

**What the second look found**, once the check was exact and every link was drawn alone:
the rails through the shin guard (190 mm3), slivers of the foot frame in the foot shell
(10 mm3), a neck deck sunk 1 mm into the chest frame (2,677 mm3, never seen), and a thigh
fairing whose rear edge crossed the femur's plates without touching them. The shin and
thigh casings were reshaped to hold their structure inside with 3 mm of air.

**For the skill.** `SKILL.md` already says an assembly is clear when `overlap_volume` is 0
for every pair. What it lacks is a gate: nothing asks for a per-part and per-link review
before composition, and nothing says "plant a known overlap and watch the check fail".
A short checklist in *Validation* would have stopped this. See also "No interference
check" below: the plugin leaves the hardest part of that sentence to the agent.

## Bugs

1. **`posed()` of a model that carries mechanism states drops them, with warnings.**
   `posed(galatea(), pose)` re-bases every joint's range on the new as-built pose but
   keeps the states' and sequences' values absolute, so each one is then out of range:
   `warning: kinematics: mechanism state 'crouch' of galatea/galatea: coupling 'l_knee'
   at 114 is outside its range [-114, 11]: the value is left out`, and every
   configuration sequence is left out whole. Expected: a posed copy either re-bases the
   states with the ranges or carries none, silently. Workaround: pose a twin of the
   model that has joints and couplings but no states (`assemble()` in `galatea.py`).

2. **The kernel memo is not shared between the models of one script.**
   `model-contract.md` says a script's worker "keeps every kernel operation its models
   ran, keyed by its inputs". Eight posed models that build identical geometry in one
   script each reported `5968 misses, 0 hits` (68 s apiece, nine minutes), while a
   second run of *one* model after a small edit reports `272 misses, 5722 hits`. So the
   memo is per model, not per worker. Marking the shared builder `@memo` fixed it
   (90 s for nine models). Either share it or say so: the same section tells the reader
   to "mark rarely", which is the wrong advice for several models over one body.

3. **A killed snapshot leaves its temporary folder beside the output.**
   `.galatea_torso.6wfwmmy9.tmp/` and `.galatea_reach.6fj6ckld.tmp/` were left in the
   output folder after the process was killed mid-draw. They should live under the
   system temp folder, or be swept on the next run.

4. **`cad model inspect <id>` prints every occurrence path of every material on one
   line.** For this model that is one line of several hundred paths per material, about
   50 kB to say twelve numbers. Cap the list (first three, "and 847 more") unless asked.

5. **A boolean can return a valid, wrong solid, silently.** Intersecting a lofted solid
   (seven superellipse sections and an apex) with a prism through its surface returned the
   whole prism: 1,118,501 mm3 where the answer is about 306,000. `is_valid` is true, nothing
   is raised, and `loft - prism` agreed with it (it removed the prism's full volume). The
   same prism against the same sections lofted 0.8 mm smaller, or without the extra end
   section, is right; a box in place of the prism is right. Later a cut left *more* volume
   than it started with (242,837 from 241,598). This is OCCT under build123d, not the
   plugin's code, but the plugin is where a model's author meets it, and it was the cause
   of a visor drawn as a 180 mm bar and of a trim that silently did nothing. The skill
   says of `overlap_volume` that "a failed boolean is an error, never a zero-volume
   answer"; ordinary `&`, `-` and `+` have no such promise. Wanted: the same care as a
   documented helper (the result's vertices lie inside both operands' boxes; what is left
   and what was removed add up), or a build warning when a boolean's result has exactly
   an operand's volume.

6. **`bounding_box()` of a piece cut from a lofted face is the whole face's box.** A 13 mm
   strip cut from a skull-sized loft reports the skull's 164 mm width (with
   `optimal=True`, the default). The skill recommends boxes to rule pairs out, which is
   safe; anything that uses one to say where a part *is* gets a wrong answer. Worth a line
   in `inspection-and-validation.md`.

7. **A link and a part of one label make every bare ref ambiguous.** `isolated:
   ["neck_stem"]` is refused: "neck_stem names 2 occurrences in galatea:
   galatea/neck_stem, galatea/neck_stem/neck_stem". The message is exact and the full
   path works; naming an assembly after its main part is a natural thing to do, so the
   shallower match (or a trailing slash for "the assembly") would save the trip.

8. **`overlap_volume(a, b)` can differ from `overlap_volume(b, a)`.** For a lens that fills
   its bezel's bore (two solids turned about one axis, sharing the cylinder of radius
   5.2), taken as leaves of the built model's tree: `overlap_volume(lens, bezel)` is
   637.1 mm3, the whole lens, and `overlap_volume(bezel, lens)` is 0.0, which is right.
   Fresh copies made the same way at the same place give 0 both ways, so the failure
   needs the model's own leaves and cannot be shown in five lines. The function is one
   `BRepAlgoAPI_Common` with a validity test, and a valid wrong answer passes it (bug 5
   again, now inside the check itself). A check built on it reports a part inside
   another that only touches it. Wanted: measure both orders and refuse to answer when
   they disagree, or settle it with what a cut leaves.

## Gaps that cost real time

9. **No interference check.** The skill's rule (overlap volume 0 for every pair, posed
   too) is right, and the plugin offers the primitive, but an assembly of 851 parts has
   thousands of near pairs, poses, a mirrored side, and solids that take 0.3 to 40 s
   each to intersect. I wrote that machinery twice, and the first version was wrong
   (above). A built-in `cad model check interference [--pose NAME | --sweep JOINT]`,
   exact, pruned by boxes, parallel, with fits declared by name, would be the single
   most valuable addition for assemblies. Even a documented, tested helper would do.
   For scale: this model has 1,353 pairs of parts whose boxes meet as built (leaving out
   the mirrored side); measuring them all exactly took 22 minutes on four cores, and one
   pair (a lofted back plate against the frame under it) four minutes by itself, so a
   check needs a per-pair time limit and must report what it could not measure.

10. **A motion cannot be drawn.** `cad model snapshot` takes a pose, not a
   configuration sequence and a time, and has no frame output. To review the gait I
   recomputed each frame's joint values in my own code and called the command sixty
   times. `--motion walk --at 0.6`, or `--frames 30` into a folder, would make motion
   reviewable. The first posed snapshots of a session also took 18 s each ("Making the
   scene" per pose) against 4 s later.

11. **The snapshot's tessellation is fixed.** 0.25 % of a part's box and 28.5 degrees
   (`cad/engine/mesh.py`) is right for the viewer and coarse for a still: a 400 mm lofted
   skin shows a faceted silhouette and wavy shading in a close-up, and only STL and 3MF
   exports take `--tolerance`. A `--tolerance` (or a quality level) on `snapshot` and on
   the GLB export would fix it.

12. **A fixed camera across pictures needs hand arithmetic.** The presets and
   `azimuth:elevation` refit every picture, `--json` does not return the camera it
   settled on, and a camera object in an orthographic view is refitted to the whole
   model. For frames that must not jitter I derived eye positions from the film gauge
   maths in the renderer's source. Returning the resolved camera in `--json`, and a
   `fit: false`, would remove that.

13. **`hidden` and `isolated` take only exact occurrence paths.** Leaving the skins off
   meant listing 47 refs, each numbered among its siblings (`chest/skin_screw.3`). A
   selector by label (`*/skin_screw`) or by material would make "show me the structure"
   one flag.

14. **`cad run` chooses a script's integrations from the script's own imports.** A check
    that reaches build123d only through the model it imports fails with
    `ModuleNotFoundError: No module named 'build123d'`. The message does name the remedy
    (`cad[build123d]` in the header), which is good; the engine already traces
    first-party imports for its build keys, so `cad run` could do the same.

15. **A worker retired for memory makes the next run cold without saying so.** With the
    default 3.9 GB budget the 1.2 GB worker of a 68 s model was retired several times
    (`retired: galatea.py (RSS)` in `cad status`). The next `cad run` just reports
    `cold in 67.73s`. Say why in the run's own line, and name `CAD_ENGINE_MEMORY_MB`.

16. **Loft seams are drawn as edges in shaded pictures.** Every lofted skin shows a line
    where its sections close. I rotated each seam under a cut-out. An option to draw
    only sharp edges would be the real fix.

## What worked well

- `@memo` on the shared stage: nine models in 90 s, a pose edit in 0.6 s.
- `handle.shape` hands a check the exact tree of an 851-part model in 5.5 s, and
  `overlap_volume` on two of its solids is exact and takes seconds.
- The build line's delta (`bounds 627 x 419 x 1,745 (was 585 x 569 x 1,745)`) caught
  two unintended changes on the spot.
- `cad status`: one screen that says what every worker is doing and why one went away.
- Exports: a GLB with eight animation clips in 13 s, a 67 MB STEP in 5 s.
- Snapshot `isolated`, `pose` and `transparent` cover most review pictures without
  touching the model, and a camera preset frames the isolated parts, so "this link alone
  from four sides" is four calls. (A flag that tiles them, and repeats for each child of
  an assembly, would make the review above the path of least effort.)
- A finish-only change rebuilds in 0.65 s (every kernel call a hit), and
  `transmission=1` draws a visor one can see through.
