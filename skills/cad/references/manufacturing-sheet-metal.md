# Sheet metal

Read this file before modelling or checking a part cut and bent from sheet, or checking a cut file
(a DXF). What every process shares (the result in full, a shop's own limits, the review, a redesign)
is [the review reference](manufacturing-review.md).

## Design it

The numbers are multiples of the thickness `t`: Protolabs Network's (Hubs) bending and laser-cutting
rules, and Protolabs' for one thickness, notches, tabs and hems. Those marked *own* are
text-to-cad's where no guide states one. The errors are one thickness, a sharp bend, the flange
height, the relief, the hole-to-bend distance, a hem's diameter and plate; the other limits are
recommendations (warnings). A shop's tooling and bend table move them.

- **One thickness.** Every face is the sheet's top, its bottom or a cut edge: no boss, pocket, second
  thickness or solid block. A countersunk hole is read as a hole. A chamfered or rounded cut edge
  is a second operation (`sheet.edge_break`, a warning). A cone or a torus between flanges is
  formed, not bent (`sheet.formed_surface`, a warning: not measured), so an emboss, a louver or a
  bead is quoted as a formed feature and checked by hand.
- **A bend is two arcs.** Inside radius `r` of at least `t` (`--bend-radius` when the shop's is
  known) and outside radius `r + t` about the same axis. Build the legs, union them and fillet both
  edges of the corner:

  ```python
  leg_a = bd.Box(60, 40, t, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
  leg_b = bd.Box(t, 40, 30, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
  bracket = leg_a + leg_b
  along = bracket.edges().filter_by(bd.Axis.Y)                 # the corner's edges run along Y
  inside = [e for e in along if abs(e.center().X - t) < 1e-6 and abs(e.center().Z - t) < 1e-6]
  outside = [e for e in along if abs(e.center().X) < 1e-6 and abs(e.center().Z) < 1e-6]
  bracket = bracket.fillet(r, inside).fillet(r + t, outside)
  ```

  Two boxes with a sharp corner, a fillet on one side only, two radii that are not concentric, or a
  shelled box (`bd.offset(box, -t, openings=...)`) is not a bend: `sheet.sharp_bend`, an error, and
  nothing past it unfolds. A radius past `10t` is bump-formed or rolled, not one hit of the brake
  (`sheet.bend_radius_max`, a warning, own). Two bends that turn opposite ways with no flat between
  them, or a web under a flange's minimum, are a joggle, which takes an offset die (`sheet.joggle`, a
  warning).
- **Flanges.** A flange's height from the outside of the bend is at least `2t + r`: a straight
  length of `t` past the bend. A bend that runs on past its flange has no flange there (length 0,
  `sheet.flange_length`): end the bend with the flange, or cut a relief.
- **Reliefs.** Where a flange ends before the sheet's edge, a relief at the bend's end at least `t`
  wide, reaching past the bend's radius, so the bend does not tear.
- **Holes.** At least `t` across, `2t` from where the bend's radius starts, `t` from an edge and
  `2t` apart. A hole in a bend distorts (`sheet.hole_in_bend`); a window cut across the whole bend,
  past both tangent lines, ends the bend each side and is judged as a relief, not as a hole.
- **Cut features.** A notch at least the greater of `t` and 1.016 mm wide, a tab at least the
  greater of `2t` and 3.2 mm, neither longer than 5 times its width; webs between cut-outs at least
  `t` (a grille's bars are one `sheet.web_width` finding); every feature wider than the kerf.
- **Hems and channels.** A hem's inside diameter at least `t` and its return `6t`; a fold over
  `4t` inside (own) is a U-bend round a radius tool, no hem. A channel's base takes the brake's
  punch between its flanges: the shop's tooling, a check by hand.
- **Stock.** 0.5 to 6 mm bent and to 10 mm cut flat; over 25.4 mm is plate, no sheet shop's work
  (`sheet.thickness_limit`, own). A strip is sheet from twice as wide and ten times as long as it
  is thick (own): narrower or shorter, it is a bar or a block (`sheet.not_sheet`).
- The material on the part is `part.material = metals.mild_steel()`, or the alloy's factory.
  `bd_materials` has no sheet process, so the check always takes `--process sheet`.

## Check it

```bash
cad model dfm "$ID" --process sheet --material aluminum --thickness 2 --bend-radius 2 --k-factor 0.42
```

The check unfolds the part and measures every feature on the flat pattern, each mapped back to its
face.

- `--thickness`: the stock's. With none each part is judged by its own measured thickness; a part
  modelled at another is `sheet.thickness_mismatch`, an error.
- `--bend-radius`: the shop's inside radius; a bend modelled otherwise is
  `sheet.bend_radius_differs`.
- `--k-factor`: from the shop's bend table. With none K is read from Hubs's air-bending chart, by
  `--material`'s hardness and each bend's radius (`sheet.k_factor_assumed`), and the flat pattern is
  not a production blank. No limit turns on `--material`.
- `--kerf`: a hole, web or gap narrower is `sheet.under_kerf`, an error.
- `--sheet-size 1219x2438`: the shop's largest sheet, an error to pass. With none a standard 5 x 10
  ft sheet (1524 x 3048 mm, Xometry) is assumed, a warning to pass, and a flat no stock plate holds
  (3048 x 12192 mm, own) is an error.

Compare a shop's gauges, tooled radius per gauge, die widths and part sizes with `measurements`
`parts`, `bends`, `flanges`, `hole_to_bend` and `reliefs`.

## Read it

The result is read as [every process's](manufacturing-review.md#read-the-result). The families of
`measurements`: `parts`, `not_sheet`, `sharp_bends`, `bends`, `flanges`, `channels`, `reliefs`,
`hems`, `curls`, `holes`, `hole_spacing`, `hole_to_bend`, `notches`, `tabs`, `webs`, `gaps`.

- A part mostly sheet is judged, its departures at their refs (`not_sheet` items: a boss, a pocket,
  a closed hem's double thickness). A part that is not sheet (`parts` `is_sheet` false;
  `sheet.not_sheet` says why: a bar, a block, a tube) gets no other verdict. A sheet rolled round
  with no flat flange is not unrolled: `NOT CHECKED` (`measurement_failed` for `bends`), a check by
  hand.
- Distances come in several conventions, each its own field: `hole_to_bend` has
  `distance_tangent_mm` (from where the bend's radius starts), `distance_centerline_mm`,
  `distance_inside_mm` and `distance_outside_mm`, and `flanges` likewise. A rule names the one it
  reads in its message: compare a shop's number only with the field in that shop's convention. A
  bend's `angle_deg` is the angle it is bent through, 90 for a right angle.
- `reliefs` lists every bend end where the flange runs on past the bend; a missing relief has
  `width_mm` 0. Its width is judged. How far it reaches past the bend, corner reliefs and a
  channel's width against its legs are measured and not judged (`sheet.measured_not_judged`): read
  them against the shop's.

## Review the part

A projection of a bent solid is not its blank. `cad.build123d.unfold(shape, k_factor=...)` returns
the flat pattern the check measured, a face on XY that a model can return and export as a DXF. Each
bend adds `BA = angle * (r + K * t)`, the angle in radians. A chart's K is no production dimension:
take K from the shop's table.

Check by hand what the check does not measure: bend order, tooling access and collisions while
bending; grain direction; hardware (PEMs) and its distances; box flange maxima; bump-formed, rolled
or conical bends. A clean check, a clean DXF or an upload a supplier accepts does not establish that
every bend can be made.

## Cut files (DXF)

A laser, plasma, waterjet or routing shop cuts the DXF, so check the file it gets (a model's is the
one `cad model export "$ID" part.dxf` wrote), not the model it came from:

```bash
cad dxf dfm part.dxf --thickness 3 --kerf 0.2 --sheet-size 1219x2438
```

The check reads the file as a cutter does (every entity on a cut layer, a block reference's too)
and judges the layout:

- errors: open geometry on a cut layer (`sheet.open_contour`), curves cut twice
  (`sheet.overlapping_curves`), a contour that crosses itself (`sheet.self_intersecting`), contours
  that cross or touch (`sheet.crossing_contours`: a hole breaking or tangent to the edge) and
  zero-area loops (`sheet.zero_area_loop`);
- warnings: a piece that falls out of a hole (`sheet.floating_interior`), text or dimensions on a
  cut layer, a curve drawn as short lines, and ends a hair apart that it joined
  (`sheet.joined_gap`, under 0.01 mm);
- holes, webs and gaps against the thickness and the kerf.

`measurements.cut_file` has the units, extents and layers. The bend-extent lines and centre marks
of a CAD's flat-pattern export (Inventor's `IV_TANGENT` and `IV_ARC_CENTERS`, a `BEND_EXTENT` layer)
are read as reference, not as cuts or bends.

What it could not read is never a pass. A file with no cut curve is `NOT CHECKED`
(`no_cut_geometry`), and so is one with a cut-layer entity it does not read (a curve off the
sheet's plane, a mesh: `measurement_failed` for `cut_entities`) or with no closed contour
(`measurement_failed` for `parts`). Then:

- **Thickness.** Without `--thickness` the rules that scale with it (holes, edges, webs, notches,
  tabs, bend lines) are not evaluated (`sheet.thickness_unknown`), and an `OK` judges the contours
  alone.
- **Units.** A file that declares none (`$INSUNITS` unset: every R12 file) is `NOT CHECKED`
  (`units_not_set`) until `--units mm` (or `cm`, `m`, `in`, `ft`) says what it was drawn in; it is
  then measured, with a warning that the shop has to be told too. A unit that makes the part
  implausible is `units_suspect`: compare `cut_file.extents_mm` with the part's expected size, and
  never rescale silently.
- **Kerf.** Say whether the file is drawn to the finished size or already offset (`bd.offset`):
  offsetting twice takes the kerf off twice. The kerf is the shop's, for the material and thickness.
- **Bend lines.** Lines on a bend layer are read as the bends' centre lines
  (`sheet.bend_lines_read`). A flat drawing has no bend radius or angle, so a hole within `2t` of a
  bend line (`sheet.hole_to_bend`) and an edge within `t` of one (`sheet.flange_length`) fail
  whatever the bend, and a cutout the line ends at, or crosses reaching `2t` to both sides, ends the
  bend. The full distances, the radius and the reliefs are the bent part's check: a cut file that
  passes has not passed them.
- **The shop's file rules** are not checked: bend lines and engraving each on a named layer,
  marking text as outlines, one part a file unless the shop nests. On a router an internal corner
  takes the tool's radius.

A file that passes is a well-formed cut file, not an accepted order.
