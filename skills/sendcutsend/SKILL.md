---
name: sendcutsend
description: Review DXF and STEP/STP uploads for SendCutSend.com orders using its ordering guide, catalog, and specs. Use only for SendCutSend.com preflight reports covering upload readiness, selected material/SKU/thickness/service availability, and service-specific checks for laser cutting, CNC routing, bending, tapping, countersinking, hardware insertion, and finishing.
---

# SendCutSend

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill to produce conservative, evidence-backed SendCutSend preflight reports for DXF and STEP/STP files.

Treat SendCutSend's ordering guide, catalog JSON, and specs JSON as evidence feeds, not stable APIs. Field names, types, and coverage may vary. Do not turn missing, unparsable, `N/A`, or conflicting source data into a pass or fail. Fetch sources directly from official URLs and use local inspection code only to measure specific file facts; write the final report from explicit comparisons.

## Geometry Inspection

Use the active project Python environment for local geometry inspection code. If the `$cad` skill is available, use it first for STEP/STP/DXF geometry inspection, measurement, and validation workflows, then add any SendCutSend-specific targeted measurements that are still missing. Use `build123d.import_step` for STEP/STP inspection and `build123d.ezdxf` for DXF inspection when geometry facts are required. Do not use raw text parsing or alternate geometry backends for geometry facts.

## CAD Viewer Handoff

After completing SendCutSend work that creates or modifies a `.dxf`, `.step`, or `.stp` upload candidate, you must ALWAYS hand the explicit file path(s) to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); if `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Official Sources

Before each review, fetch and inspect the current SendCutSend source documents directly from the official URLs listed in `references/official-sources.md`:

Use the source URL, access date, and JSON `_meta` values in the source bibliography when helpful. If a source cannot be fetched, report that current SendCutSend sources were unavailable and avoid ready verdicts for dependent checks.

## Workflow

1. Collect order intent.
   - Prefer DXF for laser sheet cutting and 2D sheet profiles.
   - Prefer STEP/STP for CNC routing and 3D model upload workflows.
   - Record file type, intended process, material/SKU, thickness, quantity, services, finish, and hardware.
   - If order context is missing or ambiguous, inspect enough source data to present concrete options, then ask the user to confirm before writing a readiness verdict. Include candidate SKUs/materials/thicknesses/services with relevant source links; include `photo_url` images and `learn_more_url` links from the specs JSON when available.
2. Read `references/official-sources.md`, fetch the official sources directly, then inspect the returned documents. Normalize source facts defensively: parse numeric strings, size strings, `N/A`, missing fields, mixed types, and absent service arrays into explicit notes.
3. Inspect the exact upload file with `$cad` when available and with targeted Python/`build123d` for any missing facts. Do not inspect only the source generator, CAD model, or generator console summary.
   - DXF: measure units, bounds, layers, entity types, open/duplicate geometry, unsupported annotations, candidate holes/circles, linework stats, bend-line candidates, bend-to-cut distances, bend-adjacent cut geometry, local flange depths, and degenerate zero-area contours as needed for the selected service.
   - STEP/STP: measure parseability, units hints, solid/surface signals, bounding box, shell/body signals, validity, sheet thickness where available, cylindrical bend-face radii where bending is in scope, and limitations as needed for the selected service.
   - Keep each inspection helper fact-only. It may report measurements, parse errors, and limitations, but it must not emit pass/fail/readiness statuses.
4. Select source records by evidence quality.
   - Use exact SKU as the only authoritative catalog/spec join.
   - If only material and thickness are provided, use a selected material only when the candidate match is unique and exact enough; otherwise list candidates with links/images from the source records and ask the user to choose.
   - Use the catalog JSON for orderability: stock, cutting process, available services, size limits, hardware, and finishes.
   - Use the specs JSON for engineering values: tolerances, holes, bridges, bending, tapping, countersinking, hardware insertion, finishing, and material properties.
   - Use the ordering guide for plain-language workflow and general file-format rules.

## Comparison

Compare only trustworthy pairs of evidence.

- Determine whether a check applies.
- Cite the source field path or guide section.
- Cite the measured file fact.
- Compare only when both the source requirement and measured file fact are available and trustworthy.
- If a needed measurement is missing or risky, write a small targeted `build123d`/`ezdxf` inspector for that specific geometry fact.
- Treat every measured upload risk, manufacturability issue, or cited requirement violation as an error for now. Do not infer any alternate SendCutSend UI classification.
- For DXF units, inspect `$INSUNITS`, header extents, measured bounds, and order context together. If `$INSUNITS` is missing, unsupported, or not one of the SendCutSend guide's expected DXF unit codes (`1` inches or `4` mm), report a unit/scale error and recommend re-exporting or confirming units before applying size-, flange-, or material-specific comparisons. Do not silently rescale geometry or use an uncertain scale to issue material-specific pass/fail checks.
- For 2D files with bend lines, check flange length locally along every bend line. Measure the nearest cut/free edge on both sides of each bend at each span or sample point, including notches, slots, gaps, split tabs, and cutouts that interrupt the bend span or create a local free edge. Compare the minimum local flange depth to the selected SKU's `bending_specs.min_flange_length_before_bend` and `bending_specs.min_flange_length_after_bend`. Do not apply flange-length limits to ordinary enclosed holes or interior cutouts unless a cited source gives a hole-to-bend or feature-to-bend rule for that service; report those separately with centerline-to-bend or edge-to-bend measurements as the cited rule requires. Do not treat nearby bend-adjacent cut geometry as only corner relief unless the remaining local flange still passes the flange-length minimum. If any local flange depth is below the SKU minimum, report `❌ fail`. Do not rely on aggregate source-level values when exported geometry has local cutouts, interrupted bends, split bend segments, reliefs, tabs, or unsupported regions.
- Keep bend findings separate by physical cause. Do not collapse bend-adjacent geometry into a generic flange failure. Report distinct rows for minimum flange/contact length errors, bend line or die-area geometry crossings, insufficient bend contact/support from nearby free edges or cutouts, bend lines that do not span the bent region, split/common-axis bend segments, and cut geometry touching or crossing bend lines. If a SendCutSend source does not expose the exact die-area/contact threshold, cite the measured file fact as direct file inspection and mark the source-limited comparison explicitly.
- For STEP/STP bent parts, inspect bend radii when the model contains sheet-metal bend geometry or the intended service includes bending. Extract cylindrical or toroidal bend faces and their radii with `$cad`/`build123d`/OCP where possible, group repeated bend radii, and compare them to the selected SKU's `bending_specs.effective_bend_radius` or `bending_specs.bend_radius`. If the selected material/SKU is unknown, report the measured bend-radius set and ask for material/thickness before readiness verdicts. If measured radii conflict with the selected SKU tooling radius, report a bend-radius mismatch error.

Report with restrained status labels:

- `✅ pass`: the measured file fact satisfies the cited current requirement.
- `❌ fail`: a measured upload risk, manufacturability issue, or direct measured violation of a cited current requirement.
- `❓ need more info`: missing context, missing source evidence, unmeasured geometry, source conflicts, or tool limitations.

## Diagnostic Images

When findings would be easier to understand visually, produce a concise diagnostic diagram proactively if image-generation or image-editing capabilities are available. Use generated or edited images for callouts, legends, and before/after explanations. Do this without waiting for the user to ask whenever there is a `❌ fail`, a spatially ambiguous geometry issue, or a geometry edit that needs a before/after explanation. If image-generation tools are unavailable, state that limitation and describe the intended diagram in the report.

Before generating an image, run a layout preflight:

- Choose the smallest set of callouts needed to explain the fix.
- Estimate whether labels will crowd the geometry, overlap each other, or run outside the canvas. If crowding is likely, flag it before generation and switch to numbered markers plus a side legend, a larger canvas, or separate detail views.
- Keep long measured values and rule text in the legend, not directly over dense geometry.
- Include the measured failing distance, the cited minimum, and the proposed movement or clearance target.

After generating an image, inspect the rendered image before delivery. If labels overlap, are clipped, are hard to read, or obscure the geometry, regenerate or revise the diagram before reporting it.

## DXF Review

For laser sheet cutting, start from the refreshed sources and measured DXF geometry facts.

Check for:

- single, uploadable DXF file with model geometry at 1:1 scale
- units and overall part size; treat missing, unsupported, or unexpected `$INSUNITS` as a scale error until the user confirms units
- closed cut profiles where the service requires closed contours
- degenerate or zero-area closed contours, two-point closed polylines, and odd-degree cut endpoints
- duplicate or overlapping cut geometry
- unsupported annotation, text, dimensions, images, construction lines, or hidden instruction layers
- layer/color/linework conventions from the ordering guide and upload workflow
- bend-line entities, bend segment lengths, split/common-axis bends, local flange depth on both sides of each bend line, nearest non-bend cut edge or cutout distances, bend-line span coverage, insufficient bend contact/support, die-area or bend-adjacent cut geometry crossings, and cut geometry touching or crossing bend lines when bending is in scope
- minimum holes, slots, web widths, interior geometry, part density, nesting, and spacing only when both source facts and measured file facts support a comparison
- secondary-service requirements for bending, tapping, countersinking, hardware, finishing, or deburring when requested

## STEP Review

For CNC routing or 3D model upload, start from the refreshed sources and measured STEP geometry facts.

Check for:

- STEP/STP file readability and a solid body rather than loose curves or surfaces
- units, scale, bounding box, thickness, and feature dimensions
- sheet-metal bend radii when bending is in scope; compare measured cylindrical bend-face radii to the selected SKU's `bending_specs.effective_bend_radius` or `bending_specs.bend_radius`
- sharp inside corners, small holes/slots, thin walls, islands, deep pockets, tool access, and tolerances only when the file inspection can measure the fact
- whether geometry represents a sheet profile better served as DXF for laser cutting
- material, thickness, finish, and secondary-service compatibility

## Reporting

Include the file path, assumed service, material/order context, source files checked with access date, inspected geometry facts, findings ordered by practical impact, and specific next edits. In the findings table, include a `Rule source` column with Markdown links to the source URL plus the specific JSON field path or guide section used for that row. If a row is based only on direct file inspection and has no external rule, say `Direct file inspection`; do not leave the source blank. Do not call a file "SendCutSend ready" unless every required cited check either passes or is explicitly outside the selected service.

Use `references/report-template.md` when a structured report would help.

## References

- Official source selection: `references/official-sources.md`
- Report shape: `references/report-template.md`
