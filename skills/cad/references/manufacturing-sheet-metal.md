# Sheet metal

The evidence, the rules, the review and how to check a redesign are SKILL.md's
[Can it be made?](../SKILL.md#can-it-be-made), the same for every process; this is what is particular
to cutting and bending sheet.

An order from SendCutSend, checked against its catalog and specs, is the sendcutsend skill's
($sendcutsend).

## Design it

What a cut-and-bent part has from its first line (the `generic` set's numbers, in multiples of the
thickness `t`; a shop's set or bend table moves them):

- **One thickness.** The whole part is one sheet: every face is its top, its bottom or a cut edge.
  No boss, pocket, countersink, second thickness or solid block; a formed feature the person wants is
  a check by hand.
- **A bend is two arcs.** Inside radius `r` of at least `t` (the shop's tooling sets it; `--bend-radius`
  when known) and outside radius `r + t` at the same corner. Build the legs, union them and fillet
  both edges of the corner:

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
- **Flanges and holes.** A flange runs at least `2t` past the bend's outside radius (`4t` keeps every
  shop happy); a hole sits at least `2t` from where the bend's radius starts and `t` from an edge,
  holes `2t` apart, each at least `t` across (`2t` for a tapped one); nothing crosses a bend.
- **Reliefs.** Where a flange ends before the sheet's edge, a relief at the bend's end, at least `t`
  wide and reaching past the bend radius, so the bend does not tear.
- **Cut features.** Slots, notches and tabs at least `t` wide (and wider than the kerf), no longer than
  five times their width; webs between cut-outs at least `t`.
- **Hems and channels.** A hem's inside diameter at least `t` and its return `6t`; a channel's base at
  least twice its flange height, so a punch fits.
- Stock 0.5 to 6 mm bent (10 mm cut flat); the material on the part, `part.material = metals.steel()`
  or the alloy's factory; `--thickness` when the person named the gauge.

## Check it

```bash
cad step dfm tab.step --process sheet --material steel --thickness 2
cad model dfm "$ID" --process sheet --material aluminum --bend-radius 2 --k-factor 0.42 --rules protolabs
cad step dfm bracket.step --process sheet --rules sendcutsend --material 5052
```

The check unfolds the part and measures every feature on the flat pattern, each mapped back to its
face. The options that change the verdicts:

- `--material`: the material's limits and its K-factor chart.
- `--thickness`: the stock's. Without it the measured thickness is used; a part modelled at another
  is `sheet.thickness_mismatch`.
- `--k-factor`: from the shop's bend table. Without it K is read from a chart
  (`sheet.k_factor_assumed`), and the flat pattern is not a production blank.
- `--bend-radius`: the shop's inside radius; a bend modelled otherwise is `sheet.bend_radius_differs`.
- `--kerf` (features narrower are `sheet.under_kerf`) and `--sheet-size`.

Rule sets: `generic`, `hubs`, `protolabs`, `sendcutsend`. With `sendcutsend` give `--material`: the
thickness must be one of its gauges, and one that is not is `sheet.gauge_unmatched`, its gauge rules
not evaluated. A mesh is refused: check the STEP or the model.

## Read it

The families: `parts`, `not_sheet`, `bends`, `flanges`, `channels`, `reliefs`, `hems`, `curls`,
`holes`, `hole_spacing`, `hole_to_bend`, `notches`, `tabs`, `webs`, `gaps`.

- `parts.is_sheet` and `not_sheet`: a body of constant thickness. A boss, a pocket, a freeform or a
  closed hem's double thickness is `not_sheet` at its ref, and nothing after it is a sheet verdict.
- `bends`: `inside_radius_mm`, `angle_deg`, `k_factor` with its source, `bend_allowance_mm`.
- Distances come in several conventions: `hole_to_bend` carries `distance_tangent_mm` (from where the
  bend's radius starts), `distance_centerline_mm`, `distance_inside_mm` and `distance_outside_mm`;
  `flanges` likewise. Each rule reads one and names it in its message. Compare a shop's own number
  only with the field in that shop's convention.
- `reliefs` lists every bend end where the flange runs on past the bend: a missing relief has
  `width_mm` 0. Corner reliefs are reported, not judged.

## Review the part

Collect alloy and temper, stock thickness and units, the cutting and forming process, critical
dimensions, and any shop bend table. Ask only for missing inputs that change the current decision;
otherwise state provisional assumptions.

A projection of a bent solid is not an unfolded blank. `cad.build123d.unfold(shape, k_factor=...)`
in a check script returns the flat pattern the check measured; with bend angle theta in radians,
each bend adds BA = theta * (inside radius + K * thickness). Do not treat a chart's K as a production
dimension: take it from the shop's table.

Check by hand what the check does not measure: bend order, tooling access and collisions while
bending; grain direction; hardware (PEMs) and their distances; window bends; box flange maxima;
bump-formed or conical bends; a hole crossing a bend, or a curved bend end (both unrolled from
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

It runs the drawing checks every export runs ([2D profiles and DXF](2d-profiles-and-dxf.md#check-a-drawing))
and judges the cut layout: open geometry on a cut layer (`sheet.open_contour`), curves cut twice
(`sheet.overlapping_curves`), self-intersecting and crossing contours, zero-area loops, a piece that
falls out of a hole (`sheet.floating_interior`), text or dimensions on a cut layer, a curve drawn as
short lines, and holes, webs and gaps against the thickness. `measurements.cut_file` gives the
units, extents and layers. Then read by hand:

- **Units.** With `$INSUNITS` unset or unknown no size is compared with a rule (`units_suspect`).
  Compare `cut_file.extents_mm` with the part's expected size; never rescale silently.
- **Kerf.** Say whether the file is drawn to the finished size, with the shop's compensation, or
  already offset (`offset_profile`, `flat_pattern(..., kerf=)`): offsetting twice takes the kerf off
  twice. Take the kerf from the shop for the material and thickness.
- **What a cutting service needs.** Bend lines on their own named layer when the shop bends; marking
  text as outlines on its own layer when the shop engraves; one part per file unless the shop takes
  nested sheets. On a router an internal corner takes the tool's radius.

A file that passes is a well-formed cut file, not an accepted order: the shop's own upload checks,
material and service limits still apply.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

`sheet.hole_to_bend at tab/face 12: hole-to-bend distance from the bend's tangent line 2.5 mm is
under the 4 mm minimum` (generic, 2 mm steel). Report a 1.5 mm shortfall and propose moving the hole
or a supplier-approved relief. If the shop's drawing measures from the bend centerline, compare its
number with `distance_centerline_mm` instead.
