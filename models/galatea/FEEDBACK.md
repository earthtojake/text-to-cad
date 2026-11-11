# Feedback on text-to-cad, from building `models/galatea`

Notes kept while modelling an articulated humanoid of 700 to 850 parts with the cad skill,
filming it with the render skill and simulating it in MuJoCo (`cad-server 0.11.4-dev.0` to
`0.11.6-dev.0` from this checkout, 4 cores, 15 GB, no GPU). Each entry says what
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

**A second lesson, on looks and on parts.** The first two versions were detailed before
anyone had agreed what the robot should look like or what it was made of. The person then
asked for the opposite of both: a plain two-tone body in the manner of current production
humanoids instead of an ornamental one, and real actuators instead of housings I had
dimensioned myself. Most of the exterior and every drive bracket was redone. What I do now:

- Before detailing, a styling model: the outside alone as plain solids on the joint layout
  (`models/galatea/src/styling.py`, 17 s to build), sent as a sheet of four views. Three
  passes of it took fifteen minutes and settled what weeks of detail had not.
- Before designing a bracket, the real part it carries, from its maker's drawing. The real
  drives were up to 20 mm larger across than my invented ones; that moved five joint
  centres, changed two linkages and made one travel limit depend on another joint.
- A measure that needs no kernel for the question asked most often. `fit.py` answers
  "does this skin hold the mechanism, through its travel, with 3 mm of air" from the
  sections and the meshes in seconds, where a build and an exact check take minutes.
- Say what I am doing while I do it. Long silent runs were read, rightly, as not listening.
- Judge a look from behind as well. Every sheet I had judged the restyle on was a front or
  a three-quarter view, and the checks all passed on a robot whose back still showed three
  bare drives at the waist, two behind the hips and an open pelvis. The sheet I judge now
  is five views round the model (front, front quarter, side, back quarter, back), whole
  and then region by region (`models/galatea/src/sheet.py`, sixty lines).
- Count what a cover costs before drawing it. The abdomen that hides the waist's drives
  had to clear the pelvis however the chest leans, which set its hem and took 5 degrees
  off the waist's roll; the head's nape cannot come lower without meeting the neck's stem.
  Travel and covers are one design, and the travel table is where the cost is written.
- Move the joints that share a centre together. The sweep that takes one control through
  its travel passed a hip that could not raise a leg turned in: at 100 degrees of flexion
  the thigh's skin stood 2 mm in front of the pelvis plate, and 5 degrees of toe-in put
  it through. `interference.py --corners` now takes each such group (waist, neck, hip,
  shoulder, wrist, ankle) to every corner of its travel and the middle of every edge, 20
  poses a group, about a minute each. It found that one and nothing else. The fix was no
  apron between the hips and a raked top edge on the thigh, lower toward the groin: the
  plane under every point of the skin that came up under the pelvis anywhere in the hip's
  travel, found without the kernel by taking the skin's mesh through 200 poses.

- **A check of the poses is not a check of the motions, and a check of the motions under a
  fixed pelvis is not a check on a floor.** Every pose balanced and no motion interfered,
  and a simulation still found a squat that went over backward and feet that slid: the
  path between two sound poses had never been looked at with the feet where a floor
  holds them (entry 40). The check now follows each motion in time, standing on its
  feet. The rule it leaves is the one above again: say what the check stands in for,
  and then test the thing itself.
- **The repository has checks of its own, and they are not the three I ran.** Before
  each push I ran the tree's shipping contract and the policy tests I judged relevant.
  The whole policy suite takes 37 s and had two failures waiting for the pull request,
  both from this work: a file at the repository's root that no CI rule knew, and a
  script named `build.py` under `models/`, a name the repository keeps for KiCad
  project builds. Run all of `scripts/test/test-global.sh` before the first push.

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
   section, is right; a box in place of the prism is right. Later the difference of two
   lofts through sections that step in sharply came back as two invalid solids of a
   seventh of the right volume. (A third case I first put here, a cut that seemed to leave
   more volume than it started with, was the measurement and not the boolean: bug 9.) This
   is OCCT under build123d, not the
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

9. **`shape.volume` is good to about one per cent on a thin lofted shell.** It is a
   fixed-order quadrature. For a 2.6 mm skin between two lofted surfaces the three volumes
   of a correct cut (what was there, what is left, what was removed) disagreed by 2,600 mm3
   in 334,000, which looks exactly like a wrong boolean and is not: the adaptive integral
   (`BRepGProp.VolumeProperties_s(shape.wrapped, props, 1e-3, False, True)`) makes them add
   up to 5 mm3. It costs 0.2 to 2 s a solid where `.volume` costs nothing. A model that
   reports masses of skins, or guards its booleans by volume, needs to know; a
   `cad.build123d` helper with a tolerance would be the place to say it.

10. **One boolean, two result types.** The same `shell & prism` returned a `Part` in plain
    Python and a `Compound` under `cad run`, and `Compound(children=[...])` then failed on
    it with a bare `AssertionError` from the tree library, no message. Taking `.solids()`
    of every boolean's result before labelling it is the workaround.

25. **A warm rebuild kept a prototype's old Python state.** I gave `kit.proto` a new
    attribute on the shapes it returns (`_stood`, the location a vendor solid already
    carries) and read it in `mirror_tree`. The build line said `lib/kit.py` had changed
    and rebuilt in seconds, and the right-hand drives were still placed the old way, 6
    degrees off their bolt holes: the memo's hits handed back shapes made before the
    change, without the attribute. `cad stop` and `cad delete` did not clear it (the
    bodies came back from the disk cache under the same key); a further edit on a fresh
    worker did, 174 s cold. A check of the brackets against the drives found it, not the
    build. A memo hit should not survive a change to the function that made the shape, or
    the skill should say that a plain attribute set on a shape is not part of what is
    cached.

26. **`moved()` on a leaf of the model's tree copies the tree.** Posing one solid for a
    check, `leaf.moved(location)` took 13.6 s and 2.5 GB for a thumb pad of twelve faces:
    build123d copies the shape's parents with it. Four workers doing that ran the machine
    out of memory. `type(leaf)(leaf.wrapped)` first, a shape with no parent, makes it
    instant. Worth a line beside `handle.shape`: detach a leaf before you move it.

27. **A loft to a point ends in a cusp or a dimple.** `loft([... sections, Vertex])` came
    to the helmet's crown as a cone a millimetre high with sides at 30 degrees, and
    overshot the heel's point by 1.7 mm, leaving a dimple. Neither shows in a shaded
    snapshot; both show at once in a path tracer. Rows added near the point (entry 24)
    made the whole foot ring: its width 90 mm away changed by 6 mm, and with three rows
    the solid came back inside out, 40 times its volume, and valid. What works is to
    drill the end out round its axis and fill the mouth with `Face.make_surface_patch`,
    each rim edge given with its face at `ContinuityLevel.C1` (`geo.smooth_tip` in the
    model; with build123d's call and not the kernel's own, for the reason in entry 32).
    That recipe in the skill's notes on `loft` would have saved two hours.

28. **`Face.center()` of a cylinder's wall is a point on the wall,** not on its axis, and
    `shape.volume` of a lofted solid moved by 3,000 mm3 when a 790 mm3 hole was drilled
    in it (entry 9 again: a guard that compares volumes needs a per cent of slack, or
    `BRepGProp` with a tolerance).

29. **The GLB names a material after its physical grade, not its look.** Blender gets
    `Alu_G7075_T6`, `Alu_G7075_T6.001`, `PC_GENERIC`, `PC_GENERIC.001` for looks the model
    calls `frame_black`, `accent_champagne`, `smoke35` and `light_white`. A render script
    cannot say "the face shield's look" by name; it has to go through the part
    (`model.objects["head/face_shield"]` and its slots). The look's own name on the
    material would let a script restyle by look.

## Gaps that cost real time

11. **No interference check.** The skill's rule (overlap volume 0 for every pair, posed
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

12. **A motion cannot be drawn.** `cad model snapshot` takes a pose, not a
   configuration sequence and a time, and has no frame output. To review the gait I
   recomputed each frame's joint values in my own code and called the command sixty
   times. `--motion walk --at 0.6`, or `--frames 30` into a folder, would make motion
   reviewable. The first posed snapshots of a session also took 18 s each ("Making the
   scene" per pose) against 4 s later.

13. **The snapshot's tessellation is fixed.** 0.25 % of a part's box and 28.5 degrees
   (`cad/engine/mesh.py`) is right for the viewer and coarse for a still: a 400 mm lofted
   skin shows a faceted silhouette and wavy shading in a close-up, and only STL and 3MF
   exports take `--tolerance`. A `--tolerance` (or a quality level) on `snapshot` and on
   the GLB export would fix it.

14. **A fixed camera across pictures needs hand arithmetic.** The presets and
   `azimuth:elevation` refit every picture, `--json` does not return the camera it
   settled on, and a camera object in an orthographic view is refitted to the whole
   model. For frames that must not jitter I derived eye positions from the film gauge
   maths in the renderer's source. Returning the resolved camera in `--json`, and a
   `fit: false`, would remove that.

15. **`hidden` and `isolated` take only exact occurrence paths.** Leaving the skins off
   meant listing 47 refs, each numbered among its siblings (`chest/skin_screw.3`). A
   selector by label (`*/skin_screw`) or by material would make "show me the structure"
   one flag.

16. **`cad run` chooses a script's integrations from the script's own imports.** A check
    that reaches build123d only through the model it imports fails with
    `ModuleNotFoundError: No module named 'build123d'`. The message does name the remedy
    (`cad[build123d]` in the header), which is good; the engine already traces
    first-party imports for its build keys, so `cad run` could do the same.

17. **A worker retired for memory makes the next run cold without saying so.** With the
    default 3.9 GB budget the 1.2 GB worker of a 68 s model was retired several times
    (`retired: galatea.py (RSS)` in `cad status`). The next `cad run` just reports
    `cold in 67.73s`. Say why in the run's own line, and name `CAD_ENGINE_MEMORY_MB`.

18. **Loft seams are drawn as edges in shaded pictures.** Every lofted skin shows a line
    where its sections close. I rotated each seam under a cut-out. An option to draw
    only sharp edges would be the real fix.

19. **A still for a person needs a studio, and the command line has none.** `cad model
    snapshot` draws "technical OCCT images": flat light, no shadow, no reflection, so a
    gloss-black part is a black silhouette and a white one has no form but its edges. The
    viewer has a photographic Preview, but a checkout serves no built client (the page is
    "Not found" until the web app is built), and a headless session has no other way to
    it. I composite a backdrop and a contact shadow under each picture myself. A
    `--render` on `snapshot`, however slow, would change what a model can be shown as.

20. **A part that lets light through fights the part behind it.** `transmission` between
    0 and 1 draws as a tint, which is exactly right for smoked glass, but where the glass
    lay on a liner (two surfaces from one loft, in contact) the picture mottled. An air
    gap of a few millimetres cures it; a line in the materials reference would save the
    hour.

21. **One memory limit, many heavy things.** An exact interference crew of four, the
    engine's worker for the robot, another for nine posed copies and a snapshot at twice
    size together passed the machine's memory, and the kernel killed the robot's worker
    mid-picture (`the worker for galatea.py exited (-9) ... Drawing the picture`: the
    message is exact). Its memo went with it: the next build was 133 s cold instead of
    22 s. `cad status` could show each worker's memory against the budget, and the
    engine could refuse a new job rather than lose a warm worker.

22. **A snapshot's background is clear or white, nothing else.** `output` takes
    `transparent`, `padding`, `renderScale`, `sizeProfile` and `tightFrame`; a pearl robot
    on white has no outline and on clear it has to be composited before anyone can look at
    it. A `background` colour would do. So would a sheet: the same job from N cameras,
    tiled into one picture, which is what every review above wanted.

23. **A turned polygon shows as rings.** `revolve` of a polyline profile is a stack of
    cones, and a shaded picture draws every one of them as a band on a glossy panel (the
    shoulder pods looked like targets). The cure is a profile of real arcs
    (`EllipticalCenterArc`, whose angles are `start_angle` and the keyword `arc_size`, not
    a start and an end). Worth a line in the skill's modelling notes: profiles that will
    be seen should be curves, not sampled points.

24. **A loft is a spline through its sections, and it rings.** To make a thigh shallower
    at its top I added two sections 30 and 80 mm below the top one. The surface moved
    20 mm inward 250 mm away, between the two lowest sections, and put the liner through
    the frame there. My quick measure, which interpolates the sections linearly, saw
    14.9 mm of air where the kernel's solid had none; only the exact check as built found
    it. Sections spaced evenly with the change carried by their values, not by more of
    them, kept the form where it was. The skill could say so where it describes `loft`:
    sections close together at one end bend the surface at the other, `ruled=True` is the
    way to a form that goes only where its sections say, and a clearance measured from
    the sections is not one measured from the solid.

30. **A maker's STEP file is one shrink-wrapped skin, and everything exact is slow on
    it.** RobStride's RS04 is a single solid of some 3,000 faces. `bounding_box()` of one
    placed copy took 3 s (110 s for the robot's 33), and an exact intersection with a
    bracket took seconds more, so the interference check went from five minutes to out
    of memory. The cure was mine to find: a plain envelope per model (cans, lobes, a
    sector for the connector), held by a check to containing the maker's solid, and
    measured in its place. The skill's vendor-part page could say it: place the real
    solid for the picture and the mass, check against an envelope.

31. **The skill says to keep a vendor's STEP beside the model; this repository keeps no
    CAD file in Git.** The five drives are 53 MB. What reconciles the two is a fetch
    script that names the maker's commit and each file's checksum, and an ignored
    `vendor/` folder. A `cad step fetch <url> --sha256 ...` (or a documented pattern for
    it) would make that the path of least effort, and the build's error for a missing
    xbf could name the command.

32. **One shape made with the kernel's own classes switches the memo off behind it, and
    nothing says so.** To mend a loft's pointed end (entry 27) I called
    `BRepOffsetAPI_MakeFilling` and `BRepBuilderAPI_Sewing` from `OCP` directly. The model
    was right, and from then on every build of it took 150 to 250 s that had taken 25:
    the memo cannot name a shape it did not see made, so every boolean on the helmet's
    form ran again each time, the `@memo` stage could not be replayed, a change to a
    motion alone rebuilt the robot (`bodies 2 run; 6154 misses, 0 hits` on a worker that
    had not built it), and nine posed copies took 170 s each, not 2. The build line gave
    no hint: `12 misses, 6142 hits; body 152.64s` reads as a slow machine. I found it
    with `py-spy dump` on the worker. The same cap made with build123d's own
    `Face.make_surface_patch`, `Shell` and `Solid` is the same solid to four decimals,
    and a change to a motion now rebuilds in 1.5 s (`bodies 1 run, 1 replayed`). Two
    things would have saved the afternoon: a line in the build's report when calls ran
    plain because an input was made outside the memo (`31 calls ran plain behind a shape
    made at lib/geo.py:302`), and a sentence in the skill: reach for `OCP` only for
    questions; a shape made with it is one the memo cannot keep.

33. **On a machine without a GPU, EEVEE ends the process.** `scene.render.engine =
    "BLENDER_EEVEE"` and a render print `Couldn't open libEGL.so.1` and abort (exit 134),
    with no Python exception to catch. So does the compositor's glare, from the skill's
    own snippet, until `scene.render.compositor_device = "CPU"` is set. The render skill
    drafts in EEVEE throughout; on a headless Linux box every draft has to be Cycles
    (960 x 540 at 10 samples took 4 to 10 s here, which is fine). The skill could say so,
    `cad doctor` could report whether EEVEE can start, and the snippet could set the
    compositor's device.

34. **The first `cad run` of a bpy script failed after 48 minutes** with `uv could not
    make the blender integration's environment: Downloaded numpy`, at a moment when the
    machine was out of memory for other reasons. The second run made the environment in
    under a minute. The message named the last line uv printed, not what went wrong.

35. **A smoked window cannot be exported.** The model's face shield is
    `transmission=0.35` over a near-black colour, which the viewer draws as smoked glass.
    The GLB carries the same two numbers, and Blender reads them as a black surface: the
    base colour tints what passes, so a third of nothing passes. The render skill says a
    transmissive look "refracts rather than fades"; for a tint the script had to set its
    own (a mid-grey base, transmission 1). A note in the looks table, or an exported
    attenuation colour, would cover it.

36. **An exported clip keeps the fixed link fixed.** The pelvis is the mechanism's
    ground, so in Blender the robot crouches by lifting its feet and walks in the air.
    The film needed its own `plant`: read a foot's world matrix at every frame and key
    the root's so the foot stays put (and, walking, move the root as fast as the feet go
    back). `cad.blender` could offer `model.plant("l_foot")`, or the export a `--ground`
    link. `model.objects[path]` and `model.bounds()` at a frame made it thirty lines.

37. **The skill's sample counts are for another kind of picture.** It says 128 to 512
    samples with OIDN make a clean final. A CAD model has no textures, only flat looks
    and edges, which is what the denoiser is best at: here a frame at 8 samples was hard
    to tell from one at 24, and the film was rendered at 14 to 20. On four cores Cycles
    took 1.0 s a sample at 1600 x 900 whatever else was set (denoising, the compositor
    and persistent data together were under a second), so the sample count is the whole
    budget. A line saying "for a model with scalar looks, start at 16" would have saved
    me from planning a thirteen-hour render.

38. **`cad run` prints a `view:` link that answers 404.** In a checkout where the viewer's
    client has not been built, every build still prints `view: http://127.0.0.1:3245/<id>?token=...`,
    and the page is `Not found`. I wanted footage of the real viewer for a film and found
    out by fetching the link. The line could say that the client is not built here and
    name the command that builds it, or leave the link out.

39. **An animation cannot name a link that shares its label with one of its parts.**
    `animation(...).channel("lumbar_yoke", ...)` is refused: `lumbar_yoke names 2
    occurrences: lumbar_yoke, lumbar_yoke/lumbar_yoke` (entry 7 again, in a new place).
    There is no way to write "the one at the top": a path from the assembly is the same
    string. What works is a glob only that name matches (`lumbar_yok[e]`), because of a
    glob's matches the outermost is taken. A leading `/`, or taking the shortest path
    when one match holds the others, would say it plainly.

40. **A motion says what the joints do, not what a floor would hold.** A mechanism has one
    fixed link, and a sequence is waypoints eased joint by joint under it. For a robot
    that is the pelvis, so every motion I wrote slid its feet about in the air, and the
    pictures looked right because `stances.py` and the film set a foot back on the floor
    frame by frame. A MuJoCo model built from the same numbers (`models/galatea/sim/`)
    showed what a floor makes of them: the squat went over backward (its two poses
    balanced by 77 and 32 mm; the path between, each joint eased on its own, passed
    within 8 mm of the heels' edge), the bow and the reach scrubbed their feet and left
    the hips pushing up to 105 N m against the floor's friction, and the one-leg stand
    lifted its foot before its weight had left it. Nothing in the tooling could have
    said so: the document does not know which links stand on something. What I did:
    a leg solver for feet that stay (`kin.standing`), the motions as paths of the pelvis
    over them, sampled, and a check that follows each motion in time
    (`checks/balance.py`). Every motion on two feet now stands in the simulation; the two
    on one foot still fall, for a reason no path answers (entry 48). What would have helped: a word in the skill where it tells a
    robot's builder to fix the base link ("the fixed link is a choice of frame: a motion
    written under it needs checking in the frame of whatever the robot stands on"); a
    `plant=<link>` on `cad model snapshot` and on the viewer's playbar, so that a motion
    can be watched standing on a foot; and, further off, a sequence that names a second
    link to keep still and solves the chain between.

41. **A motion's ease is in the code, not the docs, and a function of time is hardly
    mentioned.** `configuration_sequence`'s docstring says `cubic` is "eased in and out
    at every waypoint"; to check a motion as the document plays it, and to feed a
    simulator the same path, the formula had to be read out of
    `cad/engine/mechanism.py` (`3 s^2 - 2 s^3` over each step). Either the formula there
    or a call that samples a sequence (`handle.sequence("crouch").at(t)` to joint
    values) would make a second consumer exact by construction. The same docstring's
    best feature, that a sequence may be a function of time or a dense list of samples
    with `linear`, deserves an example: it is what makes a closed-chain motion possible
    at all. A sampled path also has no rate: its straight segments are exact for a
    picture, but a servo fed them takes a step in speed at every sample (the bow's waist
    drive stepped by up to 5.5 N m, the soles' load by 31 N, until the simulation fed the
    mean of the two segments' rates instead). A sequence that could say "I am a sampled
    path" and be sampled with its derivative would spare each consumer that guess.

42. **A check that follows a build closely builds the whole model again.** After a change
    to the motions my own environment built (cold, 420 s; on later edits warm, 2 s).
    Three times a check with another dependency header then built the model again in
    full in its own environment: `built ... warm in 377.89s: bodies 2 run; 6352 misses,
    0 hits` (its worker was alive, with a memo that was no use to it), `built ... cold
    in 356.35s`, and, ten minutes after two other environments had each built that very
    state, `built ... warm in 358.68s` again with no hit. Twice a check in one of the
    same environments got `took ... cold in 3.44s: the engine's cache holds the model's
    key ... nothing ran` instead, once after another environment's build and once after
    an export of the document. So the document was sometimes to be had for four seconds,
    and eighteen minutes of a core went on it instead, beside a film render. I could not
    find what decides it. A sub-agent's script met the same thing
    earlier in the day, and its build then got my own worker retired for memory, warm
    memo and all. What would have helped: the cached document taken before any build,
    whichever worker asks; memoized stages kept on disk by their closure, as documents
    are; and a line in the docs that the scripts of one project which call a model
    should share one dependency header, and why (each header is an environment, each
    environment a worker holding the whole model: five header variants over an afternoon
    made five, and the engine's memory limit holds two or three).

43. **A script cannot learn a model's materials or masses without its solids.**
    A link's mass needs each part's density, and a simulator's meshes each part's look.
    The way that works is `handle.shape`: every solid of the robot transferred into the
    script (8 s, 1.5 GB resident) to read `node.material` off 689 leaves.
    `cad model inspect <id> --query structure --json` has density by label in 3 s, but
    not the look, and there is no Python call for either. `inspect` also gives a part's
    volume, mass and bounds and stops there: a robot description needs the centre of
    mass and the inertia tensor too, and `references/inertials.md` itself says the
    kernel's are better than a mesh's. `handle.materials()` and mass properties in
    `inspect` (a part's and an assembly's) would do.

44. **There is no export for a simulator.** Three things in one: (a) no mesh per link.
    `references/meshes.md` assumes each link is a model of its own; Galatea is one
    assembly of 73 links with its joints in the document, so the engine knows each
    link's parts and the joint that carries it, and the sim's `mjcf.py` regroups the
    GLB's nodes by link and moves each into its joint's frame in a hundred lines.
    `cad model export <id> --links DIR` (one mesh per link in the frame of the joint
    that carries it, optionally one per material) is the export a robot description
    needs, for URDF as much as MJCF. (b) A mesh export can only get finer:
    `export(tolerance=, angle=)` "meshes again at the finer of each". A simulator wants
    the opposite: the default mesh is 2.55 million triangles, 83 % of them in the five
    vendor drive solids, and `mjcf.py` decimates to 413,000 in its own process. A
    ceiling the other way, or a triangle budget per part, would remove that step.
    (c) No OBJ. MuJoCo reads STL, OBJ and its own MSH; an STL has no normals, so a
    curved panel is drawn faceted or an edge smoothed away, and the script writes OBJ
    itself with normals it computes by crease angle.

45. **MJCF is outside the robot-simulation skill.** The skill covers URDF, SRDF and SDF,
    with a validator and a snapshot for each, and says to author the XML by hand. A URDF
    cannot hold a closed chain (the knees and ankles are four-bars), which is why the
    sim is MJCF with joint equalities, and 73 links with mesh-derived inertials are not
    hand-authored. A reference for MJCF's frames (a body's `pos` in its parent, a joint
    in its child, `fullinertia`), for closing a linkage with `equality`, and a word on
    when a generator is the right tool, would have saved an hour; `cad mjcf validate`
    and `snapshot` in the long run. `references/inertials.md`'s recipe is also one mesh
    at one density: a link of dozens of parts in several materials, some of them bought
    drives weighed at their maker's mass, needs each part integrated at its own density
    and the tensors carried to the link's centre of mass, and the reference could show
    that sum.

46. **Nothing says which build a derived file came from.** The model's id stayed the same
    through two rebuilds by two sessions, so a file that records the id (the MJCF's
    header, a GLB beside a film) says which model and not which state of it. The
    closure's key on the handle, or printed on the `built ...` line, would let a derived
    file name its source exactly, and would have told me at a glance whether the GLB a
    render was reading had the old motions or the new. Nor does anything say which of a
    model's outputs a change reaches. The rewrite of the motions changed no solid, joint
    or mass, and the simulation's file needed only its twelve keyframes written again;
    but the model's key covers every source, so the only way to learn "the parts are as
    they were" is to build. The sim's `mjcf.py --poses` rewrites the keyframes and
    trusts me that nothing else changed. A document that carried its parts' key apart
    from its states' and sequences' would let a derived file decide that itself.

47. **`nice` does not reach a build.** `nice -n 19 cad run script.py` runs the program
    and what it starts at niceness 19, and a simulation's render ran that way beside the
    film's. But a build is done by one of the engine's workers, a child of the daemon at
    niceness 0: a script that calls a model under `nice` has its six-minute build done at
    full priority. There is no way to ask the engine for a build that yields to another
    job on the machine, or to cap a worker's threads. Nor is `nice` enough where it does
    reach: a software rasteriser at niceness 19 still cost a four-core Cycles render
    beside it about a third of its speed (niceness shares out processor time, not the
    caches or the memory's bandwidth), and nothing told the session that started it that
    another session's long job had the machine. A line in `cad status` for the programs
    `cad run` has running, with their start times, would have.

48. **The robot-simulation skill has nothing on standing.** `references/guardrails.md`
    covers a description's sanity, not whether the robot it describes can stay up. Three
    numbers said, before any simulation, whether position servos could take Galatea onto
    one foot, and I had none of them written down: the ankle roll drive's peak torque
    over the weight (14 N m / 553 N = 25 mm) against the sole's half-width (30 mm), which
    is how far off the ankle's axis the floor's push may ever stand; the toppling
    stiffness m g h of what stands on the ankle (484 N m/rad) against the servo's
    stiffness there, below which the stance is unstable whatever the path; and what the
    legs give when the weight goes from two feet to one (a servo's sag at the changed
    load times the lever to the centre of mass: here a degree of lean, 23 mm of the 25).
    The third decided it. A reference could give all three beside the static margin and
    the centre of pressure, and say plainly that a position servo with no torque fed
    ahead is a spring, and that a simulation which assumes one should say so where its
    conclusions hang on it.

49. **A name is a convention somewhere, and only a test knew.** The script that writes the
    MJCF was `sim/build.py` until the pull request, when
    `tests/python/global/test_generated_kicad_files_untracked.py` read it as a KiCad
    project's build and asked what it writes ("has a build.py but GENERATED does not
    list what it writes"). `models/README.md` speaks of a KiCad sample's `cad run
    build.py` and does not say the name is that convention's alone. The test could look
    for a KiCad file beside the script before it claims it, or the corpus's README could
    say that a `build.py` under `models/` means that and nothing else. The other thing
    the suite caught, this file at the repository's root, is the same kind: the CI
    table knows every tracked path, and a new root file is "unknown" until it is under a
    folder a rule covers. Both are fair rules; neither is written where someone adding a
    model would read it.

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
- A change of finish across the whole structure (31 parts renamed and recoloured, grey to
  black) rebuilt in 36 s, and a five-view sheet of any region takes about 20 s: fast
  enough to settle a look by trying it.
- Re-basing nineteen joints on real actuators was an edit to one table and one builder
  for the housings, then twenty minutes of the build line's part count and the exact
  check saying which brackets no longer fitted. A parametric model in a real language is
  what made a change of that size affordable in an afternoon.
- A maker's STEP into the model: `cad step export RS04.stp RS04.xbf` once, then
  `xbf.read` in the build, and `cad step inspect` and `cad step snapshot` to find a
  mounting face and a bolt circle on it. Five drives were in the robot, aligned and
  mirrored, in an afternoon, and their real shapes found five interferences my cans
  drawn from the datasheet had hidden.
- `cad run` on a script that imports `bpy`: no set-up at all after the first run, and
  `cad.blender.load` opens a 77 MB GLB of 689 parts with ten clips in 5.5 s, every part
  under its own path. Planting feet, following a link with the camera and restyling one
  part's look were each a few lines because of that.
- A GLB of the whole robot at 0.08 mm with ten clips exports in 26 to 37 s.
- `Text` with a font file, extruded and intersected with a layer lofted 0.35 mm outside
  a skin, gives a raised wordmark that follows the surface, in 11 s.
- The exploded view as an `animation()` on the model: 73 link channels, a radial
  `.explode` per link and a slide per skin, written in sixty lines, rebuilt in 2.4 s, and
  there in the GLB as a clip that `cad.blender` plays like any motion.
- `cad model snapshot --job` with a list of jobs draws the viewer's own display modes
  (`solid` with the grid, `parts`, `xray`, `exploded`) at any pose from any camera:
  120 frames of plain CAD footage for the film from one short script, 3.7 s a frame.
- A pose can be looked at before the model has it: `cad model snapshot --job` with
  `jointValues` drew sixteen pictures of eight new poses on the document the engine
  already held, in 66 s, while the sources were mid-edit and a render had the machine.
- A motion as dense samples: five motions of 40 to 63 waypoints, 72 joints each, went
  into the document without complaint; the warm rebuild that took them was 2.45 s
  (`rebuilt: lib/rig.py: POSES changed`, which is the right thing to be told), and the
  GLB with all ten clips exported in 57 s.
- `cad run` with a PEP 723 header gave a script MuJoCo 4.0.0 beside cad in a few seconds,
  once; a script that never touches cad runs the same way and loads no kernel. The
  robot-simulation skill's discipline (the ledger at the top of the file, "never type an
  inertia", the sanity gates of `references/inertials.md`, a mesh in its link's frame)
  carried over to a format the skill does not cover.
- Kinematics kept apart from the kernel: `lib/kin.py` and `lib/poses.py` import nothing
  of it, so when five motions became sampled paths over planted feet the simulation
  followed with two small changes, re-keyed its four changed poses in two seconds and
  simulated all thirteen clips in twelve, the kernel not loaded once. The skill's
  guidance on a mechanism could recommend the split outright, and that what a check
  counts as support, and how a pose is set on the floor, live there too: a copy of the
  balance rule in the simulation's own check drifted from the model's within an hour
  (it went on counting the sprung toe, and printed 43 mm for a motion the model's check
  has at 27), and nothing failed.
- `cad run` finds a script's integrations in the imports inside its functions too, so a
  mode that calls nothing of the CAD model (`sim/mjcf.py --poses`) could move those
  imports into the branch that builds, keep the script's environment, and start in a
  second and a half.

## Corrections, from a second check of each entry

Every entry above was checked again on `main` after 0.11.7 (2026-11-10), each claim run before it
was believed. The entries are left as written, as a record of what the build met; these are the ones
that did not hold as written, and what a reader should take from them instead.

- **2.** The memo is kept per body by design, not per worker by mistake: a kernel operation's entry
  is keyed by the body that ran it, so two models never share one. The skill's text was what was
  wrong ("the server already replays every kernel call of any model"). A builder several models
  share is marked `@memo`.
- **5.** Not reproduced. 120 intersections of the head's sections with the visor, shield and rim
  prisms (with and without the apex and the extra end section, at five insets) and 78 random
  spline-bounded bands were all consistent. The fault is presumably OCCT's on particular geometry;
  it is not shown, and nothing was built to guard against it.
- **6.** `bounding_box()`, which is `optimal=True`, was tight in every case tried: the 13 mm strip of
  a 164 mm loft reads 13.000 mm. The loose box is `bounding_box(optimal=False)`, which read 39 to
  72 mm for the same strip.
- **8.** Not reproduced: 196 lens-in-bezel pairs (fresh solids, tree leaves under nested locations,
  moved there and back, mirrored, a BREP round trip) gave 0 both ways. `overlap_volume` treats its
  two arguments alike; the one asymmetry is which is OCCT's argument and which its tool.
- **9.** `.volume` is 0.4 % high on a lofted solid (0.04 % on a 2.6 mm skin), as said. The remedy
  named is itself wrong on some cuts: `VolumeProperties_s(shape, props, 1e-3, False, True)` was off
  by 699 mm3 on one slab of the skin while reporting an error of 1e-3. What closes is Gauss-Kronrod,
  `BRepGProp.VolumePropertiesGK_s(shape, props, 1e-6, False, False, False, False, False)`: under
  0.5 mm3 on all eight cuts tried, at 0.04 to 2.4 s a solid.
- **10.** No difference between plain Python and `cad run` was found. In both, `a & b` of two parts
  that share no volume is an empty `Compound` (of two `Solid`s, `None`), and
  `Compound(children=[...])` holding an empty one fails with the bare `AssertionError`. The
  "Compound under `cad run`" was most likely that empty result.
- **13.** A GLB export has taken `--tolerance` and `--angle` since 0.11.6 (this file's own "what
  worked" says a GLB at 0.08 mm). Only `snapshot` has no tolerance.
- **16.** `cad run` does read the imports of the local modules a script imports, in its folder, its
  package or its project. What it does not read is a module reached through a path added at run
  time: the checks reach the model through `sys.path.insert` in `checks/common.py`.
- **17.** The variable is `CAD_ENGINE_WORKER_RSS_MB`, read when the engine starts.
  `CAD_ENGINE_MEMORY_MB` is the documents' budget, not the workers' cap.
- **18.** `--display shaded` draws no edges at all. The seam line is in `solid`, the default, and
  in the x-ray, hidden-line and wireframe modes.
- **21.** `cad status` already shows each worker's memory and the total against the cap. The `-9`
  was the system's out-of-memory killer, which the engine's cap does not see coming: it counts its
  own workers, not a `cad run` program or a check's processes.
- **26.** More than a line beside `handle.shape`: the skill's own `world_parts` helper called
  `located()` on every leaf, so it copied the tree once a leaf (6 s for 60 leaves, 28 ms with the
  leaf taken out of its tree first). 0.11.8 replaces the helper with `cad.build123d.leaves`, which
  gives each leaf out of its tree.
- **39.** There was a way to write "the one at the top": the path from the animation's own assembly,
  its label first (`galatea/lumbar_yoke`). The refusal listed the paths without that label, the
  first of which was the refused name itself, which is what hid it.
- **43.** A part's density was to be had without its solids, from Python:
  `cad.model.inspect(id, query="structure")["summary"]["materials"]`. A centre of mass and an
  inertia tensor of several parts at their own densities is `cad.build123d.mass_properties`. The
  look's name is still not there.

**What changed after this review**, in the pull request that carries this file:

- `posed()` says a coupling's values again from the pose, so a posed copy keeps its states and
  sequences (1). Before, a value that stayed in range was silently another pose.
- A shape's own attributes are part of its memo key, so code edited to set one is not handed the
  shapes made before it (25). The build's line counts the calls that ran uncached and says why a
  body is not retained (32), and a cold run whose worker was retired says why (17). A worker
  holding an older state takes the document another environment's worker built (42).
- `cad model interference "$ID"`: every pair of parts whose boxes meet, measured exactly, as built
  and at the poses, states and sequences asked, the named fits apart, a pair it could not measure
  said and never passed (11).
- `hidden` and `isolated` take globs (`*skin*`, `*/skin_screw`), and a name an assembly shares with
  a part inside it is the assembly, in a ref and in an animation (7, 15, 39).
- A snapshot's `--json` gives the camera it settled on, which a job draws exactly (14). A killed
  snapshot job's folders are swept by the next (3). `inspect` names a material's first few parts
  and counts the rest, as of 0.11.8 (4). The page of a checkout with no client built says so (38). uv
  killed mid-install is said as that (34). The KiCad test's message and the corpus's README say a
  `build.py` under `models/` is a KiCad sample's alone (49).
- A snapshot job stands on the flat colour it asks for (`"output": {"background": "#2b2d31"}`), so a
  pearl part has an outline without compositing (22). A GLB names each material by its look
  (`frame_black`), the physical material's name beside it, so Blender no longer gets
  `Alu_G7075_T6` and `Alu_G7075_T6.001` for two looks of one aluminium (29).
- The skill's notes: the memo per body, `OCP` shapes and the import scan (2, 16, 32); the ease's
  formula, dense linear paths and the fixed link as a choice of frame (40, 41); lofts, revolved
  polylines, empty Booleans, the loose box and the volume integral (6, 9, 10, 23, 24, 27, 28); glass
  over a liner and smoked glass (20, 35); EEVEE and the compositor with no graphics driver, and
  sample counts on the CPU (33, 37); mass properties of a link of several parts (43, 45); and the
  review order and the planted failure in *Check each change*.

- A snapshot draws the sharp edges alone when asked (`--display solid,edges=feature`): no line down a
  loft's seam (18). For a finer mesh in a close-up there was a route already, now written down: a
  GLB exported at a tolerance, drawn as that file (13).

- A snapshot draws a configuration sequence at a time of it (`--pose walk@0.6`), and a list of
  jobs its frames in one command (12). It stands under the mechanism's fixed link, as the sequence is
  written.

- A snapshot is lit when asked (`--preview`): the viewer's Preview drawn by OCCT, with no browser --
  its studio light, shadows on the model, its materials, a floor and its shadow, tone-mapped as the
  viewer's. A gloss-black part has form and a white one shading (19). It is a raster, not the
  viewer's picture pixel for pixel: no ambient occlusion, glass as a tint.

**Still open**, each a decision and not a defect: a snapshot drawn with another link as its ground
(40, 36); a mesh per link and an MJCF reference for a simulator (44, 45, 48);
what the engine counts against its memory cap, and a build's priority (21, 47); a fetched vendor
STEP (31); and a guarded Boolean and both orders of `overlap_volume` (5, 8), which nothing
reproduced.
