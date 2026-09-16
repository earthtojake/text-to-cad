# Process review evidence

## Rule selection

1. Use the selected shop's specification for the actual material and process.
2. Where none is supplied, consult [CNC milling guidelines](https://www.protolabs.com/services/cnc-machining/cnc-milling/design-guidelines/) as a starting point.
   Use this supplier-specific reference for milling capabilities, feature dimensions, and thread conventions. It does not establish the capabilities of an arbitrary lathe, five-axis machine, or custom fixture. Obtain the actual turning/tooling specification when reviewing those processes.
3. Record URL/document version, access date, section, units, and the applicable
   material/tooling conditions with every adopted limit. If the source cannot
   be checked, report the missing rule rather than manufacture a default.

Do not turn a supplier's recommendation into a physical law or its machine
capacity into a universal process limit. Preserve uncertainty and distinguish
measured geometry from planned manufacturing decisions.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

A measured 2 mm internal corner radius cannot be reproduced by a proposed 6 mm diameter cylindrical end mill: its 3 mm radius is too large. A smaller cutter may fit, but reach, holder clearance, material, and pocket depth remain separate checks.

## Finding format

| Part / feature | Evidence | Applicable rule | Result | Suggested action |
| --- | --- | --- | --- | --- |
| Named feature + location | Measured value, units, artifact revision, method | Source section + threshold + conditions | pass / fail / review / unverified | Specific change or missing evidence |

If only a render is provided, list visible concerns as review items and request
geometry or dimensions for the required measurements. Never fill a report with
invented feature IDs or sample values from this reference.
