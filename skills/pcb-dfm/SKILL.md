---
name: pcb-dfm
description: Design-for-manufacturing review of a KiCad printed circuit board before it is ordered - fab limits, silkscreen and solder mask, drills and copper to edge; decoupling, track width for current; BOM sourcing (LCSC, MPN), footprints, polarity, fiducials and placement for assembly. Use when the user asks whether a board can be made or assembled, asks for a PCB, KiCad or BOM review, a DFM or DFA check, or what to fix before ordering from JLCPCB, PCBWay or another fab.
license: MIT
---

# PCB DFM review

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth.

Produce a manufacturability review of one KiCad board (`.kicad_pcb`, with its
`.kicad_pro` beside it and its `.kicad_dru` when it has custom rules), for the
fab and assembler it will be ordered from. This is a guided review, not a fab's
own engineering check. Report what was not checked explicitly.

Review the saved native files, including their project rules and schematic when present.
Fixes belong in those files. Use the PCB skill's read-only board inspection and DRC commands
when they are available; the checklists here also work with KiCad's own reports and exports.

## Evidence, in this order

1. **KiCad's DRC.** With $pcb: `cadgen pcb drc board.kicad_pcb` runs KiCad's
   design rule check on the saved board and prints every violation of the
   board's rules and custom rules and every unconnected item; it exits 1 on any
   error. Every
   error blocks ordering. Read every warning too: KiCad's
   silkscreen, mask and courtyard rules are warnings, and they are what a fab's
   CAM engineer flags.
2. **Measurements.** What KiCad does not check: decoupling distance, track
   width against current, sourcing. Measure them from the board read back with
   $pcb's `read_board` (positions, widths, nets, pads: its checks reference
   says how) and from the project BOM.
   [references/electrical.md](references/electrical.md) and
   [references/assembly.md](references/assembly.md) say what to measure and how
   to read each result.
3. **The checklist.** What no command measures: the fab's limits beyond the
   board's own rules, panel and edge details, polarity marks, placement
   rotations. Use the references below and a picture of the board, from
   $pcb's snapshot: `cadgen pcb snapshot board.kicad_pcb tmp/board.png`.

Each finding names its parts by board reference (`U2`, `C8`, `#net:VBUS`);
with $pcb's `python`, `read_board(path).resolve(ref)` answers where one is.

| Area | Reference | Measured by |
| --- | --- | --- |
| Fabrication | [references/fabrication.md](references/fabrication.md) | KiCad's DRC against the board's rules; the rest by inspection |
| Electrical | [references/electrical.md](references/electrical.md) | the board read back: decoupling distances, narrowest track per net |
| Assembly and sourcing | [references/assembly.md](references/assembly.md) | the part list and placement file, by inspection |

## Rule selection

1. Use the selected fab's own capability page for the board's layer count,
   copper weight and finish. The project's Board Setup and custom rules may differ from the fab's limits: compare them to the page.
2. Where the user names no fab, review against JLCPCB's standard service and
   say so.
3. Record the source, its date and the conditions (layers, copper, finish) with
   every limit you adopt. If it cannot be checked, report the missing rule
   rather than invent one.

A fab's standard tier is a price, not a physical limit: finer work is often
possible at a surcharge. Say which it is.

## Report

Return a concise Markdown report in chat or the user's requested file:

- Scope: board file and revision, fab and service, layers, copper, finish,
  assembled or bare.
- Findings, errors first: what and where (board references), evidence (the
  command or measurement), the rule and its source, result, and the fix.
- Coverage: checks run, and checks not run with what is needed to run them. No
  findings is not a manufacturability approval.

| Item | Evidence | Rule | Result | Fix |
| --- | --- | --- | --- | --- |
| `U2` pad 3 to `C8` | measured 3.67 mm centre to centre from the board read back | decoupling within 3 mm (this review's guide) | review | move `C8` beside pin 3 |

**pass** for a measured item within a cited limit; **fail** for a measured
violation or a KiCad error; **review** for a risk a person decides; **unverified**
where evidence or the fab's rule is missing. Keep cost suggestions (basic vs
extended parts, a cheaper finish) apart from manufacturing constraints.

## Fixing

A review request alone does not ask for edits or an order. When the user asks
for fixes:

Edit the native board and project rules with the PCB workflow, then rerun DRC and
measurements against the saved revision.

Recheck neighbours of every fix: a moved capacitor can open a clearance or
silkscreen finding elsewhere. Never order on the user's behalf.
