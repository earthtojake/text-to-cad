---
title: Circuit boards
description: The pcb skill designs, checks and reviews native KiCad schematics and boards, and exports the fabrication files a manufacturer asks for.
---

The `pcb` skill works on native KiCad files. A schematic (`.kicad_sch`) says what connects to what, and a board (`.kicad_pcb`) carries it out. With it, your agent reads and edits those files, checks them with KiCad's own rule checks, reviews the board before you order, and exports the fabrication files.

There is no separate text-to-cad board model. The skill edits the native files in place and keeps the companion `.kicad_pro`, `.kicad_dru` and libraries.

## What it makes

- Your project's own files, changed in place.
- Fabrication files in the folder you choose: Gerbers, Excellon drill files, a placement CSV, a BOM CSV, ODB++, IPC-2581, PDFs, and a DXF of the outline and holes. The BOM comes from the schematic, so a change goes in its fields and the BOM is exported again.
- A STEP or GLB of the board and its parts, for enclosure design. A part without a 3D model is named in the result and left out. The GLB also holds copper, mask and silkscreen.
- A pre-order review of the board, with each finding marked pass, fail, review or unverified.

In the [viewer](/docs/viewer), a board shows in 2D and 3D with layers, selection, Measure and annotations, and a schematic shows one sheet at a time with a parts, nets and hierarchy panel.

## How it works

The work starts from the saved parts, nets, outline and constraints, and from the schematic. Each sheet is checked with ERC (electrical rules check, KiCad's check of a schematic) and a snapshot:

```bash
cad kicad_sch erc board.kicad_sch
cad kicad_sch snapshot board.kicad_sch tmp/sheet.png --sheet /Power/
```

Parts and footprints are checked against the datasheet: pad numbering, pitch, polarity, connector mating side.

The board is laid out from the schematic's netlist, one part or functional group at a time, with rules set from the fab's limits and each net's current. Edits are Python scripts, run with `cad run board.py`, that state the result they want ("U1 at (10, 20)"), so running one twice is harmless:

```python
from cad import kicad_pcb
from kicode.util.units import from_mm

with kicad_pcb.edit("board.kicad_pcb") as b:
    power = [t for t in b.get_tracks() if t.net.name in {"+5V", "+3V3"}]
    for track in power:
        track.width = from_mm(0.8)
    b.update_items(power)
    b.refill_zones()
```

Every step is followed by DRC (design rule check, KiCad's check of a board against its own rules) and a picture:

```bash
cad kicad_pcb drc board.kicad_pcb
cad kicad_pcb snapshot board.kicad_pcb tmp/placement.png --display placement
```

DRC exits 1 on errors or unconnected items. The warnings are read too, because a fab's CAM engineer flags them.

Before you order, the board is reviewed against the fab's capability page for your layer count, copper weight and finish, or JLCPCB's standard service if you name no fab. The review covers fabrication limits, electrical points such as decoupling distance and track width for current, and assembly and BOM sourcing. The report lists what was not checked.

Exports come from the revision that was checked, and only the files you asked for:

```bash
cad kicad_pcb export board.kicad_pcb --to gerbers -o fab/gerbers
```

The `--to` kinds are `gerbers`, `drill`, `pos`, `bom`, `step`, `glb`, `odb`, `ipc2581`, `pdf` and `dxf`. A schematic exports `pdf`, `svg`, `netlist` and `bom` with `cad kicad_sch export`.

## What it needs

- Nothing to install for reading, viewing or taking snapshots of a board or schematic: text-to-cad reads the files itself. Showing a board or taking its snapshot does start the download below.
- DRC, ERC, every export and every edit run KiCad's command line through the `kicad` integration (`cad[kicad]`), installed the first time a board command needs it: about 100 MB to download and 340 MB on disk, once. It runs headless and never opens the KiCad app. A KiCad you installed yourself is never run.
- Edits start a local KiCad server on a socket. A sandbox that refuses sockets, as Codex's default does, stops the edit, and the script has to run outside the sandbox. Checks, exports and snapshots run inside it.

## Ask for it

- "Design a schematic and a two-layer board for an ESP32 sensor node with a USB-C power input and a 3.3 V regulator."
- "Place the parts on this board so the decoupling capacitors sit next to the IC power pins, then route it."
- "Run ERC on the schematic and DRC on the board and fix what they report."
- "Review this board before I order it from JLCPCB, assembled."
- "Export Gerbers, drill files, a BOM and a placement file, and a STEP so I can fit an enclosure around it."

## Limits

- A clean DRC proves the board meets its own rules, not that the circuit is right or that a fab can make it. A review is a guided check, not a fab's engineering approval.
- A fab's standard tier is a price, not a physical limit. The review records the source and conditions of every limit it uses.
- DRC or ERC errors block writing fabrication files unless you explicitly say to go ahead. The report then names every error you went ahead with.
- Snapshots and the viewer approximate mask and paste openings. KiCad's DRC and exports are authoritative, so look at the exported Gerbers in a Gerber viewer before ordering.
- A board or schematic that text-to-cad saves is in KiCad's nightly format (10.99), which a stable KiCad app refuses. The viewer's Open in says which KiCad on your computer can open the file.
- Your agent never places an order for you.

## The skill

The skill is [`pcb`](repo:skills/pcb/SKILL.md). Its references:

- [Schematic](repo:skills/pcb/references/schematic.md), [parts](repo:skills/pcb/references/parts.md), [layout](repo:skills/pcb/references/layout.md) and [placement](repo:skills/pcb/references/placement.md)
- [Checks](repo:skills/pcb/references/checks.md) and [manufacturing](repo:skills/pcb/references/manufacturing.md)
- The pre-order reviews: [fabrication](repo:skills/pcb/references/review-fabrication.md), [electrical](repo:skills/pcb/references/review-electrical.md) and [assembly](repo:skills/pcb/references/review-assembly.md)

Related pages: the document types [`kicad_pcb`](/docs/document-types/kicad_pcb) and [`kicad_sch`](/docs/document-types/kicad_sch), [the KiCad integration](/docs/integrations/kicad), [the viewer](/docs/viewer), and [parts and assemblies](/docs/skills/parts-and-assemblies) for the enclosure you fit round the board's STEP.
