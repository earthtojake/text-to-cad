---
name: pcb
description: Create, edit and review native KiCad circuit boards (.kicad_pcb), inspect parts and nets, run DRC, and export fabrication files or STEP for enclosure design. Shows boards in the CAD Viewer.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# PCB design

## Setup

Run the `cad` command (`~/.local/bin/cad` where `~/.local/bin` is not on your PATH, or where a
project's environment puts its own `cad` first; `cad.cmd` on Windows). If `cad` is not found and
the CAD app was only just added, its server may still be starting: wait five seconds and run the
command again, for up to a minute, before anything else. Otherwise install text-to-cad, outside a sandbox or with its permission:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. Any other failure
says what to do, and `cad doctor` explains the installation.

Viewing, inspecting and taking snapshots need no KiCad installation. DRC (`cad kicad_pcb check`)
and fabrication/STEP exports (`cad kicad_pcb export`) run a user-installed
[KiCad 9 or newer](https://www.kicad.org/download/)'s `kicad-cli`; a `@kicad_pcb` board script
needs a KiCad nightly's (10.99), the only one with the headless `api-server` for now, and is
refused before it starts without one.
`CAD_KICAD_CLI` can name its `kicad-cli` (the command line itself, named `kicad-cli`); otherwise
`cad kicad_pcb check` uses `kicad-cli` on PATH, then the one inside the usual macOS or Windows installation.
It runs `kicad-cli` headless, with private settings, and never opens KiCad. For the direct export
examples below, `kicad-cli` means that same executable; never open a board in KiCad's app to check it.

Native boards here use KiCad's nightly format, so they open only in a nightly KiCad app, and DRC and
exports need a nightly `kicad-cli` for now. A stable KiCad refuses a board saved by the nightly (DRC
then reports `kicad_failed`); viewing and snapshots still work.

## Native files are the source

Edit the `.kicad_pcb` itself, preserving its companion `.kicad_pro`, `.kicad_dru`, libraries and
schematic when present. Reading or displaying a board never writes it. There is no text-to-cad PCB
model, build step, or generated-board ownership marker. A helper script may make a requested edit,
but reread the current file before editing and preserve unknown records and UUIDs. Do not regenerate
an existing project from an incomplete description.

A persistent board script edits the board through KiCad's IPC API: `@kicad_pcb` hands the function
the open board (kipy's `Board`), saves it when the function returns and saves nothing when it raises.
It needs a KiCad nightly's `kicad-cli` (10.99: its headless `api-server`, which `kicad-cli api-server
--help` lists; a stable `kicad-cli` is refused up front, before any server starts) and the `kicad`
extra (`cad[kicad]`, kipy) in the environment the script runs in. Saving writes the board in the
nightly's format: a board from an older KiCad is upgraded, which the run says, and that older KiCad
can no longer open it. A `@step` stacked on it writes the saved board's STEP (`kicad-cli pcb export
step --subst-models`); parts whose 3D model is missing or only in VRML have no body in it, which the run
names:

```python
from cad import kicad_pcb, step

@step("STEP/board.step")
@kicad_pcb("board.kicad_pcb")          # the board file is the source; the function edits it
def board(b):
    for footprint in b.get_footprints():
        ...

if __name__ == "__main__":
    board()
```

For creation or structured edits read [native files](references/board-api.md). For parts and
footprints read [parts](references/parts.md). To place and route a board, read
[layout](references/layout.md): start from the schematic's netlist, place one part or functional
group at a time, route octolinear by hand (never an autorouter) with widths for each net's current,
and check each step with `cad kicad_pcb check` and a script of the layout's own properties. KiCad's file coordinates are millimetres, **y down**;
footprint-local positions and rotations must be transformed into the board frame. Use a net's
actual pad positions when routing. Check the datasheet's pin numbers, footprint orientation and
connector mating side; a plausible-looking layout does not establish electrical correctness.

## Edit and check

1. Inspect the saved board with `from cad.kicad_pcb import read_board` in a script run with
   `cad run`; record the parts, nets, outline, relevant dimensions and constraints before
   changing it. [Checks](references/checks.md) documents this read-only API and clickable references.
2. Edit the native files. Keep net assignments, layer stack, track widths, clearances and custom
   rules consistent with the chosen fab and electrical requirements. Refill changed copper zones
   with KiCad before relying on their saved fill; the viewer displays the fill stored in the file.
3. Run `cad kicad_pcb check board.kicad_pcb` (or `--json`). It checks the saved board against its rules
   (its `.kicad_pro`'s; without one, KiCad's defaults, which it warns about as `no_project`)
   and exits 1 on error-severity violations or unconnected items. Review warnings too. Resolve
   the cause instead of weakening rules to obtain a clean report.
4. Inspect placement and routing visually: `cad kicad_pcb snapshot board.kicad_pcb tmp/board.png`.
   Measure constraints DRC cannot establish, such as decoupling placement and connector access.
5. Show the result and explain remaining findings. Export only the requested deliverables from
   that same saved revision; see [manufacturing and STEP](references/manufacturing.md).

## Show the model

Show the user each model you create or change, and any model or file they ask to see.
A file you export is a download: give its path, do not open it.
Snapshots and validation don't replace this. Never screenshot the viewer to confirm your
own work; review with `cad <type> snapshot`.

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
  cad viewer --json FILE [FILE ...]
  ```

  The command ensures this installation's server, registers each file and prints
  its page, `/<id>`, then exits. Read each file's `url` from `documents` in its one
  JSON line (never guess the port); the URL carries its token query. A page follows
  every later run of its model and every rewrite of its file, so share it once.
  Return that link to the user. If it fails to launch, say so.

## Board views

The board view supports parts, pads, nets, layers, selection, Measure, annotations and Quick Edit.

Snapshots use `cad kicad_pcb snapshot`, including `--job` packets saved by Quick Edit. Display modes are
`board`, `copper`, `assembly`, and `placement`:

```bash
cad kicad_pcb snapshot board.kicad_pcb tmp/copper.png --display copper
cad kicad_pcb snapshot board.kicad_pcb tmp/bottom.png --display '{"mode":"copper","side":"bottom","poured":false}'
cad kicad_pcb snapshot board.kicad_pcb tmp/front.png --display '{"layers":["F.Cu","Edge.Cuts"]}'
```

Bottom views mirror the board and its annotations. Native 2D snapshots support the board's plan
camera, layer visibility and saved ink; they do not support 3D Preview, pose or transparency.
The viewer and snapshots approximate mask/paste openings and use stroke lettering; dimensions,
text boxes, embedded images and keepout hatching are not drawn. KiCad's DRC and manufacturing
exports remain authoritative for fabrication. For an enclosure use KiCad's STEP export, not a
solid inferred from the 2D plot.
