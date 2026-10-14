# Multi-axis

Tilting the part or the tool: indexed 3+2 setups (any operation, cut from a tilted position), `rotary`
(a 4th-axis wrap), `swarf` (a ruled wall cut with the side of the tool) and `surface_normal` (a 5-axis
finish). The keys every operation shares are in [job-file.md](job-file.md#operations); how each
controller posts rotary moves is in [posts.md](posts.md).

Read the part first: every face this page names comes from it.

```bash
cadgen cam features part.step
```

## Machines

| `machine.kind` | rotary axes | `machine.kinematics` |
| --- | --- | --- |
| `mill4` | A, turning the part about its X | none |
| `mill5` | A tilting and C turning (a trunnion table) | `ac_trunnion` (default) |
| `mill5` | B tilting the head and C turning the table | `bc_head` |

`machine.rotary_limits_deg` bounds them, like `{"a": [-30, 110], "c": [-360, 360]}`: a setup outside
them is refused, a move outside them is a `travel` error. Without limits every angle is allowed.

A and C are rotations of the part on the table, right-handed, in degrees: C about Z first, then A about
X (or B about Y), and the tool always points down the machine's Z. So on a 4th axis A 90 brings the
part's +Y side up to the tool, and on a trunnion A 30 C 90 brings up the side facing +X, tilted 30°.

## Indexed (3+2) setups

Any operation runs in a tilted setup: the table turns, then the operation cuts in three axes in that
setup's work coordinates, exactly as it would from the top. Give the setup a rotary position:

| `orientation` | meaning |
| --- | --- |
| `{"a_deg": 30}` | a mill4, or a trunnion with C at 0 |
| `{"a_deg": 30, "c_deg": 90}` | a trunnion (`ac_trunnion`) |
| `{"b_deg": 20, "c_deg": 45}` | a head (`bc_head`) |
| `+Z`, `-Z`, `+X`, `-X`, `+Y`, `-Y` | on a mill4 or mill5, the rotary position that brings that side up (a mill4 cannot bring up +X or -X: those stay a re-fixture by hand) |

Every move of the setup carries its rotary position, and the posted file turns the table before the
first cut. The work offset is set on the turned part at the setup's `origin` (posts.md says which
controllers program a tilted plane instead). A position the machine cannot reach is refused in one
sentence: an axis it does not have (`c_deg` on a mill4, `a_deg` on a `bc_head`), or one outside
`rotary_limits_deg` (the sentence names the other tilt that reaches the same side, when there is one).
A pocket square to a face tilted 30° about X:

```json
{
  "machine": {"kind": "mill4", "post": "linuxcnc", "max_rpm": 18000},
  "material": "aluminum-6061",
  "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
  "tools": [{"id": "T1", "type": "flat", "diameter_mm": 6, "flute_length_mm": 20, "stickout_mm": 35}],
  "setups": [
    {"id": "top", "orientation": "+Z", "operations": [{"op": "face", "tool": "T1"}]},
    {"id": "tilt", "orientation": {"a_deg": 30}, "operations": [{"op": "pocket", "tool": "T1", "faces": ["#o1.f12"]}]}
  ]
}
```

```bash
cadgen cam plan part.step --job job.cam.json
```

## rotary: 4th-axis wrap (lite)

Turns the part about its X axis while the tool stays pointed at the axis. The axis is the stock's
centre line: use a `cylinder` stock along `"x"` (a bar) with the part modelled along X; a cylinder
along another axis is refused. At every X and angle of a grid the tool is dropped radially onto the
part (exact contact through the drop-cutter), held `stock_to_leave_mm` off it. Ball, flat or bull.

| key | meaning |
| --- | --- |
| `mode` | `finish` (default): ride the surface; `rough`: clear radial levels `stepdown_mm` apart, each pass at the level or the finish surface, whichever is further out, entering each group of passes by a ramp along its first pass |
| `passes` | `around` (default): A turns continuously, one ring per X step (`stepover`: default 0.1 of the diameter finishing, 0.4 roughing), alternating direction; `along`: passes along X, A indexing between them by the stepover measured round the part's largest radius |
| `x_range_mm` | `[start, end]` along the part's X (default the part's length) |
| `angle_range_deg` | `[from, to]` (default `[0, 360]`, all the way round) |
| `sample_mm` | spacing along a pass (default 0.5); a chord that would sink into the surface is split until it does not |

The tool starts and ends over the setup's angle at the clearance radius (stock radius plus
`clearance_mm`), turning back every turn it made; between groups it lifts to the retract radius.

```json
{
  "machine": {"kind": "mill4", "post": "linuxcnc"},
  "material": "aluminum-6061",
  "stock": {"kind": "cylinder", "axis": "x", "diameter_mm": 32},
  "tools": [{"id": "T2", "type": "ball", "diameter_mm": 4, "flute_length_mm": 12, "stickout_mm": 30}],
  "setups": [{"id": "wrap", "operations": [
    {"op": "rotary", "tool": "T2", "mode": "rough", "stock_to_leave_mm": 0.3, "stepdown_mm": 1.5},
    {"op": "rotary", "tool": "T2", "stepover_mm": 0.4}
  ]}]
}
```

Its limits, which its result carries (quote them): it wraps only about the part's X through the
stock's centre line; undercuts the radial direction cannot see are left; roughing air-cuts over
finished areas; moves are written for tool-centre-point control (below).

## swarf: Swarf (lite, mill5)

Cuts ruled walls with the side of the tool, its axis along the wall's rulings (the straight lines from
the wall's foot to its top). Name the walls in `faces`: planes (and B-spline faces that are flat:
their rulings run parallel up the slope, clipped to the face's own outline), cylinders, cones, and
ruled lofts or extrusions. A floor, or a face curved both ways, is refused. Flat or bull tool.

| key | meaning |
| --- | --- |
| `direction` | `climb` (default) or `conventional` |
| `max_tilt_deg` | the most the tool may lean from the setup's tool direction (default 60); a steeper wall is refused |
| `sample_mm` | spacing of the rulings along the wall (default 1) |
| `lead_mm` | how far off the wall each pass starts and ends (default 2) |

The tool's side sits on the wall (plus `stock_to_leave_mm`) with its end at the wall's foot. Where its
tilted end would dip below the foot on the far side (a wall that overhangs) it is lifted, leaving a
strip at the foot (the row's `foot_strip_mm`). `stepdown_mm` cuts a tall wall in passes from the top
down; one full-height pass by default. Rulings whose flutes would cut the part beside the wall (an
inside corner, a floor) are dropped (`dropped_rulings`). Clear the material first (a pocket or `rough`
with stock to leave): swarf is a finishing pass.

Its limits: walls are cut one by one, corners between them not blended; a curved wall is followed
over its whole parameter range; a twisted (non-developable) ruled wall touches the tool only along
its middle; the strip at an overhanging foot is left.

## surface_normal: 5-axis finish (lite, mill5)

A ball raster over named `faces` with the tool's axis along the surface normal. Raster lines a
`stepover` apart (default 0.1 of the diameter) are cast straight down onto the faces; the ball's
centre sits a radius (plus `stock_to_leave_mm`) out along the normal, so it touches the surface
whatever the tilt. Ball tools only.

| key | meaning |
| --- | --- |
| `angle_deg` | the raster's direction in the setup's XY (default 0, along X) |
| `lead_deg` | leans the tool's top forward along the cut (negative: back), default 0 |
| `tilt_deg` | leans the tool's top to the right of the cut, default 0 |
| `max_tilt_deg` | the most the tool may lean from the setup's tool direction (default 30); steeper spots are held to it |
| `smooth` | the moving average of the axis along a line, in samples (default 5; 1 for none) |
| `sample_mm` | spacing along a line (default 0.5) |

Where the cutter or the shank would cut into the part (a concave corner, a neighbouring wall) the tool
rises up its own axis until it clears (`lifted_mm`); undercut spots (the normal facing down) are
skipped. A lead or tilt of a few degrees keeps the axis off the setup's tool direction, where C would
spin. Its limits: ball only, cast from above only, rising rather than re-tilting, C not smoothed at
the pole.

## How multi-axis moves are written

Indexed setups: every move carries the setup's rotary position; X Y Z are its work coordinates.

Continuous moves (`rotary`, `swarf`, `surface_normal`): X Y Z are the tool tip in the setup's work
coordinates fixed to the part, and A/B/C tilt the tool, which is how a controller with tool centre
point control (TCP) is programmed: LinuxCNC/Fanuc `G43.4`, Haas `G234`. Moves between two rows are
straight in the part's frame, so the planners split rotations finely enough to stay within the
tolerance, and every move that turns an axis posts its own A/B/C (never as an arc). A controller without TCP needs the
moves turned into machine positions about the rotary centre: posts.md says which posts refuse
instead. Feeds are tip feeds in mm/min (no inverse-time `G93`).

## The stock simulation

A mill4 or mill5 simulates the stock as a tri-dexel: three grids of rays along X, Y and Z, each holding
its material as intervals, cut by the tool at its true angle on every move. The stock in the result is
the Z rays drawn as merged boxes (blocky by a cell sideways, exact in height). `material_left` counts
stock outside the part over its footprint, by its thinnest reading across the three rays. A big stock
coarsens the grid and says so in an `adapted:` line.

## Reading the results

Each operation's row carries `facts`: `passes`, `levels` (rough wraps), `max_tilt_deg` (swarf,
surface_normal), `stock_to_leave`. Its `note` becomes a warning line: rulings skipped, the foot lifted,
samples held to `max_tilt_deg`, undercuts skipped, the tool risen off the surface. The planners' own
findings join the checks' ([checks.md](checks.md)): `gouge` (type `gouge_multiaxis`: the cutter would
enter the part between samples; use a smaller `sample_mm` or `stepover`), `holder_collision` (type
`holder_multiaxis`: the shank or holder hits the part; more stickout, a slimmer holder, or another
setup), `travel` (type `rotary_travel`: a rotary axis beyond `rotary_limits_deg`). Every lite limit is
in the verdict's `lite` list and the posted file's header: report them.
