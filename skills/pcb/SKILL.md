---
name: pcb
description: Create, edit and review native KiCad circuit boards (.kicad_pcb), inspect parts and nets, run DRC, and export fabrication files or STEP for enclosure design. Shows boards in the CAD Viewer.
license: MIT
---

# PCB design

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

## Setup

Run cadgen through the `cadgen` command its installation writes, so this skill's commands
share one installation, and its engine server, with the CAD app's:

- `cadgen` below means `cadgen +0.8.2` (`~/.local/bin/cadgen +0.8.2` where `~/.local/bin` is not on your PATH)
- `python` below means `cadgen +0.8.2 run`

If `cadgen` is not on your PATH, or it says 0.8.2 is not installed, run
`uvx --no-config --managed-python --python 3.13 --from cadgen==0.8.2 cadgen doctor` once,
outside any sandbox or with its permission: it installs cadgen, registers it, writes the
`cadgen` command and starts the engine. With the CAD app's server running, nothing else
needs the sandbox's permission: it starts the engine and holds it. Without it, a sandboxed
shell cannot start the engine; when a command says no engine is running, run `cadgen server`
outside the sandbox once.

`cadgen doctor <skill-dir>` reports the installation in use and checks that it is
the one this skill pins, that the CAD kernel loads, and whether the engine every
build runs in is running, starting it when none is; use it for installation or kernel load errors.


Viewing, inspecting and taking snapshots need no KiCad installation. DRC and fabrication/STEP
exports use a user-installed [KiCad 9 or newer](https://www.kicad.org/download/).
`CADGEN_KICAD_CLI` can name its executable; otherwise cadgen checks `kicad-cli`, then
`kicad-cli-nightly` on PATH, then the usual macOS or Windows installation folder.
For the direct export examples below, `kicad-cli` means that same executable.

## Native files are the source

Edit the `.kicad_pcb` itself, preserving its companion `.kicad_pro`, `.kicad_dru`, libraries and
schematic when present. Reading or displaying a board never writes it. There is no cadgen PCB
model, decorator, build step, or generated-board ownership marker. A helper script may make a
requested edit, but reread the current file before editing and preserve unknown records and UUIDs.
Do not regenerate an existing project from an incomplete description.

For creation or structured edits read [native files](references/board-api.md). For parts and
footprints read [parts](references/parts.md). KiCad's file coordinates are millimetres, **y down**;
footprint-local positions and rotations must be transformed into the board frame. Use a net's
actual pad positions when routing. Check the datasheet's pin numbers, footprint orientation and
connector mating side; a plausible-looking layout does not establish electrical correctness.

## Edit and check

1. Inspect the saved board with `from cadgen.pcb import read_board`; record the parts, nets,
   outline, relevant dimensions and constraints before changing it. [Checks](references/checks.md)
   documents this read-only API and clickable references.
2. Edit the native files. Keep net assignments, layer stack, track widths, clearances and custom
   rules consistent with the chosen fab and electrical requirements. Refill changed copper zones
   with KiCad before relying on their saved fill; cadgen displays the fill stored in the file.
3. Run `cadgen pcb drc board.kicad_pcb` (or `--json`). It checks the saved board against its rules
   and exits 1 on error-severity violations or unconnected items. Review warnings too. Resolve
   the cause instead of weakening rules to obtain a clean report.
4. Inspect placement and routing visually: `cadgen pcb snapshot board.kicad_pcb tmp/board.png`.
   Measure constraints DRC cannot establish, such as decoupling placement and connector access.
5. Show the result and explain remaining findings. Export only the requested deliverables from
   that same saved revision; see [manufacturing and STEP](references/manufacturing.md).

## Show the model

Show the user each model you create or change, and any model or file they ask to see.
A file you export is a download: give its path, do not open it.
Snapshots and validation don't replace this. Never screenshot the viewer to confirm your
own work; review with `cadgen snapshot`.

- If your tools include `cad_show` (your host may prefix it), call it with the model's id
  or the file's absolute path, and follow its description for when to call it again.
  The other tools depend on the host. A host that draws CAD cards or tabs (Claude
  Desktop, the Codex app) also has `cad_view`, which reads what the user selected, and
  `cad_screenshot`, which shows you what they see, both of a card or tab that is open, for
  when they ask about it. A text host (Claude Code in a terminal, `codex exec`) draws
  nothing: its `cad_show` opens the model's page in the user's browser and answers with
  the URL to give them, and it has no view to read. `cad_inspect`, `cad_snapshot` and
  `cad_export` are on every host. Call only the tools you have, and never say a card
  shows a model when your host drew none.
- Otherwise give the user the page's link once: a model's page is the `view:` line its
  run prints. For a file, run the CAD Viewer, from any folder:

  ```bash
  cadgen viewer --json FILE [FILE ...]
  ```

  The command ensures this installation's engine, registers each file and prints
  its page, `/<id>`, then exits. Read each file's `url` from `documents` in its one
  JSON line (never guess the port); the URL carries its token query. A page follows
  every later run of its model and every rewrite of its file, so share it once.
  Return that link to the user. If it fails to launch, say so.

## Board views

The board view supports parts, pads, nets, layers, selection, Measure, annotations and Quick Edit.

Snapshots use `cadgen snapshot` or `cadgen pcb snapshot`, including `--job` packets saved by
Quick Edit. Display modes are `board`, `copper`, `assembly`, and `placement`:

```bash
cadgen pcb snapshot board.kicad_pcb tmp/copper.png --display copper
cadgen pcb snapshot board.kicad_pcb tmp/bottom.png --display '{"mode":"copper","side":"bottom","poured":false}'
cadgen pcb snapshot board.kicad_pcb tmp/front.png --display '{"layers":["F.Cu","Edge.Cuts"]}'
```

Bottom views mirror the board and its annotations. Native 2D snapshots support the board's plan
camera, layer visibility and saved ink; they do not support 3D Preview, pose or transparency.
The viewer and snapshots approximate mask/paste openings and use stroke lettering; dimensions,
text boxes, embedded images and keepout hatching are not drawn. KiCad's DRC and manufacturing
exports remain authoritative for fabrication. For an enclosure use KiCad's STEP export, not a
solid inferred from the 2D plot.
