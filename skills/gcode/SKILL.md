---
name: gcode
description: Slice 3D models into printer-ready G-code with OrcaSlicer, the open-source slicer with built-in profiles for most FDM printers (Prusa, Bambu Lab, Creality, Voron and more). Use when the user wants an `.stl`, `.3mf` or `.obj` model sliced for their printer, as a sliced `.gcode.3mf` or plain `.gcode`, headless with OrcaSlicer's command line or by opening the model in OrcaSlicer. Never contacts a printer.
---

# G-code

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Slice with OrcaSlicer, headless (below) or by opening the model in the
OrcaSlicer app for the user. The agent never contacts a printer: for a Bambu
Lab printer, hand the result to `$bambu-labs`; for any other printer, give the
user the `.gcode`.

## Install OrcaSlicer

- macOS: `brew install --cask orcaslicer`. The command line is
  `/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer`.
- Windows and Linux: install a release from
  https://github.com/OrcaSlicer/OrcaSlicer/releases. The command is
  `orca-slicer`; on Linux, run it from the AppImage or Flatpak.

Below, `<orca>` is that command.

## Slice headless

OrcaSlicer's command line (https://www.orcaslicer.com/wiki/cli/cli_mode) needs
complete presets: it doesn't fill in a preset's parent settings, and it slices
only with a process whose compatible printers name the printer.
`scripts/orca_presets.py` (Python 3, no dependencies) writes them from
OrcaSlicer's presets, searching the user's own first, then OrcaSlicer's
built-in profiles.

1. Find the user's printer, process and filament presets. Prefer the presets
   the user prints with; never invent one, since a wrong bed size or
   temperature can damage the printer.

   ```bash
   python scripts/orca_presets.py --list machine --match "MK4S"
   python scripts/orca_presets.py --list process --match "@MK4S 0.4"
   python scripts/orca_presets.py --list filament --match "PLA @MK4S"
   ```

2. Write the complete presets:

   ```bash
   python scripts/orca_presets.py --printer "Prusa MK4S 0.4 nozzle" \
     --process "0.20mm SPEED @MK4S 0.4" --filament "Prusa Generic PLA @MK4S" \
     --out presets
   ```

3. Slice. Give `--outputdir` an absolute path:

   ```bash
   <orca> model.stl \
     --load-settings "presets/process.json;presets/printer.json" \
     --load-filaments presets/filament-1.json \
     --arrange 1 --slice 0 \
     --outputdir "$PWD/out" --export-3mf model.gcode.3mf
   ```

   This writes `out/plate_1.gcode`, the plain G-code, and
   `out/model.gcode.3mf`, the sliced 3MF. The command line reads `.stl`,
   `.3mf`, `.obj` and `.amf`; export STEP to STL or 3MF with `$cad` first.
   Override one setting with `--<setting>=<value>`, using the setting's key
   with hyphens for underscores, such as `--layer-height=0.16`.

## Open in OrcaSlicer

When the user would rather pick presets and slice themselves, or no preset can
be found, open the model in the app: `open -a OrcaSlicer model.stl` on macOS,
`Start-Process model.stl` on Windows when OrcaSlicer opens that file type, or
`orca-slicer model.stl` on Linux. The app also reads STEP.

## Check before printing

- `<orca> model.stl --info` prints the model's size; it has to fit the bed.
- Check the slice's settings, which OrcaSlicer writes at the end of the G-code:

  ```bash
  grep -E '^; (printer_model|nozzle_diameter|filament_type|nozzle_temperature|hot_plate_temp|bed_temperature) =|printing time' out/plate_1.gcode
  ```

  Confirm they match the user's printer and material before anyone prints it.

## Hand off

- A Bambu Lab printer: `$bambu-labs`, with the `.gcode.3mf`.
- Any other printer: the user prints the `.gcode` from their printer's app, its
  web interface (PrusaLink, OctoPrint, Mainsail, Fluidd) or an SD card.
