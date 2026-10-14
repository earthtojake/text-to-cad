# 3D milling

Curved and sculpted parts: domes, fillets, moulds, freeform surfaces, cut with the tool along Z by the
drop-cutter (each point of a pass is as low as the tool can sit without cutting the part):
`rough`, `adaptive_3d`, `parallel`, `waterline`, `scallop`, `pencil` and `rest`. Flat floors and straight walls are
[milling-2d.md](milling-2d.md). The keys every operation shares (`tool`, `faces`, `region`, `feed`,
`speed`, `stepdown_mm`, `stepover`, `stepover_mm`, `stock_to_leave_mm`, `coolant`, `name`) are in
[job-file.md](job-file.md#operations).

```bash
cadgen cam features part.step
```

The usual order: `rough` with a flat or bull end mill leaving `stock_to_leave_mm` (0.3 to 0.5), then
finish with a ball: `parallel` on the shallow areas and `waterline` on the steep walls (split them at
about 45° with the slope keys), then `pencil` or `rest` with a smaller ball for the corners the big
one could not reach. Coordinates in a `region` are the setup's work coordinates (WCS): with the
default origin `stock-top-center`, Z 0 is the top of the stock.

A minimal job: rough, finish shallow and steep, clean the corners with a 2 mm ball.

```json
{
  "machine": {"kind": "mill", "post": "grbl", "max_rpm": 24000},
  "material": "aluminum-6061",
  "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
  "tools": [
    {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 30, "stickout_mm": 40},
    {"id": "T2", "type": "ball", "diameter_mm": 6, "flute_length_mm": 30, "stickout_mm": 40},
    {"id": "T3", "type": "ball", "diameter_mm": 2, "flute_length_mm": 12, "shank_diameter_mm": 6, "stickout_mm": 40}
  ],
  "setups": [{"id": "top", "operations": [
    {"op": "rough", "tool": "T1", "stepdown_mm": 3, "stock_to_leave_mm": 0.4},
    {"op": "parallel", "tool": "T2", "stepover_mm": 0.5, "max_slope_deg": 45},
    {"op": "waterline", "tool": "T2", "stepdown_mm": 0.5, "min_slope_deg": 45},
    {"op": "rest", "of": "parallel", "tool": "T3", "from_tool_diameter_mm": 6, "stepover_mm": 0.2}
  ]}]
}
```

```bash
cadgen cam plan part.step --job job.cam.json
```

Without `faces` or a `region`, the finishing operations cover the part's whole silhouette (the part
seen from the tool). `faces` keeps the tool's centre over those faces' footprint; a `region`
(`{"polygon": [[x, y], ...]}`, WCS) keeps it inside the polygon. Give one or the other, not both.

## rough: 3D rough

Clears the stock round the part's 3D shape in Z levels: even step-downs from the stock top, plus
every upward flat of the part (at the flat plus the stock to leave, so flats are left exactly that
thick). At each level the tool keeps its radius plus `stock_to_leave_mm` off everything of the part
above the level. Areas open to the outside of the stock are cleared from the outside in, starting in
the air beside the stock or fed in sideways at the level; closed cavities are cleared from the inside
out like a pocket, entered by a helix (else a ramp that follows the pass, else a plunge). Flat, bull
or ball tool; stepover defaults to 0.4 of the diameter, step-down to the material's. It takes a
`region` (`{"polygon": [...], "bottom_z": z}`), not faces.

| key | meaning |
| --- | --- |
| `bottom_z` | the lowest level, WCS (default: the part's bottom, or the region's `bottom_z`) |
| `ramp_angle_deg` | entry ramps and helices (default 3) |
| `direction` | `climb` (default) or `conventional` |

On slopes the levels leave steps up to the step-down tall: finish after it.

## adaptive_3d: 3D adaptive clear (lite)

Roughs like `rough`, in the same Z levels round the part's 3D shape, but at a capped tool load and
only where material stands: the adaptive clear of [milling-2d.md](milling-2d.md) at each level, the
tool kept its radius plus `stock_to_leave_mm` off everything of the part above the level. It reads
the stock as it stands (every earlier operation and setup replayed), so after a `rough` (or another
setup) it cuts only what is left, and skips a level with nothing left. An open side is come into from
the air beside the stock; a closed cavity is entered by a helix. Flat or bull tool; stepover defaults
to 0.15 of the diameter (more than 0.5 is refused), step-down to twice the material's, within the
flutes (deep and light). It takes a `region` (`{"polygon": [...], "bottom_z": z}`), not faces.

| key | meaning |
| --- | --- |
| `bottom_z` | the lowest level, WCS (default: the part's bottom, or the region's `bottom_z`) |
| `ramp_angle_deg` | helix entries (default 3) |
| `direction` | `climb` (default) or `conventional` |

Pick it over `rough` for a hard material or a deep cavity (no full-width cut in a corner), or to
clean up after a rough with a bigger stepover. On fresh stock it is usually slower than `rough`:
its passes are lighter. Its limits, which its result carries (quote them): engagement is capped by
growing the cleared area, not a true adaptive solver (about twice the stepover on the first ring
round an entry); a piece too narrow for a helix is ramped along its outline at full width; steps on
slopes are as tall as the step-down. `air_fraction`, `air_mm` and `cut_mm` say how much of the path
cuts nothing.

## parallel: Parallel finish

Parallel passes the stepover apart (default 0.1 of the diameter), each dropped onto the part with
the stock to leave. Wherever the surface bends away from the straight move between two samples by
more than half the tolerance the move is split, so the path follows the surface to the job's
`tolerance_mm`. Passes are joined zig-zag by short moves along the surface; a long link lifts over
the stock as it stands (the earlier operations simulated) and comes back down. Ball (best), bull or
flat tool. Steep walls get a coarse finish across the passes: keep it to the shallow areas.

| key | meaning |
| --- | --- |
| `angle_deg` | the passes' direction in the XY plane (0 runs along X) |
| `pattern` | `zigzag` (default) or `one_way` (every pass the same direction) |
| `min_slope_deg`, `max_slope_deg` | cut only where the surface's slope is between them (degrees, 0 flat, 90 vertical; defaults 0 and 90). `"max_slope_deg": 45` keeps to the shallow areas |

## waterline: Waterline

Constant-height loops, each where the tool touches the part at its level, from the top down:
the finish for steep walls. `stepdown_mm` is the height between levels (default the stepover, 0.1 of
the diameter). Each loop point is placed on the contact by the drop-cutter, within a quarter of the
tolerance, never inside the part. Loops run with the part on the right (climb).

| key | meaning |
| --- | --- |
| `min_slope_deg`, `max_slope_deg` | keep to where the surface's slope is between them; `"min_slope_deg": 45` keeps to the steep walls |
| `direction` | `climb` (default) or `conventional` |

The loops are found on a grid (a quarter of the tool's radius, 0.1 to 0.5 mm): a feature narrower
than that can be missed, and the result's `adapted` says when a big part made the grid coarser.

## scallop: Scallop (lite)

Rings a constant stepover apart (default 0.1 of the diameter), offset inward from the boundary in the
plan view and dropped onto the part, cut from the outside in.

| key | meaning |
| --- | --- |
| `direction` | `climb` (default) or `conventional`: which way round the rings run |

Lite: the stepover is constant as seen from above, not along the surface, so on a slope the real
distance between passes grows by 1/cos(slope) (pair it with `waterline` on walls); the rings follow
the boundary's outline, so the finish is even only where the surface follows it too.

## pencil: Pencil (lite)

One pass along each inside corner and crease, where the tool touches two surfaces at once (found where
the drop-cutter surface bends sharply upward), smoothed and dropped onto the part again. Use the
finishing ball, or a smaller one after it.

| key | meaning |
| --- | --- |
| `crease_deg` | how sharply the surface must bend to count as a crease (default 30) |

Lite: creases are found on a grid (a sixth of the radius, 0.05 to 0.25 mm), so each pass lies up to a
grid spacing from the true corner, on the side away from the part; a crease shorter than four grid
points is not traced; one pass per crease (a corner tighter than the tool needs a smaller tool, so
`rest`).

## rest: Rest machining

Runs a `rough`, `parallel` or `waterline` only where material is still left: by default where the
stock as it stands (every earlier operation replayed on the stock simulator) is more than
`stock_to_leave_mm` plus 0.05 mm over the part; with `from_tool_diameter_mm`, where a bigger tool of
that diameter (the same type as this one) could not reach. The area is grown by this tool's radius
and the chosen operation plans inside it, with its own keys.

| key | meaning |
| --- | --- |
| `of` | `rough`, `parallel` or `waterline` (required) |
| `from_tool_diameter_mm` | judge by a bigger tool of this diameter instead of the simulated stock |
| `bottom_z`, `ramp_angle_deg`, `direction` | for `of: rough`, as there |
| `angle_deg`, `pattern`, `min_slope_deg`, `max_slope_deg` | for `of: parallel`, as there |
| `min_slope_deg`, `max_slope_deg`, `direction` | for `of: waterline`, as there |

The stock is only simulated for top and bottom setups; in a tilted one the rest runs everywhere and
says so as an `adapted` step.

## Reading the results

Each operation's row gives its tool, spindle speed, feed and time; its `facts` give `levels` (rough,
waterline), `passes`, `entries` (rough: `air`, `side`, `helix`, `ramp`) and `stock_to_leave`. A
`note` becomes a warning line (nothing to cut, an empty boundary, nothing left for a rest).

Every 3D operation is judged by the full `gouge` check: each feed point against the drop-cutter, so
a gouge here is a planning fault to report. `holder_collision` judges a shank or holder wider than the
flutes (`shank_diameter_mm`, `holder_diameter_mm`) against the part and the stock as it stood before
the operation: a small ball on a wide shank needs `flute_length_mm` as deep as it cuts. After a rough,
`material_left` warns about the stock left on walls and steps: expected until the finishing
operations, and the reason to run them. Report every lite limit and every `adapted:` line.
