---
title: Fabrication services
description: The sendcutsend skill checks DXF and STEP files before you upload them, and the print3d skill slices 3D prints and hands them to your printer.
---

Two skills take a finished part to whoever makes it: a cutting service or your own printer. `sendcutsend` checks a DXF or STEP file against SendCutSend's published guidelines before you upload it. `print3d` slices a part with OrcaSlicer and hands it to your printer's app. The SendCutSend check does not talk to your account, and the print skill never starts a print: those steps stay with you.

## SendCutSend

SendCutSend is an online service that laser cuts, routes and bends parts from files you upload. The `sendcutsend` skill is a pre-upload check of a DXF or STEP file against the guidelines SendCutSend publishes, and it gives you a report. It is not an official SendCutSend integration, it does not talk to your SendCutSend account, and SendCutSend's own upload and quote have the last word.

### How it works

The check starts from the order context: file type, process (laser cutting, CNC routing, bending, tapping, countersinking, hardware insertion, finishing), material or SKU, thickness, quantity, finish. Without it, your agent lists candidate materials and thicknesses from SendCutSend's data and asks you to choose before it gives a verdict.

SendCutSend's three published source files are fetched fresh each time: the ordering guide (workflow and file format rules), the catalog JSON (materials, thicknesses, size limits and services) and the specs JSON (engineering values such as hole, bridge and bend figures, joined to the catalog by exact SKU). They are treated as data that can change or have gaps, not as a stable API.

The measurements come from the actual upload file, not the script that made it. A model's upload is exported first with `cad model export <id> part.step` or `part.dxf`. `cad step inspect` gives a STEP's bodies, bounds and volume, or reads one face, such as a bend's cylinder and its radius. text-to-cad's own sheet-metal check runs on the file with the SKU's figures where the specs list them:

```bash
cad step inspect part.step 'face 9'
cad step dfm part.step --process sheet --material <material> --thickness <mm> --json
cad dxf dfm part.dxf --material <material> --thickness <mm> --json
```

The `dfm` check is text-to-cad's, not SendCutSend's ([manufacturing checks](/docs/skills/manufacturing-checks)); its measurements are compared with the cited requirements. For a DXF, the report's checks include units (`$INSUNITS` must be `1` for inches or `4` for mm, otherwise it is a scale error and nothing is rescaled), closed cut profiles, duplicate or overlapping geometry, unsupported text, dimensions or images, and the flange length on both sides of each bend line. For a STEP, they include readability, a solid body, units, bounding box, thickness and, where bending is in scope, bend radii against the SKU's tooling radius.

The report gives the file, the assumed order context, the source files and the date they were fetched, the measured facts, and a findings table. Each row has a status (pass, fail or need more info), the evidence, and a rule source that links to the document or JSON field path, or says "Direct file inspection". The verdict is "Ready to upload for this assumed context", "Needs edits before upload" or "Insufficient context to validate".

### Limits

- It states only limits the sources give. A missing, unparsable or `N/A` field makes a row "need more info", not a pass or a fail.
- It cannot say whether SendCutSend's upload will accept the file or what it will quote.
- A verdict is only as good as the order context. A different material, thickness or service changes the limits.
- It needs network access to fetch the three source files. If they cannot be fetched, the report says so and gives no ready verdict for the checks that depend on them.

## 3D printing

The `print3d` skill slices a part into printer-ready G-code with OrcaSlicer and hands the result to your printer's app. For a Bambu Lab printer that is Bambu Connect or Bambu Studio, where you press Print yourself. Whether a part will print well at all is a separate question, answered by the printing check in [manufacturing checks](/docs/skills/manufacturing-checks), for example `cad model dfm "$ID" --process printing --technology fdm`.

### How it works

OrcaSlicer's command line reads `.stl`, `.3mf`, `.obj` and `.amf`, so a model or a STEP is exported to a mesh first:

```bash
cad model export "$ID" part.3mf
cad step export part.step part.3mf
```

The skill's helper, `scripts/orca_presets.py`, finds your printer's presets: from your own OrcaSlicer folders first, then from OrcaSlicer's built-in profiles. Your agent prefers the presets you print with and never invents one, because a wrong bed size or temperature can damage a printer. The helper also writes complete presets, since OrcaSlicer's command line does not fill in a preset's parent settings:

```bash
python scripts/orca_presets.py --list machine --match "MK4S"
python scripts/orca_presets.py --printer "Prusa MK4S 0.4 nozzle" \
  --process "0.20mm SPEED @MK4S 0.4" --filament "Prusa Generic PLA @MK4S" \
  --out presets
```

OrcaSlicer then slices with those presets (`<orca>` is the OrcaSlicer command), and writes `plate_1.gcode` and `model.gcode.3mf`. One setting can be overridden with `--<setting>=<value>`, such as `--layer-height=0.16`:

```bash
<orca> model.stl \
  --load-settings "presets/process.json;presets/printer.json" \
  --load-filaments presets/filament-1.json \
  --arrange 1 --slice 0 \
  --outputdir /absolute/path/to/out --export-3mf model.gcode.3mf
```

Before the hand-off, `<orca> model.stl --info` gives the model's size, which must fit the bed, and the settings at the end of the G-code are compared with your printer and material. For a Bambu Lab printer, a sliced `.gcode.3mf` opens in Bambu Connect through a `bambu-connect://import-file` link, and an unsliced model opens in Bambu Studio. For any other printer, you get the `.gcode` to send from your printer's app, its web interface (PrusaLink, OctoPrint, Mainsail, Fluidd) or an SD card. If you would rather pick presets yourself, or none can be found, the model opens in the OrcaSlicer app instead.

### What it needs

- OrcaSlicer. On macOS, `brew install --cask orcaslicer`. On Windows and Linux, a release from the [OrcaSlicer releases page](https://github.com/OrcaSlicer/OrcaSlicer/releases).
- Python 3 for the presets helper, which has no dependencies.
- For a Bambu Lab printer, Bambu Connect (Windows 10 or later, macOS 13 or later) signed in to your Bambu Lab account, with the printer on that account or in LAN mode. On Linux, where Bambu Connect is still in development, Bambu Studio.

### Limits

- Your agent never starts, pauses or cancels a print, never reads printer status and never asks for an access code. Bambu Lab's firmware takes those from other software only through Bambu Connect or Developer Mode, which is LAN-only and disconnects the printer from Bambu Cloud.
- It cannot see your printer. Before you press Print, check the printer, plate type, nozzle, filament and AMS mapping, a clear build plate, and that someone is nearby for the first layer.
- Bambu Connect accepts a plain `.gcode` only if it was sliced with that printer's Bambu profile. If it refuses one, slice in Bambu Studio.
- A printer with no OrcaSlicer profile needs you to choose settings in the app.

## Ask for it

- "Check `bracket.dxf` against SendCutSend's guidelines for laser cutting. The material is 5052 aluminium, 0.063 in."
- "Is `housing.step` ready to upload to SendCutSend for CNC routing? Tell me what to change."
- "Check whether the stand will print in PETG on an FDM printer, then slice it for my Prusa MK4S."
- "Slice `bracket.stl` for my Bambu Lab printer in PLA and open it in Bambu Connect."

## The skills

The skills are [`sendcutsend`](repo:skills/sendcutsend/SKILL.md) and [`print3d`](repo:skills/print3d/SKILL.md). Their references:

- [SendCutSend's official sources](repo:skills/sendcutsend/references/official-sources.md) and [the report template](repo:skills/sendcutsend/references/report-template.md)
- [The presets helper](repo:skills/print3d/scripts/orca_presets.py)
- [The printing manufacturing check](repo:skills/cad/references/manufacturing-printing.md)

Related pages: [manufacturing checks](/docs/skills/manufacturing-checks), [DXF profiles and flat patterns](/docs/skills/parts-and-assemblies#dxf-profiles-and-flat-patterns) for making a cut file, [engineering drawings](/docs/skills/engineering-drawings), and the document types [`dxf`](/docs/document-types/dxf), [`step`](/docs/document-types/step), [`stl`](/docs/document-types/stl) and [`threemf`](/docs/document-types/threemf).
