# Turning: face, rough, finish, groove, thread, drill and part off on a lathe

Seven operations turn a round part from bar stock on a 2-axis lathe (`machine.kind` `lathe`). They
read the part's turned profile straight off the exact solid, so you name only what needs naming: a
groove, the thread's cylinder. Order them as a machinist would: face, centre drill or drill, rough
the outside and the bore, finish them, groove, thread, part off.

Read the part first: its round faces and holes, with their selectors, are what the profile is made
of.

```bash
cadgen cam features part.step
```

## A minimal job

A shaft along the part's Z, its front (the end away from the chuck) at the top of Z:

```json
{
  "machine": {"kind": "lathe", "post": "fanuc", "max_rpm": 4000, "travel_mm": [200, 300]},
  "material": "aluminum-6061",
  "stock": {"kind": "cylinder", "diameter_mm": 40, "length_mm": 75, "face_stock_mm": 1},
  "tools": [
    {"id": "T1", "type": "turn", "insert": "C", "nose_radius_mm": 0.4},
    {"id": "T2", "type": "turn", "insert": "V", "nose_radius_mm": 0.2},
    {"id": "T3", "type": "groove", "width_mm": 3},
    {"id": "T4", "type": "thread", "pitch_mm": 1.5},
    {"id": "T5", "type": "partoff", "width_mm": 3},
    {"id": "T6", "type": "drill", "diameter_mm": 8},
    {"id": "T7", "type": "turn", "insert": "D", "nose_radius_mm": 0.2, "diameter_mm": 6}
  ],
  "setups": [
    {"id": "turn", "orientation": "+Z", "origin": "stock-top-center", "operations": [
      {"op": "turn_face", "tool": "T1"},
      {"op": "turn_drill", "tool": "T6", "peck_mm": 5},
      {"op": "turn_rough", "tool": "T1"},
      {"op": "turn_rough", "tool": "T7", "side": "id"},
      {"op": "turn_finish", "tool": "T2", "face": true},
      {"op": "turn_finish", "tool": "T7", "side": "id"},
      {"op": "turn_groove", "tool": "T3"},
      {"op": "turn_thread", "tool": "T4", "faces": ["#o1.f13"]},
      {"op": "turn_partoff", "tool": "T5"}
    ]}
  ]
}
```

```bash
cadgen cam plan part.step --job part.cam.json
```

## The lathe's frame

- The setup's `orientation` names the part axis the spindle turns about (`+Z`: the part's Z, its
  +Z end facing the tailstock); the bar's `axis` must be the same letter.
- The WCS is X = radius, Z along the spindle, the chuck at negative Z. `origin`
  `stock-top-center` (the default) puts Z0 on the bar's front face; `part-top-center` on the part's
  front face; `{"xyz": [...]}` anywhere on the axis. `stock-top-corner` is refused (a lathe's zero
  sits on the spindle axis).
- Toolpaths are stored as radii; the post writes X as a diameter (`machine.diameter_mode`, default
  true). Every point is the tool's controlled point (below), already compensated for the nose
  radius: the post writes G40, never G41/G42.
- One setup per chucking. To turn the other end, add a second setup with `"orientation": "-Z"`;
  the simulator carries what the first one cut.

## The bar

`stock` is a `cylinder`: `diameter_mm`, `length_mm`, `axis`, `margin_mm` and, on a lathe,
`face_stock_mm`: how far the bar stands proud of the part's +axis end (default 1 mm on a lathe). The
bar is centred on the part's own turning axis (the line its round faces share) and runs
`length_mm` back from its front: give the part, the face stock, the part-off blade's width and what
the chuck holds. Left out, the diameter is the part's plus `margin_mm`, the length the part's plus
the face stock. Box or STEP stock is refused on a lathe.

## Tools

| `type` | own keys | the controlled point (where its offsets are touched off) |
| --- | --- | --- |
| `turn` | `insert` (`C` 80°, `D` 55°, `V` 35°, `W` 80° trigon; default C), `nose_radius_mm` (default 0.4), `side` (`right`, the default, or `neutral`) | the imaginary tip: the nose's lowest X and lowest Z (a neutral tool: its lowest X, its centre's Z) |
| `turn` as a boring bar (`side: "id"` on the operation) | the same, and `diameter_mm` (the bar; half of it is how far it stands inward of the nose) | the nose's highest X and lowest Z |
| `groove` | `width_mm`, `nose_radius_mm` (the blade's corners) | the tip corner on the chuck side: the blade cuts from there `width_mm` towards the front |
| `partoff` | `width_mm` | the same |
| `thread` | `pitch_mm` | the tip of the 60° insert |
| `drill`, `spot` | `diameter_mm`, `point_angle` / `angle_deg` | the point, on the axis |

The insert's shape matters: the holder's lead angle (95° for C and W, 93° for D and V) and the
nose angle leave an end clearance (5° for C and W, 32° for D, 52° for V), and the path never lets
the insert's edges rub a profile that falls away more steeply than that. A left-hand tool (cutting
towards the tailstock) is refused.

## Feeds

Turning runs at constant surface speed (G96) with the rpm capped at `machine.max_rpm` (3000 when
the job names none, and the note says so), and feeds per revolution (G95). The table gives a
carbide insert's surface speed and roughing/finishing feeds per material
([job-file.md](job-file.md#material)): the finish runs 1.2x faster at no more than half the nose
radius a revolution, a groove 0.7x, a part-off 0.6x, a thread 0.5x. Each operation takes:

| key | meaning |
| --- | --- |
| `css_m_min` | the surface speed (m/min) instead of the table's |
| `feed_mm_rev` | the feed per revolution instead of the table's |
| `speed` | a constant rpm instead of CSS (shared key) |
| `feed` | mm/min at the operation's reference rpm (shared key; `feed_mm_rev` is clearer) |

A thread always runs at a constant rpm with the feed one pitch a revolution; a drill takes the
drilling table at a constant rpm. The times assume the rpm at the operation's working diameter.

## `turn_face`: Face

Takes the front of the bar down to the part's front face (or `z_mm`) in passes towards the axis,
starting outside the bar and running past the centre by the nose radius.

| key | meaning |
| --- | --- |
| `z_mm` | the faced front, WCS (default the part's front face plus `allowance_z_mm`). Below the part's front it cuts into the part: the note says so and the gouge check flags it |
| `doc_mm` | most taken off a pass, axially (default the material's roughing depth) |
| `allowance_z_mm` | left on the face for a finish (default 0) |
| `x_end_mm` | where each pass ends (default minus the nose radius: no pip at the centre) |

## `turn_rough`: Rough turn

Passes along Z towards the chuck at radial levels `doc_mm` apart, each ending where the insert
(nose, edges, holder) would touch the profile plus its allowance, pulled off at 45°; then one pass
along the profile at the allowance to take off the steps. It starts from the stock as everything
before it left it. A profile that only steps outward is also carried as a G71 cycle a post may emit
(`machine.cycles`, see [posts.md](posts.md)).

| key | meaning |
| --- | --- |
| `side` | `od` (the outside, the default) or `id` (a bore) |
| `doc_mm` | radial depth a pass (default the material's: 2 mm in aluminium, 1.5 in mild steel; 0.6 of it in a bore) |
| `retract_mm` | the 45° pull-off after each pass (default 0.5) |
| `allowance_x_mm`, `allowance_z_mm` | left for the finish, radially and axially (default `stock_to_leave_mm`, else 0.2 and 0.1) |
| `beyond_mm` | how far past the part's back end the profile is carried, so the part-off line is clean (default the nose radius plus 0.5, as far as the bar reaches) |
| `cleanup` | the profile-following pass (default true) |
| `reach_mm` | a boring bar: how far its body stands inward of the nose (default half its `diameter_mm`, else 3) |

A bore needs a hole to start in: `turn_drill` it first (at least `reach_mm` plus two nose radii
across), or the job is refused. Its passes also stop short of material the bar would run into (the
drill's point). What the insert cannot reach from the front (grooves, undercuts) is left and named
in the note with its Z range: plunge it with `turn_groove`.

## `turn_finish`: Finish turn

One pass along the finished profile (front to back), compensated for the nose radius, the insert's
clearance kept: on a straight diameter the controlled point runs exactly at the radius, on a face at
its Z, and round a chamfer or radius the nose rolls on the surface.

| key | meaning |
| --- | --- |
| `side` | `od` or `id` |
| `face` | start with a pass across the front face from the centre (or from the bore); `od` only (default false) |
| `spring_passes` | the same pass again, 0 to 5 (default 0) |
| `beyond_mm`, `reach_mm` | as for `turn_rough` |

`stock_to_leave_mm` leaves that much all round. A finish that would take more than 1 mm (or four
times the stock to leave) in one cut says so: rough first.

## `turn_groove`: Groove

A groove is a stretch of the profile lower than the part on both sides of it (or, in a bore, wider):
relief grooves, ring grooves, undercuts. Which grooves: those holding the named `faces` (the floor
or a wall), those at `z_mm`, else every one on that side. Each is plunged from its front wall back,
plunges overlapping by a fifth of the blade, so its walls are cut exactly; each plunge goes as deep
as the blade (corner radii included) can over the floor beneath it, with a dwell at the bottom.

| key | meaning |
| --- | --- |
| `side` | `od` or `id` |
| `z_mm` | a WCS height (or a list) inside the groove(s) to cut |
| `allowance_mm` | left on the floor and walls (default `stock_to_leave_mm`) |
| `peck_mm` | back off every so deep to break the chip (default none) |
| `dwell_s` | at the bottom of each plunge (default two revolutions) |

A groove narrower than the blade is refused; so is a name or height with no groove there (the
refusal lists the grooves).

## `turn_thread`: Thread

Single-point threads a cylinder in passes of decreasing depth (each takes the same chip area: the
depth times the square root of its share), then spring passes at full depth.

| key | meaning |
| --- | --- |
| `side` | `od` (outside) or `id` (inside) |
| `pitch_mm` | the lead (default the tool's) |
| `major_diameter_mm` | an outside thread's major diameter (instead of a face) |
| `minor_diameter_mm` | an inside thread's minor diameter, or an outside thread's root |
| `depth_mm` | radial thread depth (default ISO 60°: 0.6134 x pitch outside, 0.5413 x pitch inside) |
| `z_start_mm`, `z_end_mm` | the thread's front and back ends, WCS (instead of a face's ends) |
| `lead_in_mm` | run-up in front of the thread so Z is at speed (default three pitches, at least 2 mm) |
| `infeed` | `flank` (the default: each pass shifts towards the chuck along the trailing flank at 29.5°, so only the leading edge cuts), `radial`, or `alternate` (flanks in turn) |
| `passes` | cutting passes (default from `first_depth_mm`) |
| `first_depth_mm` | the first pass (default 0.3, or a third of the depth) |
| `min_depth_mm` | the smallest a pass may take (default 0.03) |
| `spring_passes` | at full depth (default 1) |

Name the thread with `faces` (its major-diameter cylinder outside, the bore inside) or with
`z_start_mm`, `z_end_mm` and a diameter. The diameter must already be turned (it is refused while
stock stands proud of it), and the thread must run out into a groove or off the part, not into a
shoulder. The toolpath carries a `thread` cycle so the post writes G76 (or synchronised G32/G33
passes); the threading moves are never posted as plain feeds. The simulated stock does not show the
helical groove, and the checks do not judge it.

## `turn_drill`: Centre drill

A centre hole or a drilled hole on the axis, the drill held still and the part turning.

| key | meaning |
| --- | --- |
| `depth_mm` | below the material's face, to the point |
| `z_mm` | the point's WCS height, instead of a depth |
| `peck_mm` | peck so deep, back out to the R plane after each (G83) |
| `chipbreak` | with `peck_mm`: back off a little instead (G73) |
| `dwell_s` | at the bottom (a centre drill's default 0.2 s) |
| `beyond_mm` | a through bore: how far past the part's back end the full diameter goes (default 1) |

Without a depth, a `spot` (centre) drill goes in until its countersink is 0.8 of its diameter
across, and a `drill` follows the part's bore: through it (and `beyond_mm` past the part) for a
through bore, its point on the floor of a blind one (the cone left there is material left until a
boring bar faces it). A drill wider than the bore is refused.

## `turn_partoff`: Part off

Plunges a part-off blade at the part's back end and backs straight out once the part is off.

| key | meaning |
| --- | --- |
| `z_mm` | the part's side of the cut, WCS (default the part's back end); the blade cuts behind it |
| `x_end_mm` | where the blade stops (default 0.2 mm past the centre, or just inside a bore that runs through) |
| `peck_mm` | back off every so deep to break the chip |
| `slow_diameter_mm` | below this diameter the feed drops (default a quarter of the bar, at least 3 mm) |
| `slow_factor` | that feed's share (default 0.5) |

A bar too short to hold the blade behind the part is refused: lengthen `length_mm`.

## What it checks

- **The part.** The profile is the part cut by four planes through the spindle axis, the union of
  the half-sections (its max-radius envelope; a pin sticking out between the cuts is caught from
  the mesh). A part under 30% of whose surface turns about the axis is refused, with the axis its
  round faces do share. Faces that do not turn about the axis (cross holes, flats, keyways) are
  named once in a note: they need live tooling or a mill and are left uncut.
- **`gouge`** sweeps each operation's tool shape (nose, edges, holder; the blade; the drill) through
  its cutting moves against that profile: any cut into it is an error, with how deep.
- **`rapid_into_stock`**: the lathe simulator (the bar's half-section, cut by the same shapes)
  flags any rapid whose tool overlaps uncut material.
- **`material_left`**: stock proud of the profile after the whole job (behind the part, towards
  the chuck, is bar and does not count): volume, section area, how proud and where.
- **`reach`** judges a drill's depth against its flutes; **`travel`** a lathe's X as a diameter.

## Reading the result

Rows read `Rough turn OD with T1 C insert turning tool, 26 s · 2390 rpm · 597.5 mm/min`, `Groove
Z-20..-17, Z-33..-29 with T3 3 mm grooving tool`, `Thread M20x1.5 outside Z-2..-17 with T4 threading
tool`. A `warning:` line carries each note: grooves an insert left, off-axis faces, a heavy finish,
a clamped spindle. `adapted:` lines are rare on a lathe (the section is exact; only the drawing of
long programs thins).

## Limits

- Right-hand and neutral tools cutting towards the chuck only; no left-hand tools, no back turning.
- Roughing is along Z (type I: pockets past a shoulder are left for `turn_groove`); there is no
  facing-direction roughing (G72) and no pattern-repeat roughing (G73) of castings.
- A thread is straight (no taper), single-start, 60° geometry by default; its groove is not
  simulated.
- The stock is simulated as a body of revolution, so off-axis features show as uncut.
- No live tooling, sub-spindle, C axis or Y axis: mill those features in a mill setup.
- A boring bar's body is modelled as its insert's reach inward of the nose and straight out along
  Z; a bar wider than that, or a bore smaller than the bar, is not checked beyond the hole it needs
  to start.
