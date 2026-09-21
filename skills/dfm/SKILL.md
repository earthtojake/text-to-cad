---
name: dfm
description: Design-for-manufacturing review of a part for sheet metal, CNC machining, or injection molding - bends, reliefs and flat patterns; machining access, internal corners, deep features and setups; draft, undercuts and projected area. Use when the user asks whether a part can be bent, machined or molded, asks about manufacturability or tooling, or asks for a DFM review or redesign.
---

# DFM review

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

Produce a process-specific DFM review of the supplied design. This is a guided
review skill, not an automatic feature-recognition or manufacturing
certification engine. Report unavailable checks explicitly.

**Pick the process, then read its reference.** One of them, or more than one
when the user is comparing:

| Process | Reference | Measurement |
| --- | --- | --- |
| Sheet metal | [references/sheet-metal.md](references/sheet-metal.md) | none; use CAD inspection or supplied dimensions |
| CNC machining / turning | [references/cnc.md](references/cnc.md) | none; use CAD inspection or supplied dimensions |
| Injection molding | [references/injection-molding.md](references/injection-molding.md) | `scripts/mold_tool.py` measures draft, undercuts and projected area |

Each reference carries that process's review checklist, its two fallback
sources, and a worked reasoning example. The rules below apply to all three.

For additive manufacturing, use `$dfam-check`, which measures mesh
printability per process.

## Evidence first

Prefer the user's actual supplier/tooling specification over general guidance.
Record conflicting specifications rather than silently choosing.

Identify the reviewed file and revision, units, and bodies. Prefer exact
STEP/B-rep measurements for radii and analytic faces. If only a mesh is
available, record its resolution and approximation limits. A screenshot
supports a suspected issue, not a measured pass/fail. Source-code parameters
describe design intent; verify that they match the artifact being reviewed
before treating them as evidence.

When $cad is available, use its documented inspection workflow for geometry
facts. If it cannot measure a required feature, use supplied dimensions with
provenance or mark the check unverified; do not invent commands or
measurements. Never infer alloy, resin, strength, or stock thickness from a
rendering material or color.

## Rule selection

1. Use the selected shop's specification for the actual material and process.
2. Where none is supplied, use the two references named in the process file as
   a starting point. Neither establishes the capabilities of an arbitrary
   machine, tool or fixture.
3. Record URL/document version, access date, section, units, and the applicable
   material/tooling conditions with every adopted limit. If the source cannot
   be checked, report the missing rule rather than manufacture a default.

Do not turn a supplier's recommendation into a physical law or its machine
capacity into a universal process limit. Preserve uncertainty and distinguish
measured geometry from planned manufacturing decisions.

## Report and redesign

Return a concise Markdown report in chat or the user's requested report file:

- Scope: artifact/revision, parts, process, material, units, tooling assumptions.
- Findings: part/feature, evidence and measurement method, applicable rule and
  source, result, and a concrete suggested change.
- Coverage: checks performed and checks not measured, including what is needed
  to resolve them. No findings is not a blanket manufacturability approval.

| Part / feature | Evidence | Applicable rule | Result | Suggested action |
| --- | --- | --- | --- | --- |
| Named feature + location | Measured value, units, artifact revision, method | Source section + threshold + conditions | pass / fail / review / unverified | Specific change or missing evidence |

Use **pass** only for a measured feature satisfying a cited applicable limit;
**fail** for a measured violation; **review** for a qualitative risk; and
**unverified** when evidence or process context is missing. Include units,
measurement uncertainty, and source section/table in numerical comparisons.
If uncertainty straddles the threshold, leave the check unverified. Keep cost
suggestions separate from manufacturing constraints. If only a render is
provided, list visible concerns as review items and request geometry or
dimensions for the required measurements. Never fill a report with invented
feature IDs or sample values.

For requested redesign, preserve the original artifact and use $cad if available
to modify the source, regenerate, and recheck the new artifact. Check affected
neighboring features as well as the original finding. Without editing tools,
provide a specific change list. A review request alone does not request edits,
uploads, ordering, or machine operation.

## Geometry measurement (injection molding only)

`scripts/mold_tool.py` is the one measurement script here; the other two
processes have no geometry analyzer. Install `requirements.txt` first — only
these measurements need it.

```bash
python scripts/mold_tool.py measure part.stl --pull z
python scripts/mold_tool.py pulls part.stl
```

The tool is fact-only: it reports measurements and never emits pass/fail.
Comparisons against resin, texture and tooling limits belong to the review.
[references/injection-molding.md](references/injection-molding.md) documents
what each fact family means and how to read it.
