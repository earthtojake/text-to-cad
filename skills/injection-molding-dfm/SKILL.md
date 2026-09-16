---
name: injection-molding-dfm
description: Review thermoplastic injection-molded parts for draft, wall transitions, ribs, bosses, undercuts, and tooling assumptions when the user asks about moldability or molding redesign.
---

# Injection Molding DFM

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

Collect resin grade/filler, nominal wall, pull direction, proposed parting line,
texture/cosmetic faces, critical fits, and tooling constraints. Treat unknown
resin or pull direction as missing context, not permission to guess a verdict.

- Review local wall thickness and transitions, including rib and boss junctions.
  Sampling must state its coverage. Thick intersections can matter even when
  nominal walls are consistent. Compare with resin-specific guidance.
- Evaluate draft relative to the stated pull direction, separating core/cavity
  sides and textured faces. Zero draft means a wall parallel to the pull direction;
  top/bottom faces perpendicular to it should not be flagged as zero-draft walls.
- Identify candidate undercuts and trapping features relative to the proposed
  parting and pull. A normal-angle check alone is not a complete undercut test;
  visibility/occlusion and the full withdrawal path matter. Distinguish a need
  for side actions or inserts from impossibility of molding.
- Review ribs, bosses, corner transitions, shutoffs, and likely ejection access.
  Flag sink/warpage risks qualitatively unless a relevant analysis was run.
- Discuss gate, vent, weld-line, packing, cooling, and shrinkage implications as
  tooling questions; geometry review does not simulate filling or predict a
  validated cycle time. Do not rescale the finished part for shrinkage without
  the toolmaker's resin/process assumptions.
- Preserve mating faces and functional dimensions when proposing draft or
  coring. Identify which datum stays fixed and whether the proposed change
  adds or removes material.

This workflow reviews conventional thermoplastic injection molding. For silicone,
overmolding, or insert molding, identify the additional process requirements
and obtain applicable guidance rather than reusing thermoplastic limits blindly.

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
