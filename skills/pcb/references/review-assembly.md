# Assembly and sourcing

Read this for the assembly area of a [review before ordering](../SKILL.md#before-ordering): what an
assembler needs from the board, its part list and its placement file. Skip it for a bare board the person
solders by hand, and say so.

## Sources

- [JLCPCB assembly capabilities](https://jlcpcb.com/capabilities/pcb-assembly-capabilities)
  and its parts library: what is stocked, basic versus extended parts.
- The chosen assembler's BOM and placement file requirements (PCBWay, Aisler,
  Eurocircuits each document theirs).

## The part list

The BOM is written from the schematic beside the board ([manufacturing](manufacturing.md#exports)); a
board with no schematic has only its footprints' fields. Review it against the board read back
(`kicad_pcb.read`: each part's `value`, `footprint`, `fields` and `dnp`):

| Check | Read it as |
| --- | --- |
| A fitted part with pads has no part number (`LCSC` for JLCPCB, `MPN` for every other assembler) | **fail** for an assembled order: the assembler cannot match the row. Holes, test points, fiducials and logos (`H`, `MH`, `TP`, `FID`, `LOGO` references) are made, not bought: skip them |
| One part number on parts with different footprints | **fail**: one of them has the wrong number or the wrong footprint; an assembler places one package per number |
| A BOM row's footprint does not match the part number's package (0402 vs 0603, SOT-23 vs SOT-23-5) | **fail** |
| A do-not-populate part appears in the BOM or the placement file | **fail**: mark it DNP in the schematic and update the board. The BOM export leaves DNP parts out and the placement export keeps them, so write the placement file without them ([manufacturing](manufacturing.md#exports)) |

Never invent a part number. Search the assembler's library for a part matching
the value, package and rating, give the person the candidates, and let them pick.

## The placement file

The placement file is KiCad's position export (`--to pos`,
[manufacturing](manufacturing.md#exports)), one row per placed part. Check:

- Its origin: the export measures from KiCad's page origin. An assembler that wants the drill/place
  origin, set on a corner of the outline, gets the file from KiCad's command line
  (`--use-drill-file-origin`).
- Polarity: diodes, LEDs, electrolytics and ICs have a pin-1 or polarity mark on
  silkscreen that the DRC did not clip (see [fabrication](review-fabrication.md)).
- Rotation: the assembler's zero orientation can differ from KiCad's; tell the
  person to check the placement preview on the order page, where a wrong rotation
  shows and is corrected.
- Parts on both sides double the assembly setup; say so if one side could hold them.
- Fiducials: three on the board, or on the panel, if the assembler asks for them.
- Clearance round tall parts and connectors for the nozzle and for hand soldering
  of through-hole parts the assembler does not place.

## Cost, kept apart

For JLCPCB, "basic" parts carry no setup fee and "extended" ones do. Suggest a
basic equivalent for passives and common ICs as a cost note, never as a
manufacturing finding.
