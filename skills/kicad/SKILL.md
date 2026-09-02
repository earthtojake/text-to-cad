---
name: kicad
description: Create, modify, validate, and mechanically hand off KiCad electronics projects. Use for .kicad_sch schematics, .kicad_pcb boards, symbols, footprints, ERC, DRC, fabrication exports, component placement, board outlines, mounting holes, connector envelopes, or STEP exports from KiCad.
---

# KiCad electronics workflow

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed skill files as the runtime source of truth; the repository
link is only for provenance and release review.

## Purpose

Work in KiCad as the source of truth for electronics. Keep schematic intent,
PCB layout, footprints, component placement, and electrical validation in the
KiCad project. Export mechanical geometry only when another tool needs to
inspect the board in a larger assembly.

This skill does not turn an electronics project into generic mechanical CAD.
It owns the board through verified KiCad outputs; an enclosure, robot chassis,
or system assembly remains in its owning mechanical source.

## Use this skill when

Use this skill for KiCad projects and files, schematic capture, PCB layout,
symbol or footprint libraries, board outlines, holes, keepouts, connector
placement, ERC/DRC, manufacturing outputs, or KiCad STEP export.

Do not use it for a standalone mechanical part, enclosure-only modeling, CAM
toolpaths, circuit simulation claims, regulatory certification, or PCB fab
approval unless the user also asks for KiCad project work.

## Required tool check

Confirm the CLI before relying on it:

```bash
kicad-cli --version
```

On macOS, an app-bundle install may expose the executable at a path such as
`/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli` without putting it on
`PATH`. Discover the actual installation rather than committing an absolute
machine path. If KiCad is unavailable, install it only when workspace policy
and user authority allow it; otherwise report the blocker.

Use the installed CLI's `--help` for commands outside the examples below.
KiCad subcommand details can change between major versions.

## Required workflow

1. **Inspect the project.** Read its README and contribution notes, then locate
   the `.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, project symbol/footprint tables,
   and project-local 3D models. Preserve unrelated board work.
2. **Separate the intents.** Write down the electrical change and any
   mechanically relevant change. A label edit is not a connector-placement
   change; a footprint move can be both electrical and mechanical.
3. **Edit KiCad source.** Keep symbols, footprints, nets, board geometry, and
   model transforms in their owning KiCad files. Use project-relative paths or
   KiCad variables such as `${KIPRJMOD}` for local libraries and 3D models.
4. **Validate the schematic.** Run ERC when the schematic exists. Treat
   violations as failures unless the project explicitly documents an accepted
   exception.
5. **Validate the PCB.** Run DRC and check unconnected items after board changes.
   Do not infer DRC success from a successful file export.
6. **Export requested outputs.** Generate fabrication data only when requested.
   Export STEP when board geometry, component envelopes, or a downstream
   mechanical check needs it; do not regenerate STEP for an unrelated text-only
   edit.
7. **Perform the mechanical handoff when triggered.** Load
   `references/mechanical-handoff.md`, export the populated board, and hand that
   artifact to the requested assembly/viewer workflow. Keep KiCad responsible
   for ERC, DRC, placement, and the exported board.
8. **Report evidence and boundaries.** Name the commands, KiCad version,
   reports, output files, warnings, and the claims they actually support.

## Baseline validation commands

Choose project-local or temporary report paths that will not overwrite retained
evidence unexpectedly:

```bash
kicad-cli sch erc \
  --exit-code-violations \
  --format json \
  --output /tmp/kicad-erc.json \
  path/to/project.kicad_sch

kicad-cli pcb drc \
  --exit-code-violations \
  --format json \
  --output /tmp/kicad-drc.json \
  path/to/project.kicad_pcb
```

Read the JSON reports, not only the exit status. If the project intentionally
has no schematic or no PCB, state that boundary rather than fabricating a
validation result.

## Confidence boundary

- A clean ERC report supports only the electrical-rule scope KiCad evaluated.
- A clean DRC report supports only the PCB-rule and connectivity scope KiCad
  evaluated.
- A successful STEP export proves that KiCad produced a mechanical artifact; it
  does not prove enclosure clearance or assembly fit.
- A downstream assembly-interference pass supports only the tested component
  pairs and only when the checker completed without an inconclusive result.
- None of these alone proves functional firmware, signal integrity, thermal
  performance, manufacturability, safety, or regulatory compliance.

## Non-negotiables

- Keep KiCad files as the electronics source of truth; never repair a generated
  STEP file instead of the board or footprint that produced it.
- Do not commit machine-specific absolute library or 3D-model paths.
- Do not hide missing symbols, footprints, 3D models, ERC/DRC violations, or
  downstream incomplete results.
- Do not claim a mechanically populated export when the required footprint 3D
  models are absent.
- Keep a downstream viewer/checker optional. Ordinary KiCad work must remain
  useful without Burr or any particular mechanical tool installed.

## Progressive references

Load only when mechanically relevant KiCad geometry must leave KiCad:

- `references/mechanical-handoff.md` — component envelopes, populated STEP
  export, subsystem grouping, and downstream assembly checks.

Final responses should include the source project paths, KiCad version,
validation reports and outcomes, requested exports, downstream evidence when
applicable, assumptions, and remaining caveats.
