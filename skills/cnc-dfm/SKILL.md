---
name: cnc-dfm
description: Review parts for CNC milling or turning manufacturability when the user asks about machining access, internal corners, deep features, workholding, or machining redesign.
---

# CNC DFM

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

Collect material, stock form, milling versus turning, available axes, critical
fits/tolerances, and the intended shop or tool constraints. If the process is
unspecified, discuss candidate setups without claiming a verified machining plan.

- For milling, identify pockets, internal corner radii, holes, thin walls, and
  approach directions. A cutter fitting in a pocket does not prove holder access.
- Compare actual internal radii with the proposed cutter radius. Report pocket
  depth, hole depth/diameter, and wall height/thickness separately; use the shop's
  material-specific reach limits instead of declaring one universal ratio.
- For turning, identify the rotation axis, diameters, bores, shoulders, grooves,
  and parting/workholding regions. Off-axis features may require live tooling or
  another setup. Rotational symmetry alone does not prove tool access.
- Review stock allowance, fixture contact, setup changes, inaccessible cavities,
  and collision risks. Treat setup counts as estimates until tool and fixture
  envelopes have been checked. No exact cycle time or quote without that evidence.
- Inspect thread callouts, engagement, drill-tip clearance, and tool runout.
  Distinguish modeled thread geometry from a drawing specification and follow
  the target shop's preferred thread representation.
- Separate geometry constraints from cost suggestions. Preserve functional
  interfaces; suggest relaxed tolerances only where function permits them.

Distinguish in-plane pocket corners from floor-to-wall roots: a flat end mill
can produce a sharp floor-to-wall junction. A root fillet is optional and may
require a corner-radius or ball tool and an extra finishing pass. For sharp
in-plane internal corners, consider larger radii or reliefs when acceptable.
A feature infeasible with one end mill is not infeasible for all manufacturing;
identify alternatives such as another setup, tooling, or EDM as proposals.

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
