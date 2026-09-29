# Building the radial — rules for every part builder

Read this whole file before touching a module. Then read `src/lib/spec.py` (the
frame and every shared number), `src/lib/kin.py` (where every moving part is),
`src/lib/geo.py` (placement + the museum-section cutters) and skim
`src/lib/palette.py`, `src/lib/castings.py`, `src/lib/fasteners.py`.

The brief: a nine-cylinder, single-row, supercharged air-cooled radial,
1930s–40s golden-age archetype (P&W R-1340 Wasp proportions: 146 × 146 mm,
~1314 mm diameter), museum-restoration quality, UNBRANDED (no names, logos,
cast-in badging, data-plate text). **Aesthetics are the primary objective; kinematics are
non-negotiable.** Where beauty and function conflict on anything that does not
move, choose beauty. Beauty decides what a part looks like; kinematics decide
where it is.

## Environment

- Python: the repo's `.venv/bin/python` (cadgen is installed there, from
  `requirements-dev.txt`). CLI: `.venv/bin/cadgen`.
- Project root: `models/radial`. Run everything from there. Scratch work goes in
  `tmp/` (gitignored).
- Skill docs: `skills/cad/SKILL.md`
  and `references/build123d-modeling.md` (read the pitfalls: `align=None`,
  `.located()` vs `.moved()`, multi-tool booleans, tangent booleans, fillets
  last; colour is linear unless via `srgb()`).
- Your system: `src/<name>.py` is a thin wrapper (do not edit it); you write
  `src/lib/<name>.py`, which must define
  - `MATERIALS`: a tuple of the palette material ids your leaves use (exactly
    those — the build fails on a mismatch), and
  - `build() -> list[Shape]`: flat list of labelled, coloured leaf solids,
    authored DIRECTLY in the engine frame at crank angle θ = 0.
- Build your system alone: `python tools/engine.py system <name>` (writes
  `STEP/<name>.step`; unchanged sources are no-ops).
- Build the whole engine + render it: `python tools/engine.py build-render <job.json>`.
  Assembly builds and renders are serialised across all builders by a lock; if it
  says it is waiting, another builder is rendering — just wait.
- Never edit `spec.py`, `kin.py`, `geo.py`, `palette.py`, `systems.py`,
  `radial.py`, `tools/`, or another builder's module. If you need a shared number
  changed, STOP and report it (say exactly what and why). Add helpers inside
  your own module. You may import `castings`, `fasteners`, `geo`, `kin`, `spec`,
  `palette` freely.
- Never `git commit`. Never touch files outside `models/radial`.

## The frame (memorise it)

- **Y = crank axis, +Y = REAR** (blower/accessory section), **−Y = FRONT**
  (propeller). **Z up. Cylinder 1 points straight up.** Seen from the front
  (camera on −Y looking +Y), +X is to the right.
- Crank turns clockwise seen from the rear = right-handed about `ROT_AXIS = (0,-1,0)`.
  Cylinders are numbered in that sense: cylinder k sits at in-plane angle
  `ALPHA(k) = 40(k−1)`; the unit vector at in-plane angle b is `(−sin b, 0, cos b)`
  (so cylinder 2 is 40° toward −X; seen from the FRONT the numbering runs
  counter-clockwise).
- **Cylinder-local frame** (author per-cylinder parts once, for cylinder 1):
  `h` along the cylinder axis from the crank centre (cyl 1: +Z), `y` along the
  crank axis (+Y), `t` tangential (cyl 1: +X; points toward cylinder k−1).
  `geo.on_cylinder(shape, k)` places a cylinder-1-authored copy on cylinder k
  and shares geometry. `spec.cyl_point(k, h, y, t)` gives engine points.
- **The model is authored at θ = 0**: crankpin on cylinder 1's axis, cylinder 1
  at FIRING TDC. Everything that moves is placed by `kin` (below).

## Architecture (settled — see `spec.SOURCES`)

Firing order 1-3-5-7-9-2-4-6-8. Cam ring: 4 lobes per track, two tracks
(intake + exhaust), 1/8 crank speed, turning AGAINST the crank, driven inside the
ring by crank gear 32T → fixed compound idler 48T/15T → ring internal gear 80T.
Reduction: 3:2 planetary — crank-driven internal bell gear 72T, FIXED sun 36T,
six 18T planets on a carrier that IS the propeller shaft (prop turns with the
crank at 2/3 speed). Supercharger: 10:1, crank gear 60T → three compound
intermediates 20T/40T → impeller pinion 12T, coaxial with the crank.

Master rod on cylinder 1; knuckle pins on a circle of radius 62 about the
crankpin at 40(k−1)° from the master-rod axis; articulating rods 203 c-c, master
265. Strokes differ slightly per cylinder (146.0–147.0 mm) — that asymmetry is
real and wanted.

Valves lie in the CYLINDER-ROW plane (the h-t plane): intake on +t, exhaust on −t,
72° included, hemispherical chamber. Two rocker boxes side by side at the head
top, rocker shafts running fore-aft (along Y). Both pushrods rise in FRONT of the
cylinder in a V from the nose-case tappets to the front ends of the rockers. Intake
port on the +t side facing rearward (pipe from the blower); exhaust port on the
−t side facing forward (stack to a front collector ring). Spark plugs front and
rear of the head on its centreline (t = 0).

## Moving parts: labels are the contract

The animation, the collision gate and the exploded view find parts ONLY by
label. Label every leaf `<group>:<part>` — lower_snake, unique across the whole
engine. Moving parts MUST use these group prefixes (the prefix decides the motion):

| prefix | motion | pose at θ | who builds |
|---|---|---|---|
| `crank:` | rotates with the crankshaft about Y | `kin.pose_crank` | crankshaft (+ `crank:cam_gear` by cam, `crank:bell_gear` by reduction, `crank:blower_gear` by blower) |
| `master:` | master rod, flange, knuckle pins, retainers, crankpin bearing | `kin.pose_master` | rods |
| `artrod<k>:` k=2..9 | articulating rod k + bushings | `kin.pose_art_rod(θ,k)` | rods |
| `piston<k>:` k=1..9 | piston, rings, wrist pin, plugs | `kin.pose_piston(θ,k)` | pistons |
| `camring:` | cam ring | `kin.pose_cam_ring` | cam |
| `camidler:` | compound idler gear | spins about its own axis at −2/3 crank | cam |
| `tappet<k><v>:` v=I/E | tappet body (+ `tappet<k><v>:roller`, which also spins on its axle) | `kin.pose_tappet` | cam |
| `pushrod<k><v>:` | pushrod | `kin.pose_pushrod` | pushrods |
| `rocker<k><v>:` | rocker arm (+ its needle bearing, adjuster, locknut) | `kin.pose_rocker` | valvetrain |
| `valve<k><v>:` | valve, retainer, keepers | `kin.pose_valve` | valvetrain |
| `spring<k><v>:` | valve springs (`:outer`, `:inner`) — compress | tube deformation | valvetrain |
| `planet<j>:` j=1..6 | planet gear + bearing | orbits with carrier + spins | reduction |
| `propshaft:` | carrier + propeller shaft + thrust-bearing inner race | spins at 2/3 crank | reduction |
| `prop:` | hub, blades, spinner, retention hardware | spins at 2/3 crank | propeller |
| `impeller:` | impeller, shaft, pinion | spins at 10× crank | blower |
| `blowergear<j>:` j=1..3 | compound intermediate gears | spin at −3× crank about own axes | blower |

Everything else is STATIC; label it `<system>:<part>[_<cyl>][_<n>]`, e.g.
`heads:head_3`, `heads:cover_bolt_3I_2`, `barrels:hold_down_nut_5_07`,
`pushrods:tube_4E`. Cylinder numbers are 1..9; valve side `I`/`E` is appended to
the cylinder number. Fastener and retaining-hardware roles end in one of
`bolt, nut, stud, screw, washer, pin, clip, clamp, wire, cotter, retainer` so the
exploded view can make fasteners leave before the parts they hold.

**Placing moving parts.** Crank-train parts (`crank`, `master`, `artrod`,
`piston`, `camring`) are authored directly at θ = 0 (their θ = 0 pose is the
identity). Valvetrain parts are authored at ZERO LIFT (rocker angle 0) and then
placed with their θ = 0 pose, because at θ = 0 some cylinders' valves are open:

```python
proto = build_valve_proto("I")                 # zero lift, authored for cylinder k's axis
part = kin.place(proto_on_k, kin.pose_valve(0.0, k, "I"))
```

Never move, resize or re-time a moving part to suit a static one. If a visual
change you want would move a moving part or alter a kinematic number, STOP and
report it.

## NOSE SHIFT (layout change, binding)

The whole nose section moved `spec.NOSE_SHIFT` = 130 mm FORWARD so the crankcase
front window (and the rod star behind it) can be seen from a front three-quarter
view: the cam section, cam ring, idler, tappets, crank-nose gear/flange,
reduction gearing, propeller shaft and propeller all sit 130 mm further forward
than the numbers below say (spec.py already carries the shifted values: use spec,
not the literals here). The nose case joins the crankcase through a SLIM NECK
(spec.NOSE_NECK_Y = -112..-240, outer radius spec.NOSE_NECK_R ≈ 115) — nothing
static may sit in front of the window annulus (r 115..238, y -112..-240) except
that neck, the harness ring and the pushrod tubes. Pushrods are longer and lean
further rearward (kin updates automatically).

## Envelopes and interfaces (engine frame; r = radius about the crank axis)

- **Crankcase** y ∈ [−112, 112], split on y = 0. Cylinder pads: flat faces ⊥ each
  cylinder axis at h = 282; barrel bore Ø162; 12 studs Ø9.5 on PCD 170 per pad.
  Between pads r ≈ 262. Front face y = −112 (nose case bolts on, bolt circle r ≈ 228);
  rear face y = +112 (blower section bolts on, bolt circle r ≈ 245). Main bearings:
  front y ∈ [−100, −72], rear [72, 100], journal Ø80. Interior must clear every rod,
  piston skirt (reaches h ≈ 124 at BDC), counterweight (r ≤ 110, |y| 42–66).
- **Crankshaft** crankpin Ø70, |y| ≤ 42, at (0, 0, 73) at θ = 0; cheeks |y| 42–64;
  counterweights opposite the pin, r ≤ 110; journals Ø80; nose shaft forward to
  y ≈ −262 (cam gear at y −137..−119, bell gear at y −300..−262); rear shaft to
  y ≈ 145 (blower crank gear at y 129..143).
- **Master rod** big end |y| ≤ 41; flange plates |y| 12–26; knuckle pins Ø22 at
  r 62 about the crankpin; retainers |y| 26–30. **Articulating rods** eyes |y| ≤ 11.5.
- **Piston** Ø146, compression height 58 + 4 mm crown dome, skirt 64 below the
  pin, SIX rings (3 compression, 2 oil control, 1 scraper), wrist pin Ø38 floating
  with aluminium plugs.
- **Barrel** skirt h 205–282 (OD 158, trimmed to its cylinder wedge — see below), hold-down flange h 282–294, fins from h ≈ 300
  to ≈ 400 at 6 mm pitch, fin OD 186 at the bottom growing to 204 at the top; bore
  top (chamber base) h = 402. Black enamel.
- **Head** h ≈ 385 up to ≈ 620 (rocker covers ≲ 640 — overall engine Ø ≈ 1300).
  Deep, thin fins (clearly deeper than the barrel's). Keep the head's FRONT
  surface behind the pushrod tubes: at t = ±55 the head must stay at y ≥ −91
  above h ≈ 500, at y ≥ −103 around h ≈ 450 (tubes pass there, Ø24).
  Rocker boxes enclose the rockers (pivot at h 576, |t| 88, shaft along y
  from −112 to 14) and receive the pushrod tubes at their front lower ends
  (pushrod ball at h 588, y −100, |t| 60).
- **Cam ring** y ∈ [−192, −138]; lobe tracks at the tappet stations y = −178 (I),
  −152 (E), base radius 150; internal gear pitch r 123.1. Tappets radial at
  in-plane angle ALPHA(k) ∓ 4° (intake −4°, exhaust +4°); pushrod-bottom ball at
  r 205 on the base circle.
- **Nose case** y from −112 to ≈ −395; cam section r ≲ 235 with 18 tappet-guide
  bosses; reduction housing r ≈ 150–165 around y −300..−250; thrust-bearing nose
  r ≈ 110; governor pad on top.
- **Reduction** gear faces y ∈ [−300, −262]; ring pitch r 108, sun r 54 (fixed),
  planets r 27 on a carrier at r 81. Prop shaft forward to ≈ −560.
- **Propeller** hub ≈ y −540..−420; blades at in-plane 20°, 140°, 260° (between
  cylinders) at θ = 0; diameter ≈ 2.6 m.
- **Blower section** y ∈ [112, 262], r ≲ 262; impeller Ø280 near y 185; nine intake
  outlets on its rim. **Accessory section** y ∈ [262, 420] plus magnetos/starter behind.
- **Ignition harness ring** r ≈ 272, y ≈ −119, Ø14 (between the crankcase front
  face and the exhaust pushrod tubes). **Exhaust collector** in front, r ≈ 400,
  y ≈ −215. **Mount ring** r ≈ 370, y ≈ 300.

## Cylinder wedges (no neighbour may ever touch)

Adjacent pistons are deep in their strokes together, and two Ø146 bodies whose
axes are 40° apart overlap below h ≈ 213. So everything that belongs to one
cylinder and reaches low — the barrel skirt, the piston skirt, anything of the
crankcase between barrels — must lie inside that cylinder's 40° WEDGE (between
the planes through the crank axis at ±20° from its axis, 1 mm inside each).
`geo.wedge_trim(shape, lift)` trims a cylinder-1-authored shape; for a moving
part authored at rest height H0 whose lowest travel is Hmin, pass
`lift = H0 − Hmin` (pistons: the minimum BDC pin height over all cylinders is
188.75). The ring belt and the bore above h ≈ 205 are narrower than the wedge,
so they stay full circles.

## The museum sections (STATIC parts only — moving parts are never cut)

1. **Sectioned cylinder**: cylinder 1 is cut on the cylinder-row plane y = 0 and
   its REAR half removed (0 < y < 340), within ±20° of its axis and beyond
   r = 300 (so the hold-down flange, nuts and the crankcase are NOT cut):
   barrel fins, head, rocker boxes and covers, rear plug and lead, intake pipe
   near the head, the top of the rear exhaust collector. Viewed from the rear/above you look straight at the piston,
   rings, master rod, valves, springs and rockers in profile, with no pushrod in
   front of it. The FRONT of cylinder 1 is intact (tubes, front plug, exhaust
   stack, front lead all present) so the head-on star is complete. Build
   cylinder 1's statics as the prototype, place copies for 2..9 with
   `geo.on_cylinder`, and for cylinder 1 use `geo.cut(proto, geo.section_cutter())`.
   A fastener whose seat lies in the removed region is omitted (`geo.in_section(p)`).
2. **Crankcase window**: the crankcase front wall is opened in an annulus
   (`geo.window_cutter()`), three slim webs left carrying the front main bearing.
3. **Nose cutaway**: a sector of the nose case (`geo.nose_cutter()`, upper right
   seen from the front) is removed back to the crankcase.
Cut faces are painted MUSEUM RED: every cut you make, make it with
`kept, skin = geo.cut_with_skin(shape, "section" | "window" | "nose")` and add
the skin as its own leaf `<group>:section_skin_<part>` (same group prefix as the
part — a moving part's skin moves with it) coloured `palette.SECTION_RED`
(material `section_red`). The skin is a 0.4 mm layer lying just inside the
removed region, so it covers the cut face exactly and never overlaps the part.
Ring cut faces are left bare steel for contrast.

## Surface languages — keep them distinct (palette.py)

- `ENAMEL_BLACK` barrels (and mount ring). `CAST_ALU` heads + rocker boxes:
  bright, fins crisp. `CASE_SILVER` crankcase, nose, blower and accessory cases.
  `MACHINED_ALU` pistons, machined faces/spot faces on aluminium.
  `STEEL_POLISHED` pushrod tubes, packing nuts, fittings. `STEEL_MACHINED` crank,
  rods, pins, gears, valves, pushrods. `HEAT_TINT`(+`_BLUE`, `_STRAW`) exhaust.
  `BRAID`/`COPPER` leads, `POLISHED_ALU` harness ring, propeller, spinner.
  `FASTENER` (cadmium) hardware, `SAFETY_WIRE`, `BRONZE` bushings, `MAGNETO_BLACK`.
- Cast surfaces: generous radii (3–8 mm on big castings), draft, parting lines,
  soft transitions, bosses with root fillets. Machined faces: flat, crisp,
  small chamfers. Fins: THIN (barrel ≈ 1.2–1.6 mm, head ≈ 1.8–2.4 mm at the root
  tapering to the tip), evenly pitched, rounded/chamfered tips so they catch
  light. Clumsy or thick fins fail instantly.
- Renderer facts (from look-dev): polished parts need curvature to show
  highlights (a flat polished face facing the camera reads dark); fins read
  through their tips; there is no real HDRI (a dark room + two light cards).

## Aesthetic rubric (priority order)

1. The head-on star is flawless: exact 40° symmetry across cylinders, pushrod
   tubes, rocker boxes, intake pipes and leads.
2. The crankcase window shows the master rod and eight articulating rods as a
   beautiful, legible mechanism.
3. Cooling fins thin, evenly pitched, deeper on the heads than the barrels.
4. Ignition leads route with deliberate rhythm from the harness ring to every
   plug — never draped or tangled.
5. Cast reads as cast, machined as machined, enamel as enamel.
6. Fastener and safety-wire discipline: consistent, deliberate patterns.
7. Exhaust collector and intake pipes sweep with smooth, generous bends, no kinks.
8. Propeller blades: true airfoil section, twist, crisp trailing edge.
9. Zero faceting, zero missing fillets, zero unblended intersections at render resolution.

Every part a real radial has must exist as a real body: every visible fastener,
safety wire, casting parting line, machined boss and lifting eye.

## Deliverable per builder

1. `src/lib/<name>.py` with `MATERIALS` and `build()`. Every leaf passes
   `geo.sound()` (check in a loop before you hand over) and is labelled and
   coloured. Prototype once, place copies (`geo.on_cylinder`, `.moved`) so
   repeated parts share geometry.
2. `python tools/engine.py system <name>` exits 0.
3. Clearances: ZERO interpenetration between ANY two leaves — within your own
   system too (every stud, bolt, pin and plug sits in a real drilled/bored hole;
   check pairwise boolean-common volume over your own leaves, AABB-prefiltered).
   Your static geometry must not touch any moving part at ANY crank
   angle, nor any neighbouring system. Use `kin` to sweep your moving neighbours
   (e.g. 0..720° in 10° steps) and `cadgen.geometry` / OCP distance checks.
   Report the minimum clearances you measured. Moving-part builders must sweep
   their parts against their moving neighbours over 720°.
4. Renders IN CONTEXT of the whole engine with the PRESENTATION envelope (never
   the default theme), largest size profile:
   ```json
   {"render": "presentation", "mode": "view",
    "outputs": [{"path": "tmp/<name>/front34.png",
                 "camera": {"position": [x, y, z], "target": [x, y, z]}}],
    "output": {"sizeProfile": "presentation-large", "padding": 0.04}}
   ```
   then `python tools/engine.py build-render tmp/<name>/job.json`. Camera
   position/target are engine-frame mm (also `"direction": [..], "zoom": z`).
   `"render": "presentation"` is substituted with `render/presentation.json`.
   READ every render you make. Do not loop on renders: rerender only after a
   change that alters what you are judging.
5. A short report: what you built, labels (groups), part count, checks run and
   minimum clearances, render paths, anything you could not make work. Be honest
   — a hidden fallback that changed the look is a bug.

After you report, a blind critic compares your renders against museum
photographs. On a loss you will receive exactly ONE gap to fix. Critics never
override kinematics: if a requested change would break motion or clearance, say
so and it will be replaced by a different gap.

## Performance and memory (the machine has run out of memory before)

- One multi-operand boolean, never long pairwise chains. Tools inside one cut
  must not overlap each other (fuse overlapping tools first, or cut in families).
- Fillet last; use the ladders in `castings.py`; never 3D-chamfer tangent chains.
- Build a prototype once and place copies; keep helix sweeps, threads and dense
  patterns light. A real-looking part beats a heavy one — but never fake detail
  with texture: fins, fasteners and wire are real bodies.
- Run ONE heavy Python process of your own at a time. Delete scratch STEPs
  when rendered. Several builders share this machine.
