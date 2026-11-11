---
title: 3D printing
description: Slice a part with OrcaSlicer and hand it to your printer, with Bambu Connect or Bambu Studio for Bambu Lab printers. Your agent never starts a print.
---

Your agent can take a part from text-to-cad, slice it into printer-ready G-code with OrcaSlicer, and hand the result to your printer's app. For Bambu Lab printers that hand-off is Bambu Connect or Bambu Studio. You end up with a sliced file and a print waiting in the app, where you press Print yourself.

Whether a part will print at all (walls, overhangs, supports, orientation) is a separate question, answered by the 3D printing manufacturing check. See [manufacturing checks](/docs/guides/manufacturing-checks). It is worth running before you slice.

## What to ask

- "Check whether the stand will print in PETG on an FDM printer, then slice it for my Prusa MK4S."
- "Slice `bracket.stl` for my Bambu Lab printer in PLA and open it in Bambu Connect."
- "Export the case as a 3MF and open it in Bambu Studio so I can pick my own settings."
- "Slice the lid at 0.16 mm layer height and tell me the print time and filament settings it used."
- "Open the model in OrcaSlicer, I will choose the presets myself."

## What your agent does

1. Optionally runs the printing check on the part first, for example `cad model dfm "$ID" --process printing --technology fdm`, and fixes what it reports.
2. Exports a mesh the slicer reads. OrcaSlicer's command line reads `.stl`, `.3mf`, `.obj` and `.amf`, so a STEP is exported first:

   ```bash
   cad model export "$ID" part.3mf
   cad step export part.step part.3mf
   ```

3. Finds your printer's presets. The skill's helper, `scripts/orca_presets.py`, lists presets from your own OrcaSlicer folders first, then from OrcaSlicer's built-in profiles. Your agent prefers the presets you print with and never invents one, because a wrong bed size or temperature can damage a printer.

   ```bash
   python scripts/orca_presets.py --list machine --match "MK4S"
   python scripts/orca_presets.py --list process --match "@MK4S 0.4"
   python scripts/orca_presets.py --list filament --match "PLA @MK4S"
   ```

4. Writes complete presets, because OrcaSlicer's command line does not fill in a preset's parent settings:

   ```bash
   python scripts/orca_presets.py --printer "Prusa MK4S 0.4 nozzle" \
     --process "0.20mm SPEED @MK4S 0.4" --filament "Prusa Generic PLA @MK4S" \
     --out presets
   ```

5. Slices. `<orca>` is the OrcaSlicer command, and `--outputdir` takes an absolute path:

   ```bash
   <orca> model.stl \
     --load-settings "presets/process.json;presets/printer.json" \
     --load-filaments presets/filament-1.json \
     --arrange 1 --slice 0 \
     --outputdir /absolute/path/to/out --export-3mf model.gcode.3mf
   ```

   One setting can be overridden with `--<setting>=<value>`, such as `--layer-height=0.16`.
6. Checks the slice before anyone prints it. `<orca> model.stl --info` prints the model's size, which must fit the bed, and the settings OrcaSlicer wrote at the end of the G-code are compared with your printer and material.
7. Hands off. For a Bambu Lab printer, a sliced `.gcode.3mf` opens in Bambu Connect through a `bambu-connect://import-file` link, and an unsliced model opens in Bambu Studio, which slices it and sends it. For any other printer, your agent gives you the `.gcode` to send from your printer's app, its web interface (PrusaLink, OctoPrint, Mainsail, Fluidd) or an SD card.

If you would rather pick presets yourself, or no preset can be found, your agent opens the model in the OrcaSlicer app instead.

## What you need

- OrcaSlicer. On macOS, `brew install --cask orcaslicer`. On Windows and Linux, a release from the [OrcaSlicer releases page](https://github.com/OrcaSlicer/OrcaSlicer/releases).
- Python 3 for the presets helper, which has no dependencies.
- For a Bambu Lab printer, Bambu Connect (Windows 10 or later, macOS 13 or later) signed in to your Bambu Lab account, with the printer on that account or in LAN mode. On Linux, where Bambu Connect is still in development, use Bambu Studio.

## What you get

- Complete printer, process and filament presets in the `presets` folder.
- `plate_1.gcode`, the plain G-code, and `model.gcode.3mf`, the sliced 3MF, in the folder you named.
- On a Bambu Lab printer, Bambu Connect or Bambu Studio in front of you with the file loaded. You choose the printer and start the print there.

## Limits

- Your agent never starts, pauses or cancels a print, never reads printer status and never asks for an access code. Bambu Lab's firmware takes those from other software only through Bambu Connect or Developer Mode, which is LAN-only and disconnects the printer from Bambu Cloud.
- It cannot see your printer, so it never reports a print as started. Before you press Print, check the printer, plate type, nozzle, filament and AMS mapping, a clear build plate, and that someone is nearby for the first layer.
- A plain `.gcode` is accepted by Bambu Connect only if it was sliced with that printer's Bambu profile. If Bambu Connect refuses it, slice in Bambu Studio.
- Presets come from OrcaSlicer's profiles. A printer with no profile needs you to choose settings in the app.
- Slicing does not show the part will print well. That is the printing check's job.

## Go deeper

- [The print3d skill](repo:skills/print3d/SKILL.md) and [the presets helper](repo:skills/print3d/scripts/orca_presets.py).
- [The printing manufacturing check](repo:skills/cad/references/manufacturing-printing.md) in detail, and its guide, [manufacturing checks](/docs/guides/manufacturing-checks).
- Document types [`stl`](/docs/document-types/stl) and [`threemf`](/docs/document-types/threemf), which a part is exported as for slicing.
- [Parts and assemblies](/docs/guides/parts-and-assemblies), for designing the part.
