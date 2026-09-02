---
name: burr
description: Browse local STEP, STL, and GLB files and check geometric interference between components in STEP assemblies. Use for Burr model folders, fullscreen CAD inspection, X-ray or solid views, assembly collision checks, clearance debugging, or source-repair loops driven by Burr pass, fail, and incomplete results.
---

# Burr model inspection

Provenance: Burr is maintained at
[fraylabs/burr](https://github.com/fraylabs/burr). This skill is maintained in
[earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad). Use the
installed skill files as the runtime source of truth.

## Purpose

Use Burr as a fast local environment for browsing model files and checking
whether distinct components in a STEP assembly geometrically interfere. Repair
the owning CAD or electronics source, regenerate the artifact, and let Burr's
watcher refresh it.

Burr is a viewer plus one geometry-native assembly check. It is not the former
metadata/rulepack experiment: there is no `burr check`, `burr explain`, Burr
receipt file, or `burr-build123d` requirement in the current product.

## Use this skill when

Use this skill when the user asks to open or browse a folder of STEP, STL, or
GLB models, inspect geometry in Burr, switch between X-ray and solid rendering,
find component interference, compare a failing and repaired assembly, or obtain
evidence from Burr's Checks panel.

Use the owning CAD, KiCad, robot-description, or other source skill to create or
repair geometry. Burr consumes the generated model; it does not replace its
source system.

## Required tool check

```bash
burr --version
```

If Burr is missing, install it only when user authority and workspace policy
allow it. Do not call a screenshot or a different viewer “Burr evidence.”

## Start Burr

Run exactly one folder-oriented command:

```bash
burr path/to/model-folder
```

From inside a project, the usual form is `burr .`. Burr recursively discovers
STEP/STP, STL, and GLB files, keeps the folder hierarchy in the sidebar, opens a
local browser, and watches for file changes.

Use `.burr/config.toml` only when a project needs explicit model roots. Do not
invent rulepacks or add configuration before the unconfigured folder workflow
actually becomes noisy.

## Required workflow

Load `references/inspection-loop.md` when evaluating or repairing an assembly.

1. Start Burr at the narrowest useful project folder.
2. Select the intended model explicitly; do not rely on the initial automatic
   selection when collecting evidence.
3. Visually inspect representative views. X-ray is the default and is useful
   for internal placement; Solid is useful for exterior shape and occlusion.
4. For STEP assemblies, open **Checks** and read the outcome, summary, component
   count, checked-pair count, findings, and any incomplete reasons.
5. Treat `fail` as a detected interference and `incomplete` as a blocked clean
   claim. A clean-looking screenshot never overrides either result.
6. Repair the source that owns the geometry, regenerate the same artifact, and
   confirm the watched model refreshes.
7. Repeat both the affected visual view and the Checks result. Preserve a
   negative fixture when it materially proves the checker catches the intended
   defect.

## Outcome semantics

- `pass`: Burr completed the assembly-interference check and found no
  interference across the reported component pairs.
- `fail`: Burr found one or more interfering component pairs. Select a finding
  to highlight the involved components and use the reported names to locate the
  owning source.
- `incomplete`: Burr could not make a clean claim, for example because the file
  is not a supported STEP assembly or a component mesh is open/inconclusive.
- STEP, STL, and GLB can all be viewed; only supported STEP assemblies receive
  the assembly-interference claim.

Do not translate `pass` into “fits in production.” Exact contact, intended
press fits, flexible parts, tolerance stacks, motion, and material deformation
need design intent or other analysis Burr does not currently have.

## Evidence

Useful evidence combines:

- the explicit model path and Burr version;
- the Checks outcome and exact summary;
- component names and finding text for a failure;
- a representative screenshot, preferably the same view for fail/pass pairs;
- the source edit that produced the repaired artifact.

Do not use only a cropped result badge when the geometry is the point. Include
enough of the viewer to make the interference or repaired clearance legible.

## Non-negotiables

- Fix source, never generated STEP/STL/GLB or Burr responses.
- Do not describe ordinary visual inspection as an interference pass.
- Do not describe `incomplete` as “mostly passed.”
- Do not make Burr a required runtime dependency of the source skill that owns
  a KiCad board or CAD model.
- Do not revive removed rulepack, metadata, or repair-packet commands.

## Progressive references

- `references/inspection-loop.md` — assembly structure, fail/pass repair, KiCad
  handoff, and honest reporting.

Final responses should include the model and source paths, Burr version, outcome
and summary, screenshots when collected, repair performed, and unsupported or
inconclusive scope.
