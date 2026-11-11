---
title: KiCad
description: The open source electronics design suite, whose command line and API text-to-cad uses to check, export and edit boards and schematics.
---

[KiCad](https://www.kicad.org) is an open source suite for designing schematics and printed circuit boards. Its editors, its libraries and its command line, `kicad-cli`, are all KiCad's.

## What it does, and what text-to-cad adds

KiCad already runs design rule checks, electrical rules checks and fabrication exports, and it has an API that changes a file in place. text-to-cad leaves all of that to KiCad, and `cad run kicad-cli ...` runs any other subcommand as KiCad spells it.

What it adds is a typed command for the common ones: `cad kicad_pcb drc`, `cad kicad_sch erc` and the exports answer in one result shape, leave the project as they found it, and name each finding. It also adds the edit, a `with` block that opens a saved [board](/docs/document-types/kicad_pcb) or [schematic](/docs/document-types/kicad_sch) through KiCad's API and saves it only if you changed it.

## How it reaches your computer

KiCad runs as a separate program. The `cad` command installs it on first need, about 100 MB to download, as `cad[kicad]`, which brings `kicad-cli`. A script that edits a board and is run with `cad run` gets the extra from its imports.

text-to-cad never runs your own KiCad install. Checks and edits run in private KiCad settings folders, so your preferences and library tables are neither read nor written. To use another `kicad-cli`, of KiCad 9 or newer, set `CAD_KICAD_CLI` to it.

## Related

[Circuit boards](/docs/skills/circuit-boards) covers the whole flow. The [pcb skill](repo:skills/pcb/SKILL.md) is the reference your agent follows.
