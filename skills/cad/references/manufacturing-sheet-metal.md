# Sheet metal

The evidence and the rules are SKILL.md's [Can it be made?](../SKILL.md#can-it-be-made), and the result
in full, the review and how to check a redesign are [the review reference](manufacturing-review.md),
the same for every process; this is what is particular to cutting and bending sheet.

The check is general, no shop's. An order from SendCutSend, checked against its catalog and specs, is
the sendcutsend skill's ($sendcutsend): it runs this check and reads the measurements against them.

## Design it

What a cut-and-bent part has from its first line (the rules' numbers, general practice in multiples of
the thickness `t`; a shop's tooling and bend table move them):

- **One thickness.** The whole part is one sheet: every face is its top, its bottom or a cut edge.
  No boss, pocket, countersink, second thickness or solid block. A chamfered or rounded cut edge is
  allowed but is a second operation (`sheet.edge_break`, a warning); a cone or a torus between
  flanges is formed, not bent (`sheet.formed_surface`, a warning: not measured): a formed feature the
  person wants -- an emboss, a louver, a bead -- is quoted as one and checked by hand. Two bends that
  turn opposite ways with no flat, or a web under a flange's minimum, between them are a joggle: both
  unroll, and `sheet.joggle` (a warning) says it needs an offset (joggle) die; two the same way round
  with no flat between are one compound bend.
- **A bend is two arcs.** Inside radius `r` of at least `t` (the shop's tooling sets it; `--bend-radius`
  when known) and outside radius `r + t` at the same corner; a radius past `10t` is bump-formed or
  rolled, not one hit of the brake (`sheet.bend_radius_max`, a warning, text-to-cad's own line).
  Build the legs, union them and fillet both edges of the corner:

  ```python
  leg_a = bd.Box(60, 40, t, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
  leg_b = bd.Box(t, 40, 30, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN))
  bracket = leg_a + leg_b
  along = bracket.edges().filter_by(bd.Axis.Y)                 # the corner's edges run along Y
  inside = [e for e in along if abs(e.center().X - t) < 1e-6 and abs(e.center().Z - t) < 1e-6]
  outside = [e for e in along if abs(e.center().X) < 1e-6 and abs(e.center().Z) < 1e-6]
  bracket = bracket.fillet(r, inside).fillet(r + t, outside)
  ```

  Two boxes with a sharp corner, a fillet on one side only, or two radii that are not concentric is
  not a bend: the check reports the corner (`sheet.sharp_bend`, an error) and unfolds nothing past
  it. A shelled box (`bd.offset(box, -t, openings=...)`) has sharp corners the same way.
- **Flanges and holes.** A flange's height from the outside of the bend is at least `2t + r` (a
  straight length of at least `t` past the bend; `4t` keeps every shop happy); a hole sits at least
  `2t` from where the bend's radius starts and `t` from an edge, holes `2t` apart, each at least `t`
  across. A hole in a bend distorts (`sheet.hole_in_bend`); a window cut across the whole bend, past
  both tangent lines, ends the bend either side and is judged as a relief there, not as a hole. A
  bend that runs on past its flange has no flange there: length 0, `sheet.flange_length` (end the bend
  with the flange, or cut a relief).
- **Reliefs.** Where a flange ends before the sheet's edge, a relief at the bend's end, at least `t`
  wide and reaching past the bend radius, so the bend does not tear.
- **Cut features.** Slots, notches and tabs at least `t` wide (and wider than the kerf), no longer than
  five times their width; webs between cut-outs at least `t` (a grille's bars are one `sheet.web_width`
  finding, not one for each pair of slots).
- **Hems and channels.** A hem's inside diameter at least `t` and its return `6t` (a fold whose inside
  diameter is over `4t` is a U-bend round a radius tool, no hem); a channel's base
  wide enough for the brake's punch between its flanges (the shop's tooling: a check by hand).
- Stock 0.5 to 6 mm bent (10 mm cut flat) is the recommendation (warnings); past an inch (25.4 mm) it is
  plate, no sheet shop's work (`sheet.thickness_limit`, an error, text-to-cad's own floor). A strip is
  sheet from twice as wide and ten times as long as it is thick; narrower or shorter, it is a bar or a
  block (`sheet.not_sheet`). The material on the
  part (`part.material =
  metals.mild_steel()` or the alloy's factory: the check reads it); `--thickness` when the person named
  the gauge. `bd_materials` has no sheet process, so the check always takes `--process sheet`.

## Check it

```bash
cad step dfm tab.step --process sheet --material steel --thickness 2
cad model dfm "$ID" --process sheet --material aluminum --bend-radius 2 --k-factor 0.42
cad dxf dfm bracket.dxf --thickness 2 --kerf 0.2 --sheet-size 1219x2438
```

The check unfolds the part and measures every feature on the flat pattern, each mapped back to its
face. The options that change the verdicts:

- `--material`: the material's limits and its K-factor chart.
- `--thickness`: the stock's. Without it each part is judged by its own measured thickness (a
  document of a 1 mm and a 3 mm part scales each part's rules by its own); a part modelled at another
  is `sheet.thickness_mismatch`.
- `--k-factor`: from the shop's bend table. Without it K is read from a chart
  (`sheet.k_factor_assumed`), and the flat pattern is not a production blank.
- `--bend-radius`: the shop's inside radius; a bend modelled otherwise is `sheet.bend_radius_differs`.
- `--kerf` (features narrower are `sheet.under_kerf`) and `--sheet-size`: the shop's largest sheet, an
  error to pass it; without it a standard 5 x 10 ft sheet is assumed, a warning, and a flat no stock
  plate holds (10 x 40 ft, 3048 x 12192 mm) is an error (`sheet.flat_length_limit`,
  `sheet.flat_width_limit`, text-to-cad's own floor).
- `--units` (a DXF's alone): the units a cut file was drawn in, where it declares none or the wrong ones.

The rules are general, no shop's: a shop's gauges, its tooled radius per gauge, its die widths, its
brake's angles and bend lengths and its smallest and largest parts are compared with the measurements
(`parts.thickness_mm`, `bends.inside_radius_mm` and `angle_deg`, `flanges`, `hole_to_bend`, `reliefs`,
the flat's size), or given as options where they are one. A mesh is refused: check the STEP or the
model.

## Read it

The last line is the check's state and its exit status -- `OK` 0, `FAILED` 1 (a finding is an error; with
`--strict` a warning fails too), `NOT CHECKED` 3 (something was not judged: never a pass), and 2 for a
command refused -- and a finding is data to edit from (a rule's `value`, `limit`, `unit`, `op`, `source`
and `refs`; the faces of a sharp corner, a chamfered edge or a part that is not sheet in `refs` too):
[Read the result](../SKILL.md#read-the-result).

The families: `parts`, `not_sheet`, `sharp_bends`, `bends`, `flanges`, `channels`, `reliefs`, `hems`,
`curls`, `holes`, `hole_spacing`, `hole_to_bend`, `notches`, `tabs`, `webs`, `gaps`.

- `parts.is_sheet` and `not_sheet`: a body of constant thickness, read off the part's own faces, so
  the same wherever it stands. A part mostly sheet is judged, its departures at their refs: a boss, a
  pocket or a closed hem's double thickness `not_sheet` (one finding a feature), chamfered or rounded
  cut edges `edge_break` (a warning), a cone or a torus `formed` (`sheet.formed_surface`); a part
  that is not sheet (`is_sheet` false: `sheet.not_sheet` says why -- a bar or a block, no face twice as
  wide and ten times as long as it is thick; a tube, a closed section) gets no other sheet verdict. A sheet rolled round with
  no flat flange is sheet, rolled, and not unrolled here: `NOT CHECKED` (`measurement_failed` for
  `bends`), to be checked by hand. `sharp_bends` are corners joined without a bend
  (`sheet.sharp_bend`): nothing past one unfolds.
- `bends`: `inside_radius_mm`, `angle_deg`, `k_factor` with its source, `bend_allowance_mm`.
- Distances come in several conventions: `hole_to_bend` carries `distance_tangent_mm` (from where the
  bend's radius starts), `distance_centerline_mm`, `distance_inside_mm` and `distance_outside_mm`;
  `flanges` likewise. Each rule reads one and names it in its message. Compare a shop's own number
  only with the field in that shop's convention.
- `reliefs` lists every bend end where the flange runs on past the bend: a missing relief has
  `width_mm` 0. Its width is judged; how far it reaches past the bend (`depth_tangent_mm`), corner
  reliefs and a channel's width against its legs (`channels`) are measured and not judged, which
  `sheet.measured_not_judged` (an info) says: read them against the shop's.

## Review the part

Collect alloy and temper, stock thickness and units, the cutting and forming process, critical
dimensions, and any shop bend table. Ask only for missing inputs that change the current decision;
otherwise state provisional assumptions.

A projection of a bent solid is not an unfolded blank. `cad.build123d.unfold(shape, k_factor=...)`
in a check script returns the flat pattern the check measured; with bend angle theta in radians,
each bend adds BA = theta * (inside radius + K * thickness). Do not treat a chart's K as a production
dimension: take it from the shop's table.

Check by hand what the check does not measure: bend order, tooling access and collisions while
bending; grain direction; hardware (PEMs) and their distances; box flange maxima; bump-formed,
rolled or conical bends; a hole crossing a bend, or a curved bend end (both unrolled from
samples). Missing tooling or a valid unfold leaves these unverified; a valid STEP solid alone does
not establish forming feasibility.

A clean DXF or flat pattern, or a successful upload to a supplier, does not establish that all bends
can be made.

## Cut files (DXF)

A laser, plasma, waterjet or routing shop cuts the DXF, so check the exact file it gets (a
text-to-cad drawing's is the one `cad xbf export <id> part.dxf` wrote), not the model it came from:

```bash
cad dxf dfm part.dxf --process sheet --material aluminum --thickness 3 --kerf 0.2
```

It reads the file as a cutter does -- every entity on a cut layer, a block reference's too, where
it is placed -- and judges the cut layout: open geometry on a cut layer (`sheet.open_contour`), curves
cut twice (`sheet.overlapping_curves`: any curve drawn again, lines and arcs that overlap),
self-intersecting contours, contours that cross or touch (`sheet.crossing_contours`: a hole breaking
or tangent to the edge), zero-area loops, a piece that falls out of a hole
(`sheet.floating_interior`), text or dimensions on a cut layer, a curve drawn as short lines, ends a
hair apart that it joined (`sheet.joined_gap`, under 0.01 mm), and holes, webs and gaps against the
thickness. `measurements.cut_file` gives the units, extents and layers. A CAD's flat pattern export
is read by its layer names: bend-extent (tangent) lines and centre marks (Inventor's `IV_TANGENT`,
`IV_ARC_CENTERS`, a `BEND_EXTENT` layer) are reference, not cuts or bends.

What it could not read is never a pass. A file with no cut curve (an empty one, a drawing of
dimensions alone) is not checked (`no_cut_geometry`); a cut-layer entity it does not read (a curve
off the sheet's plane, a mesh) is `measurement_failed` for `cut_entities`, naming it; with no contour
closed there is no part (`measurement_failed` for `parts`, beside the open contours). A dimension in
the file excuses nothing: the cut layers are measured all the same. Then read by hand:

- **Thickness.** Give `--thickness`: the rules that scale with it (holes, edges, webs, notches, tabs,
  reliefs) are not evaluated without it (`sheet.thickness_unknown`), and an `OK` then judges the
  contours alone.
- **Units.** A file that declares no units (`$INSUNITS` unset: every R12 file) is `NOT CHECKED`
  (`units_not_set`) until `--units mm` (or `cm`, `m`, `in`, `ft`) says what it was drawn in; it is then
  measured, with a warning that the shop has to be told too. A unit that makes the part implausible
  (an inch-drawn part declared mm reads 25.4 times small; a drawing over 10 m across) is
  `units_suspect`. Compare `cut_file.extents_mm` with the part's expected size; never rescale silently.
- **Kerf.** Say whether the file is drawn to the finished size, with the shop's compensation, or
  already offset (`offset_profile`, `flat_pattern(..., kerf=)`): offsetting twice takes the kerf off
  twice. Take the kerf from the shop for the material and thickness.
- **Bend lines.** Lines on a bend layer are read as the bends' centre lines (`sheet.bend_lines_read`,
  an info). A flat drawing has no bend radius or angle, so each hole and edge is held to the least any
  bend needs: a hole within `2t` of a bend line (`sheet.hole_to_bend`) and an edge within `t` of one
  (`sheet.flange_length`) fail whatever the bend. A window through the bend -- a cutout the line ends
  at, or is drawn across, reaching `2t` to both sides of it -- ends the bend and is no hole in it. The
  full distances, the radius and the reliefs are the bent part's check (its STEP): a cut file that
  passes has not passed them.
- **What a cutting service needs.** Bend lines on their own named layer when the shop bends; marking
  text as outlines on its own layer when the shop engraves; one part per file unless the shop takes
  nested sheets. On a router an internal corner takes the tool's radius.

A file that passes is a well-formed cut file, not an accepted order: the shop's own upload checks,
material and service limits still apply.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

`sheet.hole_to_bend at tab/face 12: hole-to-bend distance from the bend's tangent line 2.5 mm is
under the 4 mm minimum` (the general rule, 2 mm steel). Report a 1.5 mm shortfall and propose moving the hole
or a supplier-approved relief. If the shop's drawing measures from the bend centerline, compare its
number with `distance_centerline_mm` instead.
