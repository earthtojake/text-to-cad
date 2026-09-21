# Sheet metal

## Sources

Where the user supplies no shop specification, start from these two, and read
the shared rule-selection rules in `SKILL.md` before citing either:

- [Sheet metal fabrication design guide](https://www.hubs.com/guides/sheet-metal-fabrication/) (Protolabs Network) for the design rules: K-factor and bend allowance, bend radius and relief, hems and curls, laser-cut hole and edge spacing, kerf, welding, tolerances.
- [Sheet-metal guidelines](https://www.protolabs.com/services/sheet-metal-fabrication/design-guidelines/) (Protolabs) for that supplier's component sizes, material and thickness range, tolerances, bending guidelines, and common-feature rules for flanges, hems, reliefs and holes.

Check the current tables for the exact stock and tooling rather than importing
a universal minimum radius or flange length.

## Review

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
- For flat cutting, review closed contours, duplicate/intersecting curves, units,
  and small features against cutting capabilities. A projection of a bent solid
  is not an unfolded blank. Use an existing flat pattern or verified unfolding.
- Compute bend allowance only with a specified convention and K-factor or bend
  table. With bend angle theta in radians, BA = theta * (inside radius + K * thickness).
  Do not treat a guessed K-factor as a production dimension.
- Check bend order, tooling access, hems, hardware, grain direction, and collision
  risks when relevant. Missing tooling or a valid unfold leaves these unverified;
  a valid STEP solid alone does not establish forming feasibility.

Use $dxf, when available, for drawing/flat-pattern work and $sendcutsend only for
that supplier's requested handoff. Neither a clean DXF nor a successful upload
establishes that all bends can be made.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

A hole is 3 mm from a bend tangent, but the shop gives a 5 mm minimum measured
from that same tangent: report a 2 mm shortfall and propose relocation or a
supplier-approved relief. If the drawing instead measures from the bend
centerline, resolve the convention before comparing.
