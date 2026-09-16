---
name: sheet-metal-dfm
description: Review sheet-metal parts for cutting, bending, relief, and flat-pattern risks when the user asks whether a part can be fabricated from sheet stock.
---

# Sheet Metal DFM

Produce a process-specific DFM review of the supplied design. This is a guided
review skill, not an automatic feature-recognition or manufacturing certification
engine. It includes no geometry analyzer. Use available CAD inspection tools or
traceable supplied measurements; report unavailable checks explicitly.

## Evidence first

Read [process review guidance](references/process-review.md) before comparing
features to limits. Prefer the user's actual supplier/tooling specification over
general guidance. Record conflicting specifications rather than silently choosing.

Identify the reviewed file and revision, units, and bodies. Prefer exact STEP/B-rep
measurements for radii and analytic faces. If only a mesh is available, record
its resolution and approximation limits. A screenshot supports a suspected issue,
not a measured pass/fail. Source-code parameters describe design intent; verify
that they match the artifact being reviewed before treating them as evidence.

When $cad is available, use its documented inspection workflow for geometry facts.
If it cannot measure a required feature, use supplied dimensions with provenance
or mark the check unverified; do not invent commands or measurements. Never infer
alloy, resin, strength, or stock thickness from a rendering material or color.

## Process review

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

## Report and redesign

Return a concise Markdown report in chat or the user's requested report file:

- Scope: artifact/revision, parts, process, material, units, tooling assumptions.
- Findings: part/feature, evidence and measurement method, applicable rule and
  source, result, and a concrete suggested change.
- Coverage: checks performed and checks not measured, including what is needed
  to resolve them. No findings is not a blanket manufacturability approval.

Use **pass** only for a measured feature satisfying a cited applicable limit;
**fail** for a measured violation; **review** for a qualitative risk; and
**unverified** when evidence or process context is missing. Include units,
measurement uncertainty, and source section/table in numerical comparisons.
If uncertainty straddles the threshold, leave the check unverified. Keep cost
suggestions separate from manufacturing constraints.

For requested redesign, preserve the original artifact and use $cad if available
to modify the source, regenerate, and recheck the new artifact. Check affected
neighboring features as well as the original finding. Without editing tools,
provide a specific change list. A review request alone does not request edits,
uploads, ordering, or machine operation.
