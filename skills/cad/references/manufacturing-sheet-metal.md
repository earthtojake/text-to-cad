# Sheet metal

The evidence, the rules, the review and how to check a redesign are SKILL.md's
[Can it be made?](../SKILL.md#can-it-be-made), the same for every process; this is what is particular
to cutting and bending sheet.

An order from SendCutSend, checked against its catalog and specs, is the sendcutsend skill's
($sendcutsend).

## Sources

Where the person supplies no shop specification, start from these two:

- [Sheet metal fabrication design guide](https://www.hubs.com/guides/sheet-metal-fabrication/) (Protolabs Network) for the design rules: K-factor and bend allowance, bend radius and relief, hems and curls, laser-cut hole and edge spacing, kerf, welding, tolerances.
- [Sheet-metal guidelines](https://www.protolabs.com/services/sheet-metal-fabrication/design-guidelines/) (Protolabs) for that supplier's component sizes, material and thickness range, tolerances, bending guidelines, and common-feature rules for flanges, hems, reliefs and holes.

Check the current tables for the exact stock and tooling rather than importing
a universal minimum radius or flange length.

## Measure it

```bash
cad step inspect part.step                    # parts, bounds, volume
cad step inspect part.step 'face 9'           # one face: a bend's cylinder and its radius, a hole's
cad xbf inspect "$ID" 'bracket/face 4'        # the same of a model's face
```

A bend is a pair of cylindrical faces, inside and outside, whose radii differ by the stock thickness:
the smaller is the inside radius. A hole-to-bend distance depends on its convention: to the bend's
tangent line (where the bend's cylinder meets the flat), to its centerline, or to the outside of the
flange. Measure the one the shop's rule uses, from the faces' boxes or a check script, and say which.

## Review the part

Collect alloy and temper, nominal stock thickness and units, cutting/forming process,
critical dimensions, and any shop tooling or bend table. Ask only for missing inputs
that change the current decision; otherwise state provisional assumptions.

- Check whether each body represents constant-thickness sheet. Review matched
  inner/outer surfaces; a bounding-box dimension is not a thickness measurement.
- Identify bends, inside radii, angles, flanges, holes, slots, and reliefs per part.
  Distinguish inside radius from outside radius. Record feature locations.
- Compare radii, flange lengths, relief dimensions, and hole-to-bend distances
  against the selected shop's rules. State the distance convention (bend tangent,
  centerline, or edge) before comparing; those dimensions are not interchangeable.
- For flat cutting, review the cut file ([below](#cut-files-dxf)). A projection of a
  bent solid is not an unfolded blank. Use an existing flat pattern or verified unfolding.
- Compute bend allowance only with a specified convention and K-factor or bend
  table. With bend angle theta in radians, BA = theta * (inside radius + K * thickness).
  Do not treat a guessed K-factor as a production dimension.
- Check bend order, tooling access, hems, hardware, grain direction, and collision
  risks when relevant. Missing tooling or a valid unfold leaves these unverified;
  a valid STEP solid alone does not establish forming feasibility.

A clean DXF or flat pattern, or a successful upload to a supplier, does not
establish that all bends can be made.

## Cut files (DXF)

A laser, plasma, waterjet or routing shop cuts the DXF, so review the exact file it gets (a
text-to-cad drawing's is the one `cad xbf export <id> part.dxf` wrote), not the model it came from.
How a drawing is made and exported, and the drawing checks every export runs, are
[2D profiles and DXF](2d-profiles-and-dxf.md#check-a-drawing). Run `validate_dxf_file` on a file
from elsewhere, and read with `ezdxf` what the checks do not decide:

- **One file at 1:1, in known units.** `$INSUNITS` 4 is millimetres and 1 inches; the drawing checks
  only require it to be set. A missing or unexpected code is a scale error until the person confirms
  the units: never rescale silently, and compare no size against a rule on an uncertain scale.
  Compare the measured extents (`ezdxf.bbox.extents`) with the part's expected size.
- **Closed contours on every cut layer.** A cut path that does not close cuts nothing out. Open
  geometry belongs on a layer named for a bend, an engraving or a reference; open geometry on a cut
  layer is a finding. A file holding dimensions, viewports or paper space is read as a dimensioned
  drawing, and the closure check then does not run: a cut file holds none.
- **Nothing cut twice.** The checks refuse an exact duplicate; an overlapping, partly coincident or
  self-intersecting curve passes them and still cuts twice or leaves a sliver. Look for coincident
  segments between neighbouring contours and degenerate, zero-area loops.
- **Kerf.** Say whether the file is drawn to the finished size, with the shop's own compensation, or
  already offset (`offset_profile`, `flat_pattern(..., kerf=)`): offsetting twice takes the kerf off
  twice. Take the kerf from the shop for the material and thickness.
- **Small features against the thickness.** Hole and slot sizes, web and bridge widths, and
  hole-to-edge and hole-to-hole spacing, compared with the shop's minimums for the material and
  thickness (the sources above give typical ones). On a router an internal corner takes the
  tool's radius.
- **What a cutting service needs.** The geometry alone on cut layers: no `TEXT`, dimensions, title
  blocks, images or construction lines there (marking text as outlines on its own layer, when the
  shop engraves); bend lines on their own named layer when the shop bends; one part per file unless
  the shop takes nested sheets; curves as arcs and circles rather than runs of short lines.

A file that passes these checks is a well-formed cut file, not an accepted order: the shop's own
upload checks, material and service limits still apply.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

A hole is 3 mm from a bend tangent, but the shop gives a 5 mm minimum measured
from that same tangent: report a 2 mm shortfall and propose relocation or a
supplier-approved relief. If the drawing instead measures from the bend
centerline, resolve the convention before comparing.
