# Fabrication

Read this for the fabrication area of a [review before ordering](../SKILL.md#before-ordering).

## Sources

Where the person names no fab, start from these two, and read
[choosing the rules](../SKILL.md#choosing-the-rules) before citing either:

- [JLCPCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities): track and space,
  drills, annular rings, copper to edge, silkscreen and solder mask, per layer count.
- [KiCad's design rule checks](https://docs.kicad.org/master/en/pcbnew/pcbnew.html#design-rule-checking):
  what each DRC violation type means and which Board Setup value it reads.

[Manufacturing](manufacturing.md#standard-tier-limits) tabulates the standard-tier limits of JLCPCB, PCBWay
and OSH Park and the board rule each maps to. Recheck the fab's page for anything near a limit, and for any
other fab.

## The board's rules are the first question

KiCad's DRC checks only the project's own rules ([where they live](board-api.md#design-rules)), so compare
those with the fab's page before reading its result: track width, clearance, via and hole sizes, annular
ring and copper to edge. A rule looser than the selected service allows is a finding even when DRC is
clean. To see what it let through, set the rule to the fab's limit and run DRC again: a board that is clean
at 0.09 mm clearance and ordered from a 0.10 mm service has proved nothing about its gaps between the two.

## Review

Run `cad kicad_pcb drc board.kicad_pcb`. Its types are KiCad's; how the review reads the ones whose fix is
not in their name:

| Type | Read it as |
| --- | --- |
| `copper_edge_clearance` | pull the copper in: edge connectors and castellations are a fab option, not a default |
| `solder_mask_bridge` | pads too close for a mask web between them: on a fine-pitch part, confirm the fab's minimum web, or accept a gang opening |
| `silk_over_copper` (KiCad: "clipped by solder mask"), `silk_overlap`, `silk_edge_clearance` | the fab clips the artwork itself and makes the board, with unreadable references and marks: **review**, and **fail** when a polarity mark or pin-1 indicator is the clipped part |
| `starved_thermal` | a pad reaches its pour through too few spokes and may not solder well: add spokes, connect the pad solid, or add a track |
| `courtyards_overlap` | spread the parts: an assembler needs the courtyard |

Then by inspection, with a snapshot and the board read back (`kicad_pcb.read`):

- Outline: closed, one `Edge.Cuts` loop per board, internal cutouts with inside corners no tighter than the
  fab's router cuts.
- Layer count, thickness, copper weight and finish match what will be ordered; ENIG for fine pitch or gold
  fingers, HASL otherwise.
- Silkscreen text height (`text.size`) and stroke meet the fab's minimum
  ([its limits](manufacturing.md#standard-tier-limits)), or it prints as a smear.
- Mounting holes: plated or not as intended, clearance to copper on both sides.
- Panelization, V-score or mouse bites only if the person panels it; a fab panels a single board itself.
