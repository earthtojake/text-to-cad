# Process review evidence

## Rule selection

1. Use the selected shop's specification for the actual material and process.
2. Where none is supplied, use two references from the same supplier as a starting point:
   - [Injection molding design guide](https://www.hubs.com/guides/injection-molding/) (Protolabs Network) for the design rules: wall thickness and hollowing thick sections, draft, ribs, bosses, undercuts and side actions, snap fits and living hinges, common defects (sink, warp), and the straight-pull cost tips.
   - [Plastic injection molding guidelines](https://www.protolabs.com/services/injection-molding/plastic-injection-molding/design-guidelines/) (Protolabs) for that supplier's size limits, resin-specific wall thickness table, draft, undercut and radii guidance.
   Texture, wall depth, resin grade, fillers, and tooling can change the applicable limits. Verify the current guidance before citing numerical thresholds.
3. Record URL/document version, access date, section, units, and the applicable
   material/tooling conditions with every adopted limit. If the source cannot
   be checked, report the missing rule rather than manufacture a default.

Do not turn a supplier's recommendation into a physical law or its machine
capacity into a universal process limit. Preserve uncertainty and distinguish
measured geometry from planned manufacturing decisions.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

If a side wall has measured 0.5 degree draft (from `scripts/mold_tool.py measure --pull <axis>`) relative to the confirmed pull and the selected texture/tooling specification requires 2 degrees, report the shortfall for that wall. Without a confirmed pull direction, report draft as unverified rather than failing every vertical-looking face.

## Finding format

| Part / feature | Evidence | Applicable rule | Result | Suggested action |
| --- | --- | --- | --- | --- |
| Named feature + location | Measured value, units, artifact revision, method | Source section + threshold + conditions | pass / fail / review / unverified | Specific change or missing evidence |

If only a render is provided, list visible concerns as review items and request
geometry or dimensions for the required measurements. Never fill a report with
invented feature IDs or sample values from this reference.
