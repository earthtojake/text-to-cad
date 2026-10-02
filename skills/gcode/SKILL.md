---
name: gcode
description: Slice 3D models into printer-ready G-code with OrcaSlicer, the open-source slicer with built-in profiles for most FDM printers (Prusa, Bambu Lab, Creality, Voron and more). Use when the user wants an `.stl`, `.3mf`, `.step` or `.obj` model sliced for their printer, as a sliced `.gcode.3mf` or plain `.gcode`. The agent runs OrcaSlicer's command line with the user's own printer, process and filament presets and never contacts a printer.
---

# G-code

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Slice with OrcaSlicer's command line
(https://www.orcaslicer.com/wiki/cli/cli_mode), using the user's own OrcaSlicer
presets. The agent never contacts a printer: for a Bambu Lab printer, hand the
result to `$bambu-labs`; for any other printer, give the user the `.gcode`.

## Install OrcaSlicer

- macOS: `brew install --cask orcaslicer`. The command line is
  `/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer`.
- Windows and Linux: install a release from
  https://github.com/OrcaSlicer/OrcaSlicer/releases. The command is
  `orca-slicer`; on Linux, run it from the AppImage or Flatpak.

Below, `<orca>` is that command; `<orca> --help` confirms it runs.

## Get the user's presets

A slice needs three kinds of OrcaSlicer preset, each a JSON file: the printer,
the process (layer height, walls, infill), and one filament per material. Ask
the user to set their printer up in OrcaSlicer, which has built-in profiles for
most printers, then export the presets with OrcaSlicer's Export Preset Bundle:
Printer presets, Process presets and Filament presets each save a `.zip` of JSON
files (https://www.orcaslicer.com/wiki/general_settings/import_export). Never
invent a preset: a wrong bed size or temperature can damage the printer.

## Slice

```bash
<orca> model.stl \
  --load-settings "process.json;printer.json" \
  --load-filaments filament.json \
  --arrange 1 --slice 0 \
  --outputdir out --export-3mf model.gcode.3mf
```

`--slice 0` slices every plate, and `--export-3mf` writes the sliced
`out/model.gcode.3mf`. Override one setting with `--<setting>=<value>`, using
the setting's key with hyphens for underscores, such as `--layer-height=0.16`.
If the slice fails, OrcaSlicer says why; report that to the user.

For plain `.gcode`, take a plate's G-code out of the sliced 3MF, which is a zip:

```bash
unzip -p out/model.gcode.3mf Metadata/plate_1.gcode > out/model.gcode
```

## Check before printing

- `<orca> model.stl --info` prints the model's size; it has to fit the bed.
- The G-code starts with comments naming the printer, nozzle, filament,
  temperatures and print time. Confirm they match the user's printer and
  material before anyone prints it.

## Hand off

- A Bambu Lab printer: `$bambu-labs`, with the `.gcode.3mf`.
- Any other printer: the user prints the `.gcode` from their printer's app, its
  web interface (PrusaLink, OctoPrint, Mainsail, Fluidd) or an SD card.
