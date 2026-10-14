# 2.5D milling

Flat floors, straight walls, holes and edges, cut in levels with the tool along Z: `face`, `contour`,
`pocket`, `adaptive`, `slot`, `chamfer`, `engrave`, `vcarve`, `helix_bore`, `circular`, `trace` and
`thread_mill`. Drilling is
[drilling.md](drilling.md); curved surfaces are [milling-3d.md](milling-3d.md). The keys every
operation shares (`tool`, `faces`, `region`, `feed`, `speed`, `stepdown_mm`, `stepover`,
`stepover_mm`, `stock_to_leave_mm`, `coolant`, `name`) are in [job-file.md](job-file.md#operations).

Read the part first: every face this page names comes from it.

```bash
cadgen cam features part.step
```

Coordinates in a `region`, a `path` or `holes` are the setup's work coordinates (WCS): with the
default origin `stock-top-center`, Z 0 is the top of the stock and the part is below it.

A minimal job: face the top, cut a slot, bore a hole, profile the outline out with tabs.

```json
{
  "machine": {"kind": "mill", "post": "grbl", "max_rpm": 24000},
  "material": "aluminum-6061",
  "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
  "tools": [
    {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 15, "stickout_mm": 30},
    {"id": "T2", "type": "flat", "diameter_mm": 4, "flutes": 3, "flute_length_mm": 14}
  ],
  "setups": [{"id": "top", "operations": [
    {"op": "face", "tool": "T1"},
    {"op": "slot", "tool": "T2", "faces": ["#o1.f14"]},
    {"op": "helix_bore", "tool": "T1", "faces": ["#o1.f8"]},
    {"op": "contour", "tool": "T1", "faces": ["#o1.f3"], "loops": "outer", "tabs": {"count": 4}}
  ]}]
}
```

```bash
cadgen cam plan part.step --job job.cam.json
```

## face: Face

Takes the top of the stock down flat to the part's top in parallel passes that start and end
outside the stock. Flat, bull or `face_mill` tool. Stepover defaults to 0.4 of an end mill's
diameter and 0.7 of a face mill's. Zigzag rows stay down across their turns; `one_way` rows lift
0.5 mm, come back over the row just cut and ramp down into the next. A row that cannot start in air
(off the stock and clear of the fixtures) ramps in along itself at 3°. Facing below the part's top
is refused (`too_deep`), a face with nothing to take off is `empty_operation`.

| key | meaning |
| --- | --- |
| `depth_mm` | how far below the stock top to face (default: down to the part's top plus the stock to leave) |
| `pattern` | `zigzag` (default) or `one_way` (every pass climb, the same way) |
| `angle_deg` | the passes' direction in the XY plane (0 runs along X) |
| `region` | face only inside this polygon: the tool's centre stays 0.8 of its radius inside, so it hangs over the edge by a tenth of its diameter at most (a region too small for that is `tool_too_large`) |

## pocket: Pocket

Clears a pocket down to its floors by rings offset inward, innermost first, level by level. Name
its floor faces (naming the deepest floor of a stepped pocket clears the steps above it too) or a
`region` with `bottom_z`. Islands are walked round. Stepover defaults to 0.4 of the diameter.

| key | meaning |
| --- | --- |
| `entry` | `helix` (default), `ramp` or `plunge`: how each level is entered (a helix falls back to a ramp, then a plunge) |
| `ramp_angle_deg` | the entry's ramp angle (default 3) |
| `direction` | `climb` (default) or `conventional` |
| `finish_mm` | leave this much on the walls and take it off in one ring at the floor, entered from the area just cleared |
| `finish_floor_mm` | leave this much on the floor and take it off in a last level of its own, whose outer ring finishes the walls |

A tool that cannot enter a level of the pocket is refused (`tool_too_large`, naming the level),
never left to cut it short. Its `full_slot_mm` fact is the length cut at the tool's full width (the
links between rings into uncut material), which the `full_slot` warning reads.

## contour: Profile

Follows a shape's loops at the tool's radius, level by level from the stock top. A flat face square
to the tool names its outline and its holes; a wall (a plane standing square to XY, a cylinder or
cone along Z) names the whole loop it stands on, on its air side; or give a `region`.

| key | meaning |
| --- | --- |
| `side` | `outside` (the tool's edge on the loop, outside the shape), `inside` or `on` (the tool's centre on it). A face's default is `outside`; a floor below the part's top defaults to `inside` (its walls); a wall's side is its air side |
| `loops` | a face's `all` (default), `outer` (the outline only) or `inner` (its holes only) |
| `bottom_z` | how deep, WCS. Default: a wall's foot, a floor's height (inside), or whatever lies under the tool (a blind slot's floor), else the part's bottom (cut through) |
| `through_mm` | go this much below a cut through (default 0: nothing below the part is cut). Give 0.2 to 0.5 mm to break through cleanly when the part sits on parallels or a spoilboard, and add the support as a `fixture` box if it could be hit |
| `tabs` | `{"count": 4, "width_mm": 5, "height_mm": 1.5}`: bridges left on a cut through, evenly spaced (default width 5, height a third of the cut, at most 2 mm) |
| `lead_in_mm`, `lead_out_mm` | radius of a tangent quarter-arc lead onto and off the loop from the air side (default 0: none); the descent is then made at the lead's start |
| `finish_mm` | leave this much for the levels and take it off in one last full-depth pass |
| `finish_passes` | split the finish into this many equal passes (0 to 10; default 1 with `finish_mm`); without `finish_mm`, spring passes at the final offset |
| `entry` | `ramp` (default: zig-zag down along the loop itself) or `plunge` |
| `ramp_angle_deg` | the ramp's angle (default 3) |
| `direction` | `climb` (default) or `conventional` |

Holes are cut before the outline that holds them. A loop smaller than the tool is skipped and said
(all of them: `tool_too_large`). The tool rises onto each tab and ramps down off its end along the
loop at `ramp_angle_deg`, never dropping into the material. A lead that would swing into a fixture
is shortened, then left out. Tell the user to cut the tabs by hand after the program.

## adaptive: Adaptive clear (lite)

Clears a pocket or an open area at a capped tool load, cutting only where material stands. Name it
like a pocket: floor `faces`, or a `region` with `bottom_z`; an open side clears out to the stock's
edge. It reads the stock as it stands (every earlier operation and setup replayed): what an earlier
operation cut is air, and a level with nothing left is skipped. Each level grows the cleared area
from that air, or from a helix at the region's most open point where there is none, one stepover at
a time (each new pass is the cleared area offset by the stepover, clipped to the region), so no point
of a pass is more than a stepover from material already cut; only the stretches that meet new
material are cut, nearest first, so the tool works one side on before it crosses to the other.
Stepover defaults to 0.15 of the diameter (more than 0.5 is refused); step down to twice the
material's (deep and light), within the flutes. Flat or bull tool. Its result's `air_fraction` is the
share of the cutting path that removes nothing (with `air_mm` and `cut_mm`): quote it when the user
asks how efficient the path is.

| key | meaning |
| --- | --- |
| `direction` | `climb` (default) or `conventional` |
| `ramp_angle_deg` | the helix entry's angle (default 3) |

Its limits, which its result carries (quote them): it is not a true medial-axis adaptive solver; a
pass round a small cleared area cuts up to about twice the stepover's worth per millimetre (the first
ring round an entry); a piece too narrow for a helix is ramped into along its outline at full width;
the stock as it stands is read on a grid (0.1 to 0.5 mm), so the first pass beside an earlier cut
can run up to a cell in air.

## slot: Slot

Cuts a slot along its centreline, each level entered by a ramp along the centreline. Give one of: a
`path`, the slot's floor in `faces`, or its outline as a `region` (a straight stadium or rectangle:
its long axis is the centreline, its short side the width). A slot wider than the tool is widened in
loops round the centreline, a stepover (default 0.4 of the diameter) at a time; a tool wider than the
slot is refused. An open slot is cut back and forth.

| key | meaning |
| --- | --- |
| `path` | `{"points": [[x, y], ...], "bottom_z": z}`: the centreline, any shape (closed when its last point is its first) |
| `width_mm` | the slot's width (default: the tool's diameter for a path, the floor's or region's own width) |
| `entry` | `ramp` (default) or `plunge` |
| `ramp_angle_deg` | the ramp's angle (default 3) |
| `direction` | `climb` (default) or `conventional`, for the widening loops |

## chamfer: Chamfer

Breaks the top edges of a face's loops (or a wall's top edge, or a `region`'s outline at its
`bottom_z`) with a `vee`, `chamfer`, `engraver` or `spot` tool, in one pass on the air side. The
depth comes from the tool's angle: a cone of half angle a cuts `width / tan(a)` deep (a 90° vee: as
deep as wide). The modelled part has sharp edges there, so the gouge check does not judge a chamfer.

| key | meaning |
| --- | --- |
| `width_mm` | the chamfer's width across the top face (required) |
| `ramp_angle_deg` | the entry ramps down along the loop at this angle (default 3) |
| `tip_offset_mm` | put the tip this much lower so the cone, not the point, cuts (default 0.2 for a sharp tip, 0 for a flat tip) |
| `loops` | a face's `all` (default), `outer` or `inner` |
| `direction` | `climb` (default) or `conventional` |

A width the cone cannot reach (wider than its radius less the tip offset) is refused. The top must
be faced first (a `face` earlier in the setup, or a stock with no allowance on top): a chamfer under
uncut stock is `unreachable`. A tip that would touch the part under the chamfer is a `gouge`, a body
that would hit the part above a lower edge `tool_too_large`.

## engrave: Engrave

Follows curves at a shallow depth with the tool's centre on them: a DXF's lines, arcs, circles,
ellipses, polylines and splines (open or closed; blocks are expanded; text, dimensions and hatches are
skipped and counted: explode text to curves; any other entity is refused, naming its handle),
the edges of flat faces, or a `region`'s outline. Vee, engraver or chamfer tool. Nearest curve first;
plunges at each start. The modelled part has no engraving, so the gouge check does not judge it.

| key | meaning |
| --- | --- |
| `dxf` | the drawing's path, relative to the job file (else the part), or absolute |
| `origin_mm` | where the DXF's origin goes, `[x, y]` WCS (default `[0, 0]`) |
| `depth_mm` | how deep below the surface (default 0.2); deeper than the step down is cut in passes |
| `surface_z` | the surface's height, WCS (default: the named face's, else the part's top) |

The line's width at the surface is `tip diameter + 2 x depth x tan(half angle)` (in its note).

## vcarve: V-carve (lite)

Carves closed shapes with a V-bit along their medial axis (the centres of the largest circles that
fit inside), so the walls come out as sharp Vs: a DXF's closed profiles (even-odd, so a letter's
counter stays; open curves and text are skipped and counted in the note: explode text to curves),
flat `faces` (each face's own area, from its height), or a `region` polygon (no `bottom_z`). Vee,
engraver or chamfer tool; a flat, ball or other non-pointed tool is refused. At each point the tip
goes `(distance to the outline - tip radius) / tan(half angle)` below the surface, so the cone's
edge just touches the outline: a narrow stroke is shallow, a wide one deep. Runs are cut nearest
first, each entered where the tool already is, straight down onto the surface at a corner, onto a
point already cut as deep, or zig-zagging down along itself no steeper than the cone's flank (a
round dot spirals in); never a plunge into material. The modelled part has no carving, so the gouge
check does not judge it.

| key | meaning |
| --- | --- |
| `dxf` | the drawing's path, relative to the job file (else the part), or absolute |
| `origin_mm` | where the DXF's origin goes, `[x, y]` WCS (default `[0, 0]`) |
| `max_depth_mm` | the deepest the tip goes; wider than the cone there leaves a flat bottom (default: none) |
| `surface_z` | the surface's height, WCS (default: the named face's, else the part's top) |

`stepdown_mm` (optional) carves in levels; the default is one pass. With `max_depth_mm`, the V-bit
also runs the outline inset `tip radius + max_depth x tan(half angle)` at that depth (the walls'
foot), and the flat bottom inside is left: an operation has one tool, so clear it with a separate
`pocket` and a flat tool on the outline inset `flat_inset_mm`, its `region` `bottom_z` at
`flat_bottom_z` (both in the facts, with `flat_area_mm2`; the note says so). A DXF shape's flat
bottom needs its outline written as that region. The facts give `shapes`, `runs`, `levels`,
`length_mm` and `max_depth_mm`.

Refused: no closed shape, or every shape too small to carve (`empty_operation`); every shape
narrower than the tool's tip (`tool_too_large`); a shape wider than the cone is tall with no
`max_depth_mm` (`tool_too_small`: give one, or a wider V-bit); a `max_depth_mm` deeper than the
cone, or a carve past the flutes (`too_deep`); the part's top under uncut stock (`unreachable`:
face it first). A face below the part's top must be cleared down to first (a pocket before it).
Lite: the flat bottom is not cleared, and the axis is read from the outline sampled every 0.1 mm
(finer in small shapes), so it is within about that of the true one; the depth at each point is
exact for where the point is.

## helix_bore: Helix bore

Mills round holes by helical interpolation, posted as G2/G3 arcs with Z: the tool circles the
hole's exact centre at the hole's radius less its own, from the top of the material down at a pitch
per turn, then one flat circle at the bottom. A hole wider than twice the tool is bored inside out, a
stepover (default 0.4 of the diameter) wider each circle, so no core is left. Name hole walls in
`faces` (any face of a hole names the hole, and a counterbore's wall names the counterbore; it must
open toward the tool) or list `holes`. A tool not smaller than the hole is refused
(`tool_too_large`). Climb is counter-clockwise (G3). The feed is the table's at the cutting edge: the
centre runs at it scaled by its circle's radius over the edge's, never under a quarter.

| key | meaning |
| --- | --- |
| `holes` | `[{"center": [x, y], "diameter_mm": d, "bottom_z": z, "top_z": z}]`, WCS (`top_z` defaults to the part's top) |
| `pitch_mm` | depth per turn (default the least of 0.2 of the diameter, `stepdown_mm` when given, and the pitch that keeps the tool's centre at `ramp_angle_deg` on each circle). A pitch steeper than the ramp angle on the smallest circle is refused (`unreachable`, naming the largest allowed) |
| `ramp_angle_deg` | the helix's ramp angle when no pitch is given (default 3) |
| `through_mm` | go this much below a through hole's bottom (default 0; 0.2 to 0.5 mm breaks through cleanly) |
| `direction` | `climb` (default) or `conventional` |

## circular: Circular

Clears a round pocket or the material round a round boss, level by level (step down: the
material's default). Name the pocket's or the boss's wall in `faces` (a cylinder along Z: any face
of a pocket names the whole of it), or give a `region` with `bottom_z` (a pocket is the largest
circle inside the polygon; with `boss: true`, the boss is the smallest circle round it).

A pocket: each level goes down on a helix at the centre, spirals out to the wall a stepover
(default 0.4 of the diameter) per turn in tangent half circles (true G2/G3 arcs), then cuts one
whole finishing circle on the wall, counter-clockwise for climb. The feed is the table's at the
cutting edge: the tool's centre runs at it scaled by its circle's radius over the edge's, never
under a quarter. A tool not smaller than the pocket by a tenth of its radius on each side is
refused (drill or ream it).

A boss: each level starts on an outer ring, comes down in air off the stock or on a helix along the
ring, cuts one whole circle there, spirals in to the boss's wall and cuts one whole finishing circle
on it, clockwise for climb. A boss with less room round it than the tool's diameter is refused.

Pick `helix_bore` to bore a hole to size up to about twice the tool's diameter (one circle at the
wall), and `circular` for a wider round pocket (one spiral a level instead of a full-depth helix per
circle) and for any boss.

| key | meaning |
| --- | --- |
| `boss` | `true`: the faces are a boss's outside (or the region is a boss); `false`: a pocket. Default: what each face is; a region is a pocket. A face of the other kind is refused |
| `clear_mm` | a boss only: how far out from its wall to clear (at least the tool's diameter is). Default: out to the stock's edge, or up to the part beside the boss when it stands nearer; a `clear_mm` reaching the part beside it is refused |
| `bottom_z` | how deep, WCS (default: the pocket's bottom or the boss's foot; deeper than a blind pocket's bottom or a boss's foot is refused) |
| `through_mm` | go this much below a through pocket's bottom (default 0) |
| `ramp_angle_deg` | the helix's ramp angle (default 3) |
| `direction` | `climb` (default) or `conventional` |

`stock_to_leave_mm` is left on the wall and the floor. Its facts: `kind` (pocket or boss), `levels`,
`turns` of spiral, `diameter_mm`, `bottom_z`, `entries` (`helix`, `air`), and a boss's `cleared_mm`.

## trace: Trace

Follows a chain of the part's edges `depth_mm` below them: name the edges in `edges` as the Viewer
selects them (`#o1.e5`). They are joined end to end into chains, open or closed; each chain must lie
level in the setup (a chain that climbs is refused). Levels run from the material's top over the
edges (the stock top when they lie on the part's top) down by the step down; each level ramps in
along the path at `ramp_angle_deg`, or comes straight down where the tool is off the stock. The part
standing over the path within the tool's reach (an edge under a wall or an overhang) is refused.
Flat, bull, ball, vee, chamfer or engraver tool.

| key | meaning |
| --- | --- |
| `edges` | the edges to follow, `["#o1.e5", "#o1.e6"]` (required) |
| `depth_mm` | how far below the edges to cut (required) |
| `offset` | `on` (default: the tool's centre on the edges), `inside` or `outside` a closed loop (climb), `left` or `right` of an open chain looking along it from its start. An offset moves the centre the tool's cutting radius at the depth (a vee's: its radius `depth_mm` up its cone), so its edge runs on the edges. `left`/`right` on a loop or `inside`/`outside` on an open chain is refused |
| `start` | where an open chain starts: a point `[x, y]` (WCS) at one of its ends, or its first or last edge (`"#o1.e5"`). Required with `left` or `right`; an edge in the middle of the chain is refused. Without it a chain is cut from its end nearer the tool |
| `ramp_angle_deg` | the ramp's angle (default 3) |

With `offset: on` the tool cuts into the modelled part on purpose (a groove along the edges), so the
gouge check does not judge it; offset to one side it does. An open chain offset to one side is cut
from its start at every level; one on its edges is cut back and forth. Its facts: `passes` (the
chains), `levels`, `length_mm`, `bottom_z`, `offset`, `offset_mm`, `entries` (`ramp`, `air`).

## thread_mill: Thread mill

Mills a thread by helical interpolation with a `thread_mill` tool: inside a tap-sized hole (name its
wall) or on a round boss (name its outside). It steps in on a tangent half circle, follows a helix of
one pitch per turn over the thread's length, and steps out the same way. An internal thread is cut to
its major diameter, an external one to the ISO minor diameter (`major - 1.22687 x pitch`). The
modelled hole is the tap drill, so the gouge check does not judge a thread. Drill the hole first.

| key | meaning |
| --- | --- |
| `thread` | `internal` or `external` (default: a hole's or a boss's) |
| `pitch_mm` | the thread's pitch (default the tool's) |
| `major_diameter_mm` | the nominal size. A hole's default is the tap drill plus the pitch, snapped to 0.5 mm (Ø5 at 1 mm is M6, Ø6.8 at 1.25 is M8); a boss's, its diameter |
| `depth_mm` | the thread's length from the top (default: through and bosses their whole length, blind holes their depth less two pitches) |
| `hand` | `right` (default) or `left` |
| `form` | `single` (default: a single-point tool, the helix covers the whole length) or `multi` (a tool whose `flute_length_mm` of teeth covers the thread: one turn plus a turn per pitch the thread is longer; only the tool's own pitch) |
| `passes` | radial passes splitting the thread's depth (default 1, 2 from a 1.5 mm pitch) |
| `direction` | `climb` (default: a right-hand internal thread runs counter-clockwise from the bottom up, an external one clockwise from the top down) or `conventional` |

The feed is the table's at the cutting edge, scaled to the tool's centre (slower in a hole, never
under a quarter; faster round a boss). A tool not smaller than the hole is `tool_too_large`, a thread
longer than the hole or into a blind hole's bottom `too_deep`. An internal thread needs its hole made
first: without an earlier operation that makes it, the `prepared_hole` warning says so.

## Reading the results

Each operation's row says its tool, spindle speed, feed and time; its `facts` give `levels`,
`passes`, `entries` (how levels were entered: `helix`, `ramp`, `lead`, `air`), `plunges`, and the
floor or bottom it reached. A `note` becomes a warning line: loops too small for the tool, tabs a loop
was too short for, a chamfer's or an engraving's width and depth, a thread's size. Inside corners the
tool's radius cannot reach come back as the `corner_radius` warning ([checks.md](checks.md)): finish
them with a smaller tool. Chamfer, engrave, V-carve, thread mill and a trace `on` its edges cut into the
modelled part on purpose and are not judged by `gouge`; every other operation here is, so a gouge
from them means a wrong face, edge, offset or `bottom_z`.
