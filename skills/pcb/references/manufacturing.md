# Manufacturing: Gerbers, BOM, placement, and ordering from any fab

A finished board (no DRC error, nothing unrouted) declares what the fab needs:

```python
from cadgen import pcb


@pcb(gerber=True, bom=True, pos=True)
def controller():
    board = pcb.Board(outline=..., fab=pcb.PCBWAY)   # checked against PCBWay's limits
    ...
```

`python controller.py` then writes, beside the KiCad project:

- `controller.gerbers.zip`: Gerber X2 files for every copper, mask, paste and silkscreen
  layer and the outline, the Gerber job file, and Excellon drill files (millimetres,
  plated and unplated apart). Every PCB fab makes boards from these; this zip is in the
  form all of them take.
- `controller.bom.csv`: one row per distinct part, DNP parts left out. Its columns are
  JLCPCB's required ones, `Comment, Designator, Footprint, LCSC Part #`, which every other
  assembler accepts, then `Quantity, MPN, Manufacturer, Description`, which they ask for.
- `controller.pos.csv`: the pick-and-place file, one row per placed part, millimetres from
  the script's origin, DNP parts left out: `Designator, Val, Package, Mid X, Mid Y,
  Rotation, Layer`, which every assembler reads.

So the files are the same whichever fab makes the board: only the limits it is checked
against change with `fab=`. A path instead of `True` moves a file
(`@pcb(gerber="../fab/controller.zip")`). The same board always writes the same bytes.
`gerber=` and `pos=` refuse a draft: the build fails and lists what is left to route. For a
board drawn elsewhere, the doors take the `.kicad_pcb`:

```bash
cadgen pcb gerber board.kicad_pcb fab/board.gerbers.zip
cadgen pcb bom board.kicad_pcb       # needs board.kicad_sch beside it
cadgen pcb pos board.kicad_pcb
```

## Choosing a fab

`fab=` sets the limits the board is checked against: that fab's standard service, the
price tier with no surcharge, for two copper layers or for four and more. Numbers from each
fab's own capability pages (October 2026); check the page before ordering anything near a
limit, and for anything finer than the standard tier, pass `rules=fab.rules.replace(...)`
and expect a surcharge.

| `fab=` | Track / space (2 layers) | Smallest drill | Copper to edge | 4+ layers | Assembly |
| --- | --- | --- | --- | --- | --- |
| `pcb.JLCPCB` (default) | 0.10 / 0.10 mm | 0.3 mm | 0.2 mm | 0.09 / 0.09 mm | yes, from LCSC's stock |
| `pcb.PCBWAY` | 0.127 / 0.127 mm | 0.2 mm | 0.3 mm | same | yes, any parts |
| `pcb.OSHPARK` | 0.152 / 0.152 mm | 0.254 mm | 0.381 mm | 0.127 / 0.127 mm | no: bare boards |
| `pcb.AISLER` | 0.2 / 0.15 mm (HASL) | 0.3 mm | 0.3 mm | 0.125 / 0.125 mm (ENIG) | yes, from MPN fields |
| `pcb.EUROCIRCUITS` | 0.15 / 0.15 mm | 0.35 mm | 0.25 mm | same, 0.4 mm inner edge | yes |
| `pcb.SEEED_FUSION` | 0.152 / 0.152 mm | 0.3 mm | 0.3 mm | same | yes |
| `pcb.NEXTPCB` | 0.127 / 0.127 mm | 0.3 mm | 0.2 mm | same | yes |

`pcb.FABS` lists them; `fab.rules` and `fab.multilayer` hold every number (vias, annular
rings, hole spacing, text). A board for a fab not listed passes its numbers as
`rules=pcb.Rules(...)`: the files are the same.

## Ordering

Upload `*.gerbers.zip` on the fab's PCB order page; board size and layer count are read
from it. 1.6 mm, 1 oz copper and HASL (or ENIG for fine pitch) are the usual defaults. For
assembly, upload `*.bom.csv` and `*.pos.csv` as well and check the fab's placement preview:
a footprint whose zero rotation differs from the fab's model shows up rotated there, and is
corrected on their page (JLCPCB and Eurocircuits both use their own zero orientation).

- **JLCPCB**: parts need an `LCSC` field (`properties={"LCSC": "C25804"}`): JLCPCB matches
  BOM rows by it. Prefer its "basic" parts (no setup fee) for passives and common ICs.
- **PCBWay**: any parts; give each an `MPN` (and `Manufacturer`) field so its BOM review
  can quote them.
- **OSH Park**: bare boards only; it also takes the `.kicad_pcb` itself, but processes it
  with KiCad 9, so upload the Gerbers.
- **Aisler**: takes the KiCad project itself (KiCad 10 included): zip the `.kicad_pro`,
  `.kicad_sch` and `.kicad_pcb` and upload that; it assembles from each part's `MPN` field.
- **Eurocircuits**: prefers the KiCad project too, and reads the placement from it; its BOM
  wants `MPN`, value, package and description.
- **Seeed Fusion** and **NextPCB**: Gerbers, and for assembly the BOM and placement files;
  give parts an `MPN`. NextPCB's form asks for its own BOM spreadsheet: copy the columns
  across.

Never order on the user's behalf: hand them the files and the steps.

## Before handing off

- The build's last line says `built`, not `draft`, and there were no warnings you did not
  read.
- The board was checked against the fab it will be ordered from (`fab=`).
- Every part has a value, and parts to be assembled have an `LCSC` (JLCPCB) or `MPN` field.
- The silkscreen labels connectors and polarity (pin 1, +/-, LED and diode orientation).
- Mounting holes and connectors match the enclosure (compose the board with `@step` into
  the case and look at it).
