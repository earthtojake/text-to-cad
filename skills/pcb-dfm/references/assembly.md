# Assembly and sourcing

What an assembler needs from the board, its part list and its placement file.
Skip this file for a bare board the user solders by hand, and say so.

## Sources

- [JLCPCB assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities)
  and its parts library: what is stocked, basic versus extended parts.
- The chosen assembler's BOM and placement file requirements (PCBWay, Aisler,
  Eurocircuits each document theirs).

## The part list

A board alone has no bill of materials: a project keeps its part list as
data (reference, value, footprint, part number) and writes the BOM CSV from it;
a board drawn in KiCad has its schematic's BOM. Review whichever exists, against
the board read back ($pcb's `read_board` lists every part with its value and
footprint):

| Check | Read it as |
| --- | --- |
| A fitted part with pads has no part number (`LCSC` for JLCPCB, `MPN` for every other assembler) | **fail** for an assembled order: the assembler cannot match the row. Holes, test points, fiducials and logos (`H`, `MH`, `TP`, `FID`, `LOGO` references) are made, not bought: skip them |
| One part number on parts with different footprints | **fail**: one of them has the wrong number or the wrong footprint; an assembler places one package per number |
| A BOM row's footprint does not match the part number's package (0402 vs 0603, SOT-23 vs SOT-23-5) | **fail** |
| A do-not-populate part appears in the BOM or the placement file | **fail**: mark it (`attributes.do_not_populate`) and export with `exclude_dnp` |

Never invent a part number. Search the assembler's library for a part matching
the value, package and rating, give the user the candidates, and let them pick.

## The placement file

The placement file is KiCad's position export (`board.export_position`, with
$pcb), one row per placed part: reference, value, footprint, x, y, rotation,
side. Check:

- Its origin is the board's drill/place origin, set on a corner of the outline,
  so the coordinates are the fab's.
- Polarity: diodes, LEDs, electrolytics and ICs have a pin-1 or polarity mark on
  silkscreen that the DRC did not clip (see [fabrication](fabrication.md)).
- Rotation: the assembler's zero orientation can differ from KiCad's; tell the
  user to check the placement preview on the order page, where a wrong rotation
  shows and is corrected.
- Parts on both sides double the assembly setup; say so if one side could hold them.
- Fiducials: three on the board, or on the panel, if the assembler asks for them.
- Clearance round tall parts and connectors for the nozzle and for hand soldering
  of through-hole parts the assembler does not place.

## Cost, kept apart

For JLCPCB, "basic" parts carry no setup fee and "extended" ones do. Suggest a
basic equivalent for passives and common ICs as a cost note, never as a
manufacturing finding.

## Worked reasoning example

The following numbers are illustrative inputs, not default limits.

41 fitted parts have no part number. The user orders bare boards from OSH Park
and hand-solders: the finding does not apply, and the report says why. The same
board ordered assembled from JLCPCB: **fail**, with each part's value and
footprint listed so the user can choose `LCSC` numbers, and a note that resistors
and capacitors are usually basic parts.
