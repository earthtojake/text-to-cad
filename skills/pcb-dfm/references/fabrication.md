# Fabrication

## Sources

Where the user names no fab, start from these two, and read the rule-selection
rules in `SKILL.md` before citing either:

- [JLCPCB capabilities](https://jlcpcb.com/capabilities/pcb-capabilities): track and space,
  drills, annular rings, copper to edge, silkscreen and solder mask, per layer count.
- [KiCad's design rule checks](https://docs.kicad.org/master/en/pcbnew/pcbnew.html#design-rule-checking):
  what each DRC violation type means and which Board Setup value it reads.

$pcb's manufacturing reference tabulates the standard-tier limits of the common
fabs (JLCPCB, PCBWay, OSH Park, Aisler, Eurocircuits, Seeed Fusion, NextPCB) as
the design rule names they map to. Recheck the fab's page for anything near a
limit.

## The board's rules are the first question

KiCad's DRC only checks the numbers in the project's design rules (`.kicad_pro`,
Board Setup > Constraints) and its `.kicad_dru` custom rules. A clean DRC proves
the board meets *those*, not the fab's.

Compare `.kicad_pro` (`board.design_settings.rules`) and custom rules with the fab's page:
track width, clearance, via/hole sizes, annular ring and copper-to-edge. A rule looser than
the selected service allows remains a finding even when DRC is clean.

## Review

Run KiCad's DRC with $pcb: `cadgen pcb drc board.kicad_pcb`. Its types are KiCad's:

| Type | Meaning | Usual fix |
| --- | --- | --- |
| `clearance`, `hole_clearance` | copper or a hole closer than the rules | move or narrow; check the rule is the fab's |
| `copper_edge_clearance` | copper too close to the outline | pull it in; edge connectors and castellations are a fab option, not a default |
| `track_width`, `annular_width` | below the rules' minimum | widen; a ring under the fab's minimum breaks out of the drill |
| `solder_mask_bridge` | pads too close for a mask web between them | fine-pitch parts: confirm the fab's minimum web, or accept a gang opening |
| `silk_over_copper` | silkscreen over a mask opening (KiCad: "clipped by solder mask") | the fab removes it: move the text or outline off the pads |
| `silk_overlap`, `silk_edge_clearance` | silkscreen over silkscreen, or off the edge | move references; small boards often hide them on Fab layers instead |
| `courtyards_overlap` | parts placed into each other | spread them; an assembler needs the courtyard |
| `starved_thermal` | a pad reaches its pour through too few spokes | add spokes, connect the pad solid, or add a track; it may not solder well |
| `via_dangling`, `track_dangling` | copper ending on nothing | remove it, or finish the connection it was meant to make |
| `unconnected_items` | a connection the nets need and copper does not make | route it; the board is not finished |

Silkscreen findings never stop a fab, which clips the artwork itself, but the
result is unreadable references and polarity marks. Treat them as **review**
items, and as **fail** when a polarity mark or pin-1 indicator is the clipped
part.

Then by inspection, with a snapshot and the board read back ($pcb's `read_board`):

- Outline: closed, one `Edge.Cuts` loop per board, internal cutouts with radii the
  fab's router can cut (often 0.5 mm minimum inside corners).
- Layer count, thickness, copper weight and finish match what will be ordered;
  ENIG for fine pitch or gold fingers, HASL otherwise.
- Text height and stroke on silkscreen meet the fab's minimum (JLCPCB: 1 mm height,
  0.15 mm stroke) or it prints as a smear.
- Mounting holes: plated or not as intended, clearance to copper on both sides.
- Panelization, V-score or mouse bites only if the user panels it; a fab panels a
  single board for you.

## Worked reasoning example

The following numbers are illustrative inputs, not default limits.

A board drawn in KiCad has a clean DRC with a 0.09 mm minimum clearance in its
Board Setup. The user orders 2-layer boards from JLCPCB, whose standard 2-layer
space is 0.10 mm. The DRC passing proves nothing about the 0.09-0.10 mm gaps:
set the rule to 0.10 mm, rerun the DRC with $pcb (`cadgen pcb drc`), and report
what fails.
