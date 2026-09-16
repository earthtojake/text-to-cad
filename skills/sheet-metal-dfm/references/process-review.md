# Process review evidence

## Rule selection

1. Use the selected shop's specification for the actual material and process.
2. Where none is supplied, use two references from the same supplier as a starting point:
   - [Sheet metal fabrication design guide](https://www.hubs.com/guides/sheet-metal-fabrication/) (Protolabs Network) for the design rules: K-factor and bend allowance, bend radius and relief, hems and curls, laser-cut hole and edge spacing, kerf, welding, tolerances.
   - [Sheet-metal guidelines](https://www.protolabs.com/services/sheet-metal-fabrication/design-guidelines/) (Protolabs) for that supplier's component sizes, material and thickness range, tolerances, bending guidelines, and common-feature rules for flanges, hems, reliefs and holes.
   Check the current tables for the exact stock and tooling rather than importing a universal minimum radius or flange length.
3. Record URL/document version, access date, section, units, and the applicable
   material/tooling conditions with every adopted limit. If the source cannot
   be checked, report the missing rule rather than manufacture a default.

Do not turn a supplier's recommendation into a physical law or its machine
capacity into a universal process limit. Preserve uncertainty and distinguish
measured geometry from planned manufacturing decisions.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

A hole is 3 mm from a bend tangent, but the shop gives a 5 mm minimum measured from that same tangent: report a 2 mm shortfall and propose relocation or a supplier-approved relief. If the drawing instead measures from the bend centerline, resolve the convention before comparing.

## Finding format

| Part / feature | Evidence | Applicable rule | Result | Suggested action |
| --- | --- | --- | --- | --- |
| Named feature + location | Measured value, units, artifact revision, method | Source section + threshold + conditions | pass / fail / review / unverified | Specific change or missing evidence |

If only a render is provided, list visible concerns as review items and request
geometry or dimensions for the required measurements. Never fill a report with
invented feature IDs or sample values from this reference.
