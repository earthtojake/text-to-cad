---
name: pcb
description: Create, edit, lay out and review native KiCad circuit boards (.kicad_pcb) and their schematics (.kicad_sch) - parts and nets, ERC, placement and routing, DRC, and a review before ordering (fab limits, decoupling, track width for current, assembly and BOM sourcing for JLCPCB, PCBWay or another fab); exports fabrication files, the netlist and BOM, or STEP for enclosure design. Shows boards in the CAD Viewer.
license: MIT
metadata:
  repository: earthtojake/text-to-cad
---

# PCB design

## Setup

Run the `cad` command (`~/.local/bin/cad` where it is not on your PATH; `cad.exe` on Windows). If
it is missing, install text-to-cad, outside a sandbox or with its permission:

```bash
curl -fsSL https://texttocad.dev/install.sh | sh
```

On Windows, in PowerShell: `irm https://www.texttocad.dev/install.ps1 | iex`. If the CAD app was
only just added, its server may still be starting: try again for up to a minute first. `cad doctor`
explains any other failure.

Viewing, inspecting and taking snapshots need no KiCad. DRC (`cad kicad_pcb drc`), ERC (`cad
kicad_sch erc`), every export (`cad kicad_pcb export`, `cad kicad_sch export`) and a `@kicad_pcb` board script run KiCad's command line, `kicad-cli`,
and its IPC API from kicode, the `kicad` extra (`cad[kicad]`): the `cad` command installs it the first
time a board command needs it (some 100 MB, once; nothing for you to install), and `cad run` gives a
board script's environment it. A KiCad you installed yourself is never run. `CAD_KICAD_CLI` can name
another `kicad-cli` (the command line itself, named `kicad-cli`; KiCad 9 or newer, a nightly's for a
board script). It runs headless, with private settings, and never opens KiCad's app; never open a
board in KiCad's app to check it.

kicode's KiCad is a nightly (10.99), so a board it saves is in the nightly's format, which a stable
KiCad app refuses; viewing and snapshots still work.

## Native files are the source

Edit the `.kicad_pcb` itself, preserving its companion `.kicad_pro`, `.kicad_dru`, libraries and
schematic when present. Reading or displaying a board never writes it. There is no text-to-cad PCB
model, build step, or generated-board ownership marker. A helper script may make a requested edit,
but reread the current file before editing and preserve unknown records and UUIDs. Do not regenerate
an existing project from an incomplete description.

A persistent board script edits the board through KiCad's IPC API: `@kicad_pcb` hands the function
the open board (KiPy's `Board`, as kicode names it: `kicode.board.Board`), saves it when the function
returns and saves nothing when it raises. Run it with `cad run board.py`, which gives it the `kicad`
extra (kicode: KiPy and a `kicad-cli` with its headless `api-server`); a `kicad-cli` that
`CAD_KICAD_CLI` names without one is refused up front, before any server starts. Import KiPy's names
from `kicode` (`from kicode.proto.common.types import KIID`), never from `kipy`: the two cannot share a
process. Saving writes the board in the nightly's format: a board from an older KiCad is upgraded,
which the run says, and that older KiCad can no longer open it. A `@step` stacked on it writes the saved board's STEP (`kicad-cli pcb export
step --subst-models`), and a `@glb` its GLB the same way; parts whose 3D model is missing (or, in a STEP,
only in VRML) have no body in it, which the run names. A `@dxf` writes its outline and drilled holes, for
an enclosure (`cad kicad_pcb export --to dxf`'s file):

```python
from cad import dxf, kicad_pcb, step

@step("STEP/board.step")
@dxf("DXF/board-outline.dxf")
@kicad_pcb("board.kicad_pcb")          # the board file is the source; the function edits it
def board(b):
    for footprint in b.get_footprints():
        ...

if __name__ == "__main__":
    board()
```

A board's design starts at its schematic, which says what connects to what: read it, check it with
ERC and look at each sheet ([schematic](references/schematic.md)) before laying out, and hold the board
to it after. For creation or structured edits read [native files](references/board-api.md). For parts and
footprints read [parts](references/parts.md). To place and route a board, read
[layout](references/layout.md): start from the schematic's netlist, place one part or functional
group at a time, route octolinear by hand (never an autorouter) with widths for each net's current,
and check each step with `cad kicad_pcb drc` and a script of the layout's own properties. KiCad's file coordinates are millimetres, **y down**;
footprint-local positions and rotations must be transformed into the board frame. Use a net's
actual pad positions when routing. Check the datasheet's pin numbers, footprint orientation and
connector mating side; a plausible-looking layout does not establish electrical correctness.

## Edit

1. Inspect the saved board with `from cad import kicad_pcb` in a script run with
   `cad run`; record the parts, nets, outline, relevant dimensions and constraints before
   changing it. [Checks](references/checks.md) documents this read-only API and clickable references.
2. Edit the native files, or the board in a board script. Keep net assignments, layer stack, track
   widths, clearances and custom rules consistent with the chosen fab and electrical requirements.
   Refill changed copper zones with KiCad (`b.refill_zones()` in a board script) before relying on
   their saved fill.

## Check each change

Check the saved board after every step, from the same revision you will hand over:

| The change | Check it with |
| --- | --- |
| The schematic | `cad kicad_sch erc board.kicad_sch` (KiCad's ERC: errors fail it) and `cad kicad_sch snapshot board.kicad_sch tmp/sheet.png --sheet /Power/` for each sheet changed ([schematic](references/schematic.md)) |
| Board against schematic | the pin-by-pin comparison in [schematic](references/schematic.md#into-the-board-and-back): every pad on its schematic pin's net |
| Anything: parts, copper, zones, rules | `cad kicad_pcb drc board.kicad_pcb` (or `--json`): KiCad's DRC against the board's own rules (its `.kicad_pro`'s; without one, KiCad's defaults, which it warns about as `no_project`). It exits 1 on error-severity violations or unconnected items. Unconnected items are the routing still to do |
| Placement | `cad kicad_pcb snapshot board.kicad_pcb tmp/placement.png --display placement`: short, uncrossed ratsnest lines mean a group is placed well; measure decoupling distance and connector access with `kicad_pcb.read` |
| Routing | The layout's property script ([layout](references/layout.md#a-property-check)): segments off 45 degrees, detours, width for current |
| How copper and silkscreen look | `cad kicad_pcb snapshot board.kicad_pcb tmp/copper.png --display copper` (and `--display '{"mode":"copper","side":"bottom"}'`) |
| Ready to order | The review below |

- Review warnings too: KiCad's silkscreen, mask and courtyard rules are warnings, and they are what a
  fab's CAM engineer flags.
- Resolve the cause instead of weakening rules to obtain a clean report.
- A clean DRC establishes the board's own rules, nothing more: not the circuit's correctness and not
  the fab's limits. A number is never read off a snapshot.

## Before ordering

A review of one board, for the fab and assembler it will be ordered from, is a guided review, not a
fab's own engineering check: report what was not checked. Gather evidence in this order: KiCad's DRC
(every error blocks ordering); then measurements DRC cannot make, from the board read back with
`kicad_pcb.read` and the project BOM; then the checklist of what no command measures, with a snapshot.

| Area | Reference | Measured by |
| --- | --- | --- |
| Fabrication | [review-fabrication](references/review-fabrication.md) | KiCad's DRC against the board's rules; the rest by inspection |
| Electrical | [review-electrical](references/review-electrical.md) | the board read back: decoupling distances, narrowest track per net |
| Assembly and sourcing | [review-assembly](references/review-assembly.md) | the part list and placement file, by inspection |

Each finding names its parts by board reference (`U2`, `C8`, `#net:VBUS`); `kicad_pcb.read(path).resolve(ref)`
says where one is.

### Choosing the rules

1. Use the selected fab's own capability page for the board's layer count, copper weight and finish.
   The project's Board Setup and custom rules may differ from the fab's limits: compare them.
2. Where the person names no fab, review against JLCPCB's standard service and say so.
3. Record the source, its date and the conditions (layers, copper, finish) with every limit you
   adopt. If it cannot be checked, report the missing rule rather than invent one.

A fab's standard tier is a price, not a physical limit: finer work is often possible at a surcharge.
Say which it is.

### The review

Scope first: board file and revision, fab and service, layers, copper, finish, assembled or bare.
Then the findings, errors first, each with where (board references), the evidence (the command or
measurement), the rule and its source, the result and the fix; then the coverage: checks run, and
checks not run with what they need. No findings is not a manufacturability approval.

| Item | Evidence | Rule | Result | Fix |
| --- | --- | --- | --- | --- |
| `U2` pad 3 to `C8` | measured 3.67 mm centre to centre from the board read back | decoupling within 3 mm (this review's guide) | review | move `C8` beside pin 3 |

**pass** for a measured item within a cited limit; **fail** for a measured violation or a KiCad
error; **review** for a risk a person decides; **unverified** where evidence or the fab's rule is
missing. Keep cost suggestions (basic vs extended parts, a cheaper finish) apart from manufacturing
constraints. A review alone does not ask for edits or an order: fix only when asked, then check the
neighbours of every fix (a moved capacitor can open a clearance elsewhere). Never order on the
person's behalf.

Export only the requested deliverables from the saved revision you checked; see
[manufacturing and STEP](references/manufacturing.md).

## Show the model

Show the person each model you create or change, and any model or file they ask to see. If your
tools include `cad_show` (your host may prefix it), call it with the model's id or the file's
absolute path; its description says the rest. Otherwise give the person the page's link once: a
model's page is the `view:` line its run prints, and a file's is the `url` that
`cad viewer --json FILE [FILE ...]` prints for it (never guess the port). A file you export is a
download: give its path. Never screenshot the viewer to check your own work; review with
`cad <type> snapshot`. If it fails to launch, say so.

## Board views

The board view supports layers, selection, Measure, annotations and Quick Edit. Select works as
KiCad's: a click picks a part, pad, track, via, zone, rule area, text, dimension or graphic, as its
Selection Filter ticks them (locked items only when the person ticks them), and a drag names an
area, a box on the layer the person works on. The sidebar's **Circuit** lists the parts in the
schematic blocks their footprints record (by kind on a board that records none) and the nets: a
block picks every part in it, a net picks the whole net. Each arrives as a reference
([checks](references/checks.md#references) says what each names and how to resolve it). The
**Layers** tab hides and shows layers and sets the active layer (drawn on top); the toolbar's
Display menu sets Dim other layers and the zones' and tracks' opacity. They are the display, so a
Quick Edit's packet draws the same.

Snapshots use `cad kicad_pcb snapshot`, including `--job` packets saved by Quick Edit. Display modes are
`board`, `copper`, `assembly`, and `placement`:

```bash
cad kicad_pcb snapshot board.kicad_pcb tmp/copper.png --display copper
cad kicad_pcb snapshot board.kicad_pcb tmp/bottom.png --display '{"mode":"copper","side":"bottom","poured":false}'
cad kicad_pcb snapshot board.kicad_pcb tmp/front.png --display '{"layers":["F.Cu","Edge.Cuts"]}'
cad kicad_pcb snapshot board.kicad_pcb tmp/inner.png --display '{"active":"In1.Cu","dim":true,"zones":0.3}'
```

Bottom views mirror the board and its annotations. Native 2D snapshots support the board's plan
camera, layer visibility and saved ink; they do not support 3D Preview, pose or transparency.
The viewer and snapshots draw the board as KiCad's PCB editor shows it (front copper active, pours
at 60%, pad numbers and net names on pads, vias and tracks, dimensions; no drawing sheet, the board alone); they approximate mask/paste openings
and use stroke lettering; text boxes, tables and embedded images are not drawn. KiCad's DRC and manufacturing
exports remain authoritative for fabrication. For an enclosure use KiCad's STEP export, not a
solid inferred from the 2D plot.
