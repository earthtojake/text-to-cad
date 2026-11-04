---
name: print3d
description: Prints a part - slices an `.stl`, `.3mf` or `.obj` into printer-ready G-code with OrcaSlicer, headless or in the app, with built-in profiles for most FDM printers (Prusa, Bambu Lab, Creality, Voron), and sends it to a Bambu Lab printer through Bambu Connect or Bambu Studio. Use when the person wants a model sliced or printed. Never starts a print; whether a part will print is the cad skill's check.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# 3D printing

Get a part printed: slice it for the person's printer and hand the print to the printer's app. The
part itself is designed with the cad skill, and whether it will print (walls, overhangs, supports,
orientation) is the cad skill's manufacturing check: run it first when the person asks. This skill
never starts a print.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| **Slice it to G-code** | `python scripts/orca_presets.py --list machine --match "<printer>"` | [Slice with OrcaSlicer](#slice-with-orcaslicer) |
| **Print on a Bambu Lab printer** | The sliced `.gcode.3mf` | [Print on a Bambu Lab printer](#print-on-a-bambu-lab-printer) |
| **Will this print?** | The cad skill's printing check ($cad) | Its manufacturing references |

## Slice with OrcaSlicer

Slice with OrcaSlicer, headless (below) or by opening the model in the
OrcaSlicer app for the person. The agent never contacts a printer: for a Bambu
Lab printer, the result is sent through Bambu Connect ([below](#print-on-a-bambu-lab-printer));
for any other printer, give the person the `.gcode`.

### Install OrcaSlicer

- macOS: `brew install --cask orcaslicer`. The command line is
  `/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer`.
- Windows and Linux: install a release from
  https://github.com/OrcaSlicer/OrcaSlicer/releases. The command is
  `orca-slicer`; on Linux, run it from the AppImage or Flatpak.

Below, `<orca>` is that command.

### Slice headless

OrcaSlicer's command line (https://www.orcaslicer.com/wiki/cli/cli_mode) needs
complete presets: it doesn't fill in a preset's parent settings, and it slices
only with a process whose compatible printers name the printer.
`scripts/orca_presets.py` (Python 3, no dependencies) writes them from
OrcaSlicer's presets, searching the person's own first, then OrcaSlicer's
built-in profiles.

1. Find the person's printer, process and filament presets. Prefer the presets
   they print with; never invent one, since a wrong bed size or
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
     --outputdir /absolute/path/to/out --export-3mf model.gcode.3mf
   ```

   This writes `plate_1.gcode`, the plain G-code, and `model.gcode.3mf`, the
   sliced 3MF, into that folder. The command line reads `.stl`,
   `.3mf`, `.obj` and `.amf`; export STEP to STL or 3MF first (for a text-to-cad model, `cad model export <id> part.3mf`, or `cad step export part.step part.3mf`).
   Override one setting with `--<setting>=<value>`, using the setting's key
   with hyphens for underscores, such as `--layer-height=0.16`.

### Open in OrcaSlicer

When the person would rather pick presets and slice themselves, or no preset can
be found, open the model in the app: `open -a OrcaSlicer model.stl` on macOS,
`Start-Process model.stl` on Windows when OrcaSlicer opens that file type, or
`orca-slicer model.stl` on Linux. The app also reads STEP.

## Print on a Bambu Lab printer

Bambu Lab printers take print jobs from other software only through Bambu
Connect, Bambu Lab's desktop app for third-party tools
(https://wiki.bambulab.com/en/software/third-party-integration). Open a sliced
file in Bambu Connect, or an unsliced model in Bambu Studio; the person
picks the printer and starts the print there. The agent never controls a
printer and never asks for access codes.

Bambu Connect runs on Windows 10 or later and macOS 13 or later, signed in to the
person's Bambu Lab account, with the printer on that account or reachable in LAN
mode (https://wiki.bambulab.com/en/software/bambu-connect). On Linux, where Bambu
Connect is still in development, use Bambu Studio.

| What the person has | Handoff |
| --- | --- |
| A sliced `.gcode.3mf`, from OrcaSlicer's command line or Bambu Studio's or OrcaSlicer's "Export plate sliced file" | Open it in Bambu Connect |
| A plain `.gcode` sliced with this printer's Bambu profile | Open it in Bambu Connect; if Bambu Connect refuses it, slice the model in Bambu Studio instead |
| A model with no slice: `.3mf`, `.stl` or `.step` (from a text-to-cad model: `cad model export <id> part.3mf`) | Open it in Bambu Studio, which slices it and sends it to the printer itself |

### Open a file in Bambu Connect

Bambu Connect imports a file from a `bambu-connect://import-file` link with
three parameters: `path`, the file's absolute path, and `name`, the name to
show, each percent-encoded the way JavaScript's `encodeURIComponent` does it
(Python: `urllib.parse.quote(value, safe="")`); and `version=1.0.0`. For
`/Users/me/prints/bracket.gcode.3mf`:

```text
bambu-connect://import-file?path=%2FUsers%2Fme%2Fprints%2Fbracket.gcode.3mf&name=bracket&version=1.0.0
```

Open the link with `open "<link>"` on macOS, or `Start-Process "<link>"` in
PowerShell on Windows. Bambu Connect comes forward with the file loaded.

### Open a model in Bambu Studio

On macOS run `open -a BambuStudio <file>` (some installs name the app
`Bambu Studio`). On Windows open the file from Bambu Studio's File menu, or run
`Start-Process <file>` when Bambu Studio is the file's default app. On Linux run
`bambu-studio <file>`, or open it from the AppImage or Flatpak.

### Finish in the app

Before the person presses Print, tell them what to check: the printer, plate
type, nozzle, filament and AMS mapping, a clear build plate, and someone nearby
for the first layer. Never report a print as started: the agent can't see the
printer, and the app shows the job and its progress.

Out of scope: starting, pausing or cancelling prints without the person, and
reading printer status. Bambu Lab's firmware takes those from other software
only through Bambu Connect, or in Developer Mode, which is LAN-only and
disconnects the printer from Bambu Cloud.

## Any other printer

The person prints the `.gcode` from their printer's app, its web interface
(PrusaLink, OctoPrint, Mainsail, Fluidd) or an SD card.

## Check each change

Before anyone prints a slice:

- `<orca> model.stl --info` prints the model's size; it has to fit the bed.
- Check the slice's settings, which OrcaSlicer writes at the end of the G-code:

  ```bash
  grep -E '^; (printer_model|nozzle_diameter|filament_type|nozzle_temperature|hot_plate_temp|bed_temperature) =|printing time' out/plate_1.gcode
  ```

  Confirm they match the person's printer and material before anyone prints it.
