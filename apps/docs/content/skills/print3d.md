---
title: print3d
description: The print3d skill slices a part into printer-ready G-code with OrcaSlicer and hands it to your printer's app; it never starts a print.
---

The `print3d` skill slices a part into printer-ready G-code with OrcaSlicer and hands the result to your printer's app. For a Bambu Lab printer that is Bambu Connect or Bambu Studio, where you press Print yourself. Whether a part will print well at all is a separate question, answered by the printing check in the `cad` skill's [manufacturing checks](/docs/cad#manufacturing-checks), for example `cad model dfm "$ID" --process printing --technology fdm`.

## How it works

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

## What it needs

- OrcaSlicer. On macOS, `brew install --cask orcaslicer`. On Windows and Linux, a release from the [OrcaSlicer releases page](https://github.com/OrcaSlicer/OrcaSlicer/releases).
- Python 3 for the presets helper, which has no dependencies.
- For a Bambu Lab printer, Bambu Connect (Windows 10 or later, macOS 13 or later) signed in to your Bambu Lab account, with the printer on that account or in LAN mode. On Linux, where Bambu Connect is still in development, Bambu Studio.

## Limits

- Your agent never starts, pauses or cancels a print, never reads printer status and never asks for an access code. Bambu Lab's firmware takes those from other software only through Bambu Connect or Developer Mode, which is LAN-only and disconnects the printer from Bambu Cloud.
- It cannot see your printer. Before you press Print, check the printer, plate type, nozzle, filament and AMS mapping, a clear build plate, and that someone is nearby for the first layer.
- Bambu Connect accepts a plain `.gcode` only if it was sliced with that printer's Bambu profile. If it refuses one, slice in Bambu Studio.
- A printer with no OrcaSlicer profile needs you to choose settings in the app.

## Ask for it

- "Check whether the stand will print in PETG on an FDM printer, then slice it for my Prusa MK4S."
- "Slice `bracket.stl` for my Bambu Lab printer in PLA and open it in Bambu Connect."

## The skill

The skill is [`print3d`](repo:skills/print3d/SKILL.md). Its references:

- [The presets helper](repo:skills/print3d/scripts/orca_presets.py)
- [The printing manufacturing check](repo:skills/cad/references/manufacturing-printing.md)

Related pages: [manufacturing checks](/docs/cad#manufacturing-checks).
