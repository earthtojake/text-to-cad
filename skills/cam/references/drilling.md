# Drilling: drill, peck, tap, ream, bore, spot and counterbore holes

One operation, `drill`, cuts round holes along the setup's Z in canned cycles: spot them, drill or
peck them, tap, ream or bore them, counterbore them from the top or back bore a counterbore on their
far side. Each is its own operation in the job, one tool each, usually in that order. The posted file carries the controller's cycles (G81, G83, G84, ...) where the post has
them, and the same moves spelled out where it does not (GRBL has none).

Read the holes first: `cadgen cam features` lists each one with its diameter, depth, through or
blind, its axis, the directions that reach it (`reach`: a hole whose opening the part covers, under
a roof or a ledge, is reached from no side above it) and the face selectors of its faces. A
counterbore or countersink is part of the hole under it (`counterbore` `{diameter_mm, depth_mm}`,
`countersink` `{diameter_mm, angle_deg}`): the hole opens, and its depth runs, from the top of the
counterbore or countersink. A blind hole's drawn drill point is measured (`point_mm`).

```bash
cadgen cam features part.step
```

## A minimal job

Spot every hole, peck the 5 mm through holes, tap them M6:

```json
{
  "machine": {"kind": "mill", "post": "grbl", "travel_mm": [300, 200, 80], "max_rpm": 24000},
  "material": "aluminum-6061",
  "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
  "tools": [
    {"id": "T1", "type": "spot", "diameter_mm": 6},
    {"id": "T2", "type": "drill", "diameter_mm": 5},
    {"id": "T3", "type": "tap", "diameter_mm": 6, "pitch_mm": 1}
  ],
  "setups": [
    {"id": "top", "orientation": "+Z", "origin": "stock-top-center", "operations": [
      {"op": "drill", "tool": "T1", "holes": "all"},
      {"op": "drill", "tool": "T2", "holes": {"diameter_mm": 5}, "cycle": "peck"},
      {"op": "drill", "tool": "T3", "holes": {"diameter_mm": 5}}
    ]}
  ]
}
```

```bash
cadgen cam plan part.step --job part.cam.json
```

## Which holes

Name them one way per operation:

| key | meaning |
| --- | --- |
| `faces` | any face of the hole (`#o1.f7`: a wall, either half of a split hole, the counterbore's wall or shoulder, the countersink, a blind hole's floor names the hole). Each must run along the setup's Z (a through hole either way); one that does not is refused with the setup, or the `orientation`, that would reach it. A hole whose opening the part covers from this side is `unreachable`; a tool bigger than the hole (past `size_tolerance_mm`; a tap whose tap drill is more than 0.15 mm over the hole) is `tool_too_large` |
| `holes` | `"all"`: every hole this setup reaches and the tool suits (holes along other axes, covered holes and holes the tool is too big for are left, and the note counts them; none left is `empty_operation`); or `{"diameter_mm": 5, "tolerance_mm": 0.05}`: those of one size |
| `points` | `[[x, y], ...]` in the setup's WCS (mm from its origin), with `depth_mm`. A point where the model has no hole is drilled anyway and said once as a `no_hole_in_model` warning |
| `top_z` | with `points` only: the holes' top in WCS. Left out, the part's top at each point (else the stock's top) |

A hole along X or Y needs its own setup (`"orientation": "+X"`); a hole at an angle needs a tilted
one ([multi-axis.md](multi-axis.md)).

## The cycle

`cycle` picks what the tool does in each hole. Left out, the tool decides: a drill or flat end mill
`drill` (or `peck` when the deepest hole is three diameters or more), a spot or chamfer tool `spot`,
a tap `tap`, a reamer `ream`, a boring bar `bore`, a counterbore `counterbore`.

| `cycle` | posted as | tools | what it does |
| --- | --- | --- | --- |
| `drill` | G81 | drill, flat, spot | feed to depth, rapid out |
| `dwell` | G82 | drill, flat, spot | feed to depth, wait `dwell_s` (default 0.5 s), rapid out: clean spot faces |
| `peck` | G83 | drill, flat | pecks of `peck_mm` (default one diameter) from the R plane, back to R after each to clear chips, then down to 0.5 mm over the last depth |
| `chipbreak` | G73 | drill, flat | pecks of `peck_mm` (default half a diameter), backing off `retract_mm` (default 0.2) after each to break the chip |
| `tap` | G84, G74 for a left-hand tap | tap | feed at exactly rpm x the tap's pitch, reverse the spindle at the bottom, feed out; `rigid` says the tap holder (below) |
| `ream` | G85, or G89 with `dwell_s` | reamer | feed in, (wait,) feed out |
| `bore` | G85, G89, G86 or G76 by `bore_mode` | boring | see below |
| `spot` | G82 (dwell `dwell_s`, default 0.2 s) | spot, drill, chamfer | a short cone to start the drill true, `spot_diameter_mm` wide at the hole's top (default the countersink's diameter, else the hole's, else half the tool at a point), or `depth_mm` deep (not both). A spot wider than the tool is refused (a default one is `tool_too_small` on a named hole, and `holes` leaves it out); one past a blind hole's deepest point is `too_deep` |
| `counterbore` | G82 (dwell `dwell_s`, default 0.2 s) | counterbore, flat | the hole's counterbore from the top: the cutter's face down to its floor, the pilot in the hole below; see below |
| `back_bore` | G87 (Haas G77) | boring | a counterbore on the far side of a through hole, from the top: the bar's head through the hole and up into it; see below |

`bore_mode`: `feed` (G85, feed out; the default), `dwell` (G89, wait `dwell_s`, feed out), `stop`
(G86, spindle stop, rapid out), `fine` (G76: oriented spindle stop, shift `shift_mm`, default 0.1,
off the wall along `shift_xy` (`[x, y]` in the setup's plane, default `[1, 0]`, normalised; `[0, 0]`
is refused), rapid out, shift back). A shift of the hole's radius or more is a `gouge`.

A left-hand tap says so on the tool: `{"id": "T3", "type": "tap", "diameter_mm": 6, "pitch_mm": 1,
"hand": "left"}`; the spindle runs backwards into the hole.

`rigid` (a tap only) says what holds the tap. Left out, the post writes its controller's own tapping
cycle, as it always has: rigid on Fanuc (`M29 S`, then G84), Haas (G84) and LinuxCNC (`G33.1`), and
Mach3's G84, which does not follow the spindle and so wants a floating holder. `true`: the feed must
be synchronised to the spindle (a rigid holder); Mach3 cannot, so it refuses the tap
(`no_post_support`). `false`: a floating (tension-compression) holder: Fanuc's G84 without `M29`,
LinuxCNC's own G84 (G74 left hand) instead of `G33.1`, Haas and Mach3 their G84. GRBL taps neither
way. The planned moves are the same either way. On a machine that does not tap rigidly
(`machine.rigid_tap` false, or its model says so) a tap left out is floating, and `true` is refused.

## Counterbores and back bores

`cadgen cam features` reads a counterbore as part of the hole under it (`counterbore`
`{diameter_mm, depth_mm}`); on a through hole it may open at either end. The two cycles cut it:

- `counterbore` (G82): a `counterbore` tool (its `pilot_diameter_mm` pilot, as long as it is wide,
  leads it down the hole) or a flat end mill the counterbore's size (no pilot) goes down until its
  face is on the counterbore's floor (its depth from the features, or `depth_mm` below the hole's top),
  dwells `dwell_s` (default 0.2 s) and comes out. Only a counterbore that opens toward the tool.
- `back_bore` (G87; Haas's G77): a counterbore on the far side of a through hole, cut from the top
  with a back-boring bar (a `boring` tool): the head is its `diameter_mm` and its `flute_length_mm`
  tall, and its `shank_diameter_mm` is the thin neck that goes through the hole. At the initial level
  the spindle stops oriented, the bar shifts `shift_mm` (required) along `shift_xy` (`[x, y]` in the
  setup's plane, default `[1, 0]`) so the head passes through the hole, rapids down to its R plane
  under the stock (`retract_mm` under the stock's bottom, less the head), shifts back, starts the
  spindle, feeds up until the head's top is on the counterbore's shoulder, waits `dwell_s` (none by
  default), feeds back down to R, stops oriented, shifts, rapids up out of the hole to the initial
  level, shifts back and starts the spindle. It always returns to the initial level (G98).
  `shift_mm` must be at least half the head's diameter less the hole's plus 0.1 mm, and less than
  the hole's radius by at least half the neck.

What each refuses on a named hole (`holes` leaves such holes out and says why in the note, and is
`empty_operation` when none is left):

| refusal | when |
| --- | --- |
| `empty_operation` | the hole has no counterbore |
| `unreachable` | `counterbore`: its counterbore is on the far side (back bore it, or cut it from a setup facing that side); `back_bore`: the hole is blind, or its counterbore opens toward the tool |
| `tool_too_large` | the cutter is more than `size_tolerance_mm` over the counterbore; a pilot wider than the hole; a back bore's shift too small to pass the head through the hole, or a neck (`shank_diameter_mm`, which defaults to the head's diameter: state it) that does not fit through the hole shifted |
| `tool_too_small` | the cutter is more than `size_tolerance_mm` under the counterbore (pocket or helix bore it instead) |
| `too_deep` | a pilot that would go past a blind hole's bottom (use a shorter pilot, or a flat end mill) |
| `gouge` | a back bore's `shift_mm` of the hole's radius or more |

`holes` `{"diameter_mm": ..}` picks by the hole's diameter, not its counterbore's. `depth_to` and
`breakthrough_mm` do not apply to either; a back bore takes no `points`, no `depth_mm` and no
`return_to` but `initial`.

## How deep

| key | meaning |
| --- | --- |
| `breakthrough_mm` | a through hole: how far the full diameter goes past the exit (default 1). The tip goes the point's length further (5 mm drill, 118°: 1.5 mm) |
| `depth_to` | a blind hole: `tip` stops the drill's tip on the floor (a flat floor keeps a ring of material at its edge); `shoulder` stops its full diameter there. The default is `shoulder` when the model draws a drill point below the floor, else `tip` |
| `depth_mm` | how deep below each hole's top, overriding the above (to the tip, or the shoulder with `depth_to`). Required with `points` (except for a spot) |

A blind hole's deepest point (its drawn point's tip, else its floor) is a hard floor: the tip never
goes below it, whatever `depth_to` says, and a `depth_mm` past it is `too_deep`. Where the floor is
flat, or its drawn point is shorter than the tool's, the full diameter stops short of the floor and a
`hole_floor` warning says by how much: finish the floor with an end mill if it matters.

A tap's depth is set by the hole: it stops one pitch above a blind hole's floor, and runs three
pitches of lead past a through hole's exit plus `breakthrough_mm`. `depth_to` does not apply to it;
`depth_mm` does.

## Moving between holes

Each hole starts at its R plane: the setup's `retract_mm` (default 2) over the hole's top, or over
the stock for holes on the part's top face. The tool waits over the first hole at the initial level,
`retract_mm` over the stock.

| key | meaning |
| --- | --- |
| `return_to` | `auto` (the default): back to R between holes (G99) when every straight move between them at R clears the part, else to the initial level (G98); `r_plane` or `initial` force one |
| `order` | `shortest` (the default): nearest hole first, then improved by 2-opt; `given`: in the order named |

Holes with one depth and one R plane in a row are one canned cycle; between cycles the tool climbs
to the initial level before it moves across. Past 3000 holes the order is nearest-first only, and
the note says so.

## Feeds

From the material table as for any operation ([job-file.md](job-file.md#material)): drills by feed
per revolution, spots slower, reamers at half speed, taps at a fifth with the feed locked to rpm x
pitch. `speed` overrides the rpm; `feed` overrides the feed, except on a tap, which is refused (set
`speed`; the feed follows it).

## What it checks

As findings in the result (`check` `drill`, warnings), besides the shared checks
([checks.md](checks.md)):

| `type` | meaning |
| --- | --- |
| `hole_size` | the tool is more than `size_tolerance_mm` (default 0.05) under the hole's diameter, so the hole comes out small (oversize is `tool_too_large`, not planned). A drill one pitch under a hole drawn at its thread size says it is the tap drill |
| `hole_floor` | the full diameter stops short of a blind hole's floor by the amount it says (a flat floor, or a drawn point shorter than the tool's) |
| `tap_thread` | the tap's pitch is not a standard one for its size (M6: 1 or 0.75), or the hole is not drawn for it: an M6x1 tap wants a Ø5 hole (the tap drill) or a Ø6 one (drawn at the thread size) |
| `no_hole_in_model` | a point drills where the model is solid |

`reach` (an error) compares how deep the tool goes below the material beside it with its
`flute_length_mm` (a drill's default is ten diameters, a spot drill's one). The `gouge` check (an
error) judges the tool's whole body up its flutes, not just its point. A tap is judged as its core (the thread's minor diameter,
`d - 1.2269 P`, for an M6x1 4.77 mm), since its thread form cuts the wall on purpose: a tap run into
material past its hole is a gouge. Point holes in solid material are not judged (said above).

Holes along one axis line are split where material stands between them: two blind holes drilled
from either side of a web are two holes, each blind, never one through hole.

## Reading the result

Each drill operation's row reads `Peck drill 4 holes with T2 5 mm drill, 20 s`, with its rpm and
feed. Its note (a `warning:` line) says what was left out: holes along another axis, covered holes,
holes the tool is too big for. A tap feeds at the posted `S` times the pitch exactly. A post that
cannot tap (GRBL, a post with `cycles` off, a 5-axis program under tool centre point, Mach3 with a
left-hand tap) refuses it: a `no_post_support` error, no G-code; thread mill the hole
(`thread_mill`) or use a post that taps. A fine bore that shifts its bar posts as G76 with its
shift on Fanuc (when the shift is +X) and Haas (`I J`), as moves with an oriented stop (`M19`) on
LinuxCNC (and Fanuc for another direction), and is refused on Mach3 and GRBL, which cannot orient
the spindle; the file's header says which way the bar's tip must point. A back bore posts the same
way: `G87 ... Q` on Fanuc (a +X shift, its dwell as `P`), `G77 ... I J` on Haas (without a dwell:
G77 takes none), and otherwise as its moves with an oriented stop (`M19`) before each shift
(LinuxCNC, Fanuc for another direction, Haas with a dwell, `cycles: false`); Mach3 and GRBL refuse it.

## Limits

- Holes run along the setup's Z only; there is no cross-hole or angled-hole drilling within a setup.
- On a controller's own G73 the back-off distance is the controller's setting, not `retract_mm`
  (the expanded moves use `retract_mm`).
- A counterbore or countersink is part of its hole: the `counterbore` and `back_bore` cycles cut the
  counterbore (or pocket or helix bore it), and a spot the countersink (`spot_diameter_mm` defaults
  to it). A spot on a counterbored hole with no countersink starts at the counterbore's top, so it
  cuts air.
- The stock simulator follows a back bore: a move made with the spindle stopped cuts nothing, and
  the back bore's stopped moves (down through the hole, across under the part, back up) are judged
  for `rapid_into_stock` with the neck's radius (`shank_diameter_mm` / 2), so the hole must be
  drilled through by an earlier operation; the head feeding up cuts the counterbore from under the
  part, never the material over it. The oriented head's own passage through the hole is the
  planner's (the shift against the head, the neck and the hole). `reach` judges the bar's
  `stickout_mm` (the holder must stay over the stock's top with the head down at R), not its flutes
  (the head rises through the counterbore). The bar under the part is a `through_stock_bottom`
  warning: leave room under the hole. The `gouge` check skips the back bore (the planner checks
  the head against the counterbore and the hole). The `uncut_feature` check does not see that a
  `counterbore` cycle cuts its counterbore's floor (the tool's tip runs on the hole's axis), and may
  warn of it as a pocket left.
