---
name: print3d
description: Gets a part 3D printed - slices an .stl, .3mf or .obj into G-code with OrcaSlicer and, for a Bambu Lab printer, hands it to Bambu's own app. Use when the person wants a model sliced, printed or sent to their printer (Prusa, Bambu Lab, Creality, Voron and most FDM printers). Whether a part will print well is the cad skill's check.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# 3D printing

Get a part printed: slice it for the person's printer and hand the result to the printer's own app.
Designing the part, and checking whether it will print (walls, overhangs, supports, orientation), is
the cad skill's.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| Slice to G-code | OrcaSlicer's command line, with the person's presets | [Slice with OrcaSlicer](#slice-with-orcaslicer) |
| Print on a Bambu Lab printer | The sliced `.gcode.3mf`, opened in Bambu Connect | [Bambu Lab printers](#bambu-lab-printers) |
| Print on any other printer | The `.gcode`, given to the person | [Any other printer](#any-other-printer) |
| Will this print? | The cad skill's printing check | Its manufacturing references |

## Setup

Written for `cad==0.11.18`. Before first use in a chat, run `cad --version`. If `cad` is missing or older than
0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.

If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
https://github.com/earthtojake/text-to-cad
A project written for an earlier version may need changes; the migration guides say what:
https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations

`cad` is needed only to write the mesh a slicer takes from a text-to-cad model or a STEP:

```bash
cad model export "$ID" part.3mf
cad step export part.step part.3mf
```

OrcaSlicer is the person's own install: `brew install --cask orcaslicer` on macOS (its command line is
`/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer`), or a release from
https://github.com/OrcaSlicer/OrcaSlicer/releases on Windows and Linux (`orca-slicer`; on Linux, the
AppImage or Flatpak). Below, `<orca>` is that command, and `<orca> --help` is its interface
(https://www.orcaslicer.com/wiki/cli/cli_mode).

## Slice with OrcaSlicer

The command line slices with the settings it is given: a printer, a process and a filament preset.
Two things carry them:

- **A project file** the person saved from the app (File > Save Project, a `.3mf`): it holds its
  models and every setting, and slices as it is. This is the sure route.
- **Preset files**, passed with `--load-settings "process.json;printer.json"` and
  `--load-filaments "a.json;b.json"` (one filament per material, in order).

A preset as OrcaSlicer stores it holds only its differences from the preset its `inherits` names, and
an export from the app (File > Export > Export Preset Bundle) is an archive of those same files. The
person's own are under `user/` in the configuration folder: `~/Library/Application Support/OrcaSlicer`,
`~/.config/OrcaSlicer` (a Flatpak's `~/.var/app/com.orcaslicer.OrcaSlicer/config/OrcaSlicer`) or
`%APPDATA%\OrcaSlicer`. The built-in ones they inherit from are in `system/` beside them and in the
app's `resources/profiles`: JSON files before OrcaSlicer 2.5, binary caches (`.opc`) from it.

Whether the command line fills in the parents depends on its version, so check what it sliced with:
the settings are written into the G-code (`grep -m1 "nozzle_temperature =" plate_1.gcode`, and the
same for the bed size and layer height). Where they are OrcaSlicer's defaults and not the preset's,
this version wants complete presets: merge the chain, parents first, the child last (skip nothing: a
parent may inherit in turn; of two presets with one name, take the one whose `compatible_printers`
lists the printer), and put the printer's name in the process's `compatible_printers`. From 2.5 the
parents are in the caches and cannot be read: use a project file there.

Use the presets the person prints with, and never invent one: a wrong bed size or temperature can
damage a printer. Where there are none to slice headless with, open the model in the app instead.

```bash
<orca> model.stl \
  --load-settings "presets/process.json;presets/printer.json" \
  --load-filaments presets/filament.json \
  --arrange 1 --slice 0 \
  --outputdir /absolute/path/to/out --export-3mf model.gcode.3mf
```

This writes `plate_1.gcode` and the sliced `model.gcode.3mf` into the folder; give `--outputdir` an
absolute path. It reads `.stl`, `.3mf`, `.obj` and `.amf`. A setting is overridden with
`--<setting>=<value>`, its key written with hyphens (`--layer-height=0.16`).

To let the person pick presets and slice themselves, open the model in the app: `open -a OrcaSlicer
model.stl` on macOS, `Start-Process model.stl` on Windows where OrcaSlicer opens that file type,
`orca-slicer model.stl` on Linux. The app also reads STEP.

## Bambu Lab printers

A Bambu Lab printer takes jobs from other software only through Bambu Connect, Bambu Lab's desktop app
for third-party tools (https://wiki.bambulab.com/en/software/bambu-connect; Windows 10 and macOS 13
or later, signed in to the person's account). The person picks the printer and starts the print there.
Never ask for access codes.

| What the person has | Hand it off by |
| --- | --- |
| A sliced `.gcode.3mf` | Opening it in Bambu Connect |
| A plain `.gcode` sliced with this printer's Bambu profile | Opening it in Bambu Connect; if refused, slice the model in Bambu Studio |
| An unsliced `.3mf`, `.stl` or `.step` | Opening it in Bambu Studio, which slices and sends it. On Linux, where Bambu Connect is still in development, this is the route |

Bambu Connect imports a file from a `bambu-connect://import-file` link with three parameters: `path`
(the file's absolute path) and `name` (the name to show), each percent-encoded as JavaScript's
`encodeURIComponent` does (Python: `urllib.parse.quote(value, safe="")`), and `version=1.0.0`:

```text
bambu-connect://import-file?path=%2FUsers%2Fme%2Fprints%2Fbracket.gcode.3mf&name=bracket&version=1.0.0
```

Open the link with `open "<link>"` on macOS or `Start-Process "<link>"` in PowerShell. Bambu Studio
opens a model with `open -a BambuStudio <file>` on macOS (some installs name it `Bambu Studio`), from
its File menu on Windows, or `bambu-studio <file>` on Linux.

Before the person presses Print, tell them what to check: the printer, plate type, nozzle, filament
and AMS mapping, a clear build plate, and someone nearby for the first layer. This hand-off shows the
agent nothing of the printer, so do not report a print as started.

## Any other printer

The person prints the `.gcode` from their printer's app, its web interface (PrusaLink, OctoPrint,
Mainsail, Fluidd) or an SD card.

## Check each change

Before anyone prints a slice:

- `<orca> model.stl --info` prints the model's size, which has to fit the bed.
- OrcaSlicer writes the slice's settings at the end of the G-code. Confirm they match the person's
  printer and material:

  ```bash
  grep -E '^; (printer_model|nozzle_diameter|filament_type|nozzle_temperature|hot_plate_temp|bed_temperature) =|printing time' out/plate_1.gcode
  ```
