---
title: SendCutSend
description: Check a DXF or STEP file against SendCutSend's published ordering guide, catalog and specs before you upload it, and get a cited report.
---

SendCutSend is an online service that laser cuts, routes and bends parts from files you upload. text-to-cad can check a DXF or STEP file against the guidelines SendCutSend publishes before you upload it, and give you a report. This is a pre-upload check against their published documents. It is not an official SendCutSend integration, it does not talk to your SendCutSend account, and SendCutSend's own upload and quote have the last word.

## What to ask

- "Check `bracket.dxf` against SendCutSend's guidelines for laser cutting. The material is 5052 aluminium, 0.063 in."
- "Is `housing.step` ready to upload to SendCutSend for CNC routing? Tell me what to change."
- "Review my bent part for SendCutSend: bend radius, flange length, and holes near the bends."
- "Export the bracket model as a DXF and preflight it for SendCutSend in mild steel."
- "Which SendCutSend materials and thicknesses could I pick for this part?"

## What your agent does

1. Collects the order context: file type, process (laser cutting, CNC routing, bending, tapping, countersinking, hardware insertion, finishing), material or SKU, thickness, quantity, finish. DXF suits laser sheet cutting and 2D profiles. STEP suits CNC routing and 3D uploads. If the context is missing, your agent lists candidate materials and thicknesses with links from SendCutSend's data and asks you to choose before it gives a verdict.
2. Fetches SendCutSend's three published source files fresh each time:
   - the ordering guide, for the workflow and file format rules,
   - the catalog JSON, for what is orderable: materials, thicknesses, size limits and services,
   - the specs JSON, for engineering values such as hole, bridge and bend figures, joined to the catalog by exact SKU.

   These are treated as data that can change or have gaps, not as a stable API. If they cannot be fetched, the report says so and gives no ready verdict for the checks that depend on them.
3. Measures your actual upload file, not the script that made it. For a STEP:

   ```bash
   cad step inspect part.step
   cad step inspect part.step 'face 9'
   ```

   The first gives bodies, bounds and volume. The second reads one face, such as a bend's cylinder and its radius. For a model's upload, your agent exports it first with `cad model export <id> part.step` or `part.dxf` and inspects that file.
4. Runs the general sheet-metal check on the file, with the SKU's own figures where the specs list them:

   ```bash
   cad step dfm part.step --process sheet --material <material> --thickness <mm> --json
   cad dxf dfm part.dxf --material <material> --thickness <mm> --json
   ```

   This is text-to-cad's check, not SendCutSend's. Its measurements are compared with the specs, and its general findings appear beside them. See [manufacturing checks](/docs/guides/manufacturing-checks).
5. Compares each measured fact with the cited requirement, and writes the report.

## What you get

A report with the file, the assumed service and order context, the source files and the date they were fetched, the measured geometry facts, and a findings table. Each row has a status, the check, the evidence, a rule source and a recommendation. The rule source links to the specific document or JSON field path, or says "Direct file inspection" where no external rule applies.

The statuses are three: pass, fail, and need more info. Any measured upload risk or manufacturability issue counts as a fail for now. Your agent does not invent an alternative classification.

The verdict is one of "Ready to upload for this assumed context", "Needs edits before upload" or "Insufficient context to validate". A ready verdict needs every required check to pass or to be outside the selected service.

For a DXF, the checks include:

- units: `$INSUNITS` must be `1` (inches) or `4` (mm), otherwise it is reported as a scale error and nothing is rescaled
- closed cut profiles, duplicate or overlapping geometry, and unsupported text, dimensions or images
- for bend lines, the flange length measured locally on both sides of each bend, not as one aggregate figure

For a STEP, they include readability, a solid body, units, bounding box, thickness and, where bending is in scope, bend radii compared with the SKU's tooling radius. Where a spatial finding is hard to explain in words, your agent adds a diagram if it can generate images.

## Limits

- It checks against the guidelines SendCutSend publishes, and states only limits the sources give. Where a source field is missing, unparsable or `N/A`, the row is "need more info", not a pass or a fail.
- It cannot say whether SendCutSend's own upload will accept the file or what it will quote. Use their upload as the final check.
- A fail or pass is only as good as the order context. A different material, thickness or service changes the limits.
- If a source does not expose an exact threshold, such as a bend's die-area contact, the row cites direct file inspection and marks the comparison as limited by the source.
- It needs network access to fetch the three source files.

## Go deeper

- [The sendcutsend skill](repo:skills/sendcutsend/SKILL.md), [the official source map](repo:skills/sendcutsend/references/official-sources.md) and [the report template](repo:skills/sendcutsend/references/report-template.md).
- [Manufacturing checks](/docs/guides/manufacturing-checks), the shop-neutral sheet-metal and cut-file review.
- [DXF profiles](/docs/guides/dxf-profiles), for making the cut file, and [the `dxf` document type](/docs/document-types/dxf).
- [The `step` document type](/docs/document-types/step).
- [Engineering drawings](/docs/guides/engineering-drawings), if you also need a dimensioned sheet for the part.
