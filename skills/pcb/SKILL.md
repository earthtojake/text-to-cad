---
name: pcb
description: Designs, edits and reviews KiCad circuit boards and schematics (.kicad_pcb, .kicad_sch). Use for any request about a PCB, a schematic or a circuit - parts and nets, placement and routing, ERC and DRC, a review before ordering from JLCPCB, PCBWay or another fab, and fabrication files, a BOM, a netlist or a STEP of the board. Not for the enclosure or other mechanical parts, which the cad skill makes.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# PCB design

A board is its native KiCad files: the `.kicad_pcb`, its schematic and its project. text-to-cad reads,
draws and inspects them itself, and runs KiCad headless for everything KiCad owns: ERC, DRC, exports
and edits through its IPC API. There is no board model or build step; the files are the source.

## Start with the task

| Task | Start with | Reference |
| --- | --- | --- |
| Read a board or a schematic | `kicad_pcb.read`, `kicad_sch.read` in a script; `cad kicad_pcb inspect` | [Checks](references/checks.md), [schematic](references/schematic.md#read-it) |
| Draw or edit a schematic | `kicad_sch.edit`, then `cad kicad_sch erc` | [Schematic](references/schematic.md) |
| Choose parts and footprints | The datasheet, then the project's libraries | [Parts](references/parts.md) |
| Create or edit a board | `kicad_pcb.edit` ([below](#native-files-are-the-source)) | [Native files](references/board-api.md) |
| Place and route | The schematic's netlist, one functional group at a time | [Layout](references/layout.md), [placement](references/placement.md) |
| Check a change | `cad kicad_pcb drc`, snapshots | [Check each change](#check-each-change) |
| Review before ordering | DRC, then measurements, then the checklist | [Before ordering](#before-ordering) |
| Export fabrication files, a BOM, or a STEP for an enclosure | `cad kicad_pcb export`, `cad kicad_sch export` | [Manufacturing](references/manufacturing.md) |
| Show a board or a schematic; what the person can see or pick in it; a missing 3D model | `cad viewer --json FILE` | [Show the model](#show-the-model), [views](references/views.md) |

## Setup

Written for `cad==0.11.17`. Before first use in a chat, run `cad --version`. If `cad` is missing or older than
0.11.12, run `uv tool install cad`, adding `--force` if uv says `cad` already exists.

If cad is a major or minor version newer than this skill, tell the person to update the text-to-cad plugin:
https://github.com/earthtojake/text-to-cad
A project written for an earlier version may need changes; the migration guides say what:
https://github.com/earthtojake/text-to-cad/tree/main/docs/migrations

Reading and inspecting a board or schematic needs no KiCad. DRC, ERC, exports, edits, and drawing a
board (its copper pours are refilled on a copy first) run KiCad's own `kicad-cli` and IPC API, which
`cad` fetches the first time one is needed (kicode: about 100 MB to download, 340 MB on disk, once);
`cad run` gives a script the same. Things to know about that KiCad:

- **It is a nightly (10.99).** A file it saves is in the nightly's format, which a stable KiCad app
  refuses to open; viewing and snapshots still work, and the viewer tells the person which KiCad on
  this computer can open the file. Say so before the first save of a board the person opens in a
  stable KiCad.
- **It runs headless with private settings**, never the person's KiCad app or its settings: never open
  a board in KiCad's app to check it. A project library row that names a stock library as KiCad's own
  tables do (`${KICAD10_SYMBOL_DIR}/Device.kicad_sym`) is read from the KiCad the person installed;
  with none installed, ERC warns `lib_symbol_issues` and DRC `lib_footprint_issues`. A project that
  carries its libraries (`${KIPRJMOD}`) needs no KiCad installed.
- **An edit needs a local socket.** A shell sandbox that refuses sockets (an agent app's default) stops
  an edit at once, saying so: run the script outside the sandbox. Inspecting, DRC, exports and
  snapshots run inside it.
- **A KiCad the person installed is never run.** Where the fetched one does not run on a computer,
  `CAD_KICAD_CLI` names another `kicad-cli` (KiCad 9 or newer; a nightly's for an edit).
- **`CAD_KICAD_REFILL=0` in the server's environment turns the refill off**: showing a board then
  downloads nothing, and its pours are drawn as the file saved them.

## Native files are the source

Edit the `.kicad_pcb` itself and keep its `.kicad_pro`, `.kicad_dru`, libraries and schematic beside
it. Reading or showing a board never writes it. Reread the file before an edit, preserve records and
UUIDs you do not understand, and never regenerate an existing project from a partial description.

A board changes inside a `with` block that hands over KiPy's open `Board` and saves at the end only if
the block changed it; a block that raises saves nothing. `kicad_sch.edit` does the same for a schematic
([schematic](references/schematic.md#edit-it)). Run the script with `cad run board.py`:

```python
from cad import kicad_pcb
from kicode.util.units import from_mm

BOARD = "board.kicad_pcb"

with kicad_pcb.edit(BOARD) as b:       # the board file is the source; the block edits it in place
    power = [t for t in b.get_tracks() if t.net.name in {"+5V", "+3V3"}]
    for track in power:
        track.width = from_mm(0.8)
    b.update_items(power)
    b.refill_zones()
drc = kicad_pcb.drc(BOARD)
if not drc.ok:
    raise SystemExit("\n".join(drc.human_lines()))  # each finding, then FAILED and the count
for kind in ("gerbers", "drill", "pos", "bom", "step"):
    kicad_pcb.export(BOARD, to=kind, out=f"fab/{kind}")
```

- **State the result, not the change**: "U1 is at (10, 20)", "the power tracks are 0.8 mm", never
  "move U1 5 mm". Set absolute positions, rotations, widths and nets, and create an item only when the
  board does not hold it yet, so a script stopped halfway and run again ends where one run would.
- **Import KiPy's names from `kicode`** (`from kicode.proto.common.types import KIID`), never from
  `kipy`: the two cannot share a process.
- **Coordinates are millimetres, y down.** Footprint-local positions and rotations are transformed into
  the board frame; route to a net's actual pad positions.
- **Refill changed zones** (`b.refill_zones()`) before relying on their fill.
- KiCad's first start in a new environment can take a minute.

A board's design starts at its schematic, which says what connects to what: read it, check it with ERC
and look at each sheet before laying out, and hold the board to it after. Place one functional group at
a time, route the nets whose path matters by hand, and direct cad's router (`cad.kicad.route`, inside
the edit, with the plan you give it; never a third-party autorouter) through the rest, with widths
for each net's current ([layout](references/layout.md)). A plausible-looking layout does not
establish electrical correctness: pin numbers, footprint orientation and connector mating side come
from the datasheet.

For anything the typed commands do not cover, `cad run kicad-cli ...` runs the fetched KiCad's
command line with its own subcommands and flags (`cad run kicad-cli pcb --help`); `CAD_KICAD_CLI`
does not change which one that is:

```bash
cad run kicad-cli pcb render --side top --rotate -45,0,45 -o tmp/board.png board.kicad_pcb
cad run kicad-cli project downgrade --dry-run --target 10.0 board.kicad_pro   # then -o DIR without --dry-run
```

Most of its commands write only their `-o` (it may leave a `.kicad_prl` beside a board it reads).
These rewrite the source: `pcb upgrade`, `sch upgrade`, `fp upgrade` and `sym upgrade` without `-o`,
and `pcb drc --refill-zones --save-board`.

## Check each change

Check the saved board after every step, from the revision you will hand over:

| The change | Check it with |
| --- | --- |
| The schematic | `cad kicad_sch erc board.kicad_sch`, and `cad kicad_sch snapshot board.kicad_sch tmp/sheet.png --sheet /Power/` for each sheet changed |
| Board against schematic | The pin-by-pin comparison in [schematic](references/schematic.md#into-the-board-and-back): every pad on its schematic pin's net |
| Anything on the board | `cad kicad_pcb drc board.kicad_pcb` (`--json`): KiCad's DRC against the board's own rules. It exits 1 on errors or unconnected items; unconnected items are the routing still to do |
| Placement | `cad kicad_pcb snapshot board.kicad_pcb tmp/placement.png --display placement`: short, uncrossed ratsnest lines mean a group is placed well |
| Routing | The layout's [property script](references/layout.md#a-property-check): segments off 45 degrees, detours, width for current |
| How copper and silkscreen look | `cad kicad_pcb snapshot board.kicad_pcb tmp/copper.png --display copper` ([more views](references/views.md#board-snapshots)) |
| Ready to order | The review below |

- Warnings count: KiCad's silkscreen, mask and courtyard rules are warnings, and they are what a fab's
  CAM engineer flags.
- Fix the cause; a rule weakened to get a clean report has shown nothing.
- A clean DRC establishes the board's own rules, not the circuit's correctness and not the fab's
  limits. A number is measured from the board (`kicad_pcb.read`), never read off a snapshot.

## Before ordering

A review of one board for the fab and assembler it will be ordered from is a guided review, not the
fab's own engineering check. Gather evidence in this order: KiCad's DRC (every error blocks ordering);
then what DRC cannot measure, from the board read back and the project's BOM; then the checklist of
what no command measures.

| Area | Reference | Measured by |
| --- | --- | --- |
| Fabrication | [review-fabrication](references/review-fabrication.md) | KiCad's DRC against the board's rules; the rest by inspection |
| Electrical | [review-electrical](references/review-electrical.md) | The board read back: decoupling distances, narrowest track per net |
| Assembly and sourcing | [review-assembly](references/review-assembly.md) | The part list and placement file |

### Choosing the rules

Use the chosen fab's own capability page for the board's layer count, copper weight and finish, and
compare it with the project's Board Setup, which may differ. Where the person names no fab, review
against JLCPCB's standard service and say so. Record each limit's source, date and conditions; a rule
that cannot be checked is reported as missing, never invented. A fab's standard tier is a price, not a
physical limit.

### The report

Scope first (board file and revision, fab and service, layers, copper, finish, assembled or bare),
then the findings, errors first, each naming its parts by board reference (`U2`, `C8`, `#net:VBUS`;
`kicad_pcb.read(path).resolve(ref)` says where one is), with the evidence, the rule and its source,
the result and the fix. Then the coverage: checks run, and checks not run with what they need.

| Item | Evidence | Rule | Result | Fix |
| --- | --- | --- | --- | --- |
| `U2` pad 3 to `C8` | measured 3.67 mm centre to centre from the board read back | decoupling within 3 mm (this review's guide) | review | move `C8` beside pin 3 |

The result is **pass** (measured, within a cited limit), **fail** (a measured violation or a KiCad
error), **review** (a risk a person decides) or **unverified** (evidence or the fab's rule is missing).
No findings is not a manufacturability approval. A review alone asks for no edits: fix only when
asked, and recheck the neighbours of every fix.

Export only the deliverables asked for, from the revision you checked
([manufacturing](references/manufacturing.md)). A DRC or ERC error blocks writing fabrication files
unless the person says to go ahead, and the report then names every error they went ahead with.

## Show the model

Show the person each model you create or change as soon as its first run succeeds, and any model
or file they ask to see. A model's page is the `view:` line its run prints, and a file's is the `url`
that `cad viewer --json FILE [FILE ...]` prints for it (never guess the port). Show it with
the first of these you have:

1. `cad_show` among your tools (your host may prefix it): call it with the model's id or the file's
   absolute path; its description says the rest.
2. A tool that opens a page in the app's own browser pane, not in the person's own browser (in the
   Claude desktop app, the Browser pane's `preview_start` with the page's `url`, or its `navigate`):
   open the page there yourself, and give the person the link as well.
3. Neither: give the person the link, to open in their browser.

The page follows every run of the model. A file you export is a download: give its path. Showing is
for the person: to check your own work, review with `cad <type> snapshot`, never a screenshot
of the page. If it fails to launch, say so.

What the board and schematic pages offer the person (layers, selection, 3D, part models), and what
they approximate, is in [views](references/views.md).
