---
title: Circuit boards
description: Design KiCad schematics and boards with your agent, from parts and placement to routing, ERC, DRC, a pre-order review and fabrication files.
---

text-to-cad works on native KiCad files. A schematic (`.kicad_sch`) says what connects to what, and a board (`.kicad_pcb`) carries it out. Your agent reads and edits those files themselves, checks them with KiCad's own rule checks, and shows them in the CAD Viewer. You end up with a checked board, a review of it before you order, and the fabrication files a manufacturer asks for.

You can view a board or a schematic without KiCad installed. text-to-cad reads the files itself.

## What to ask

- "Design a schematic and a two-layer board for an ESP32 sensor node with a USB-C power input and a 3.3 V regulator."
- "Place the parts on this board so the decoupling capacitors sit next to the IC power pins, then route it."
- "Run ERC on the schematic and DRC on the board and fix what they report."
- "Review this board before I order it from JLCPCB, assembled."
- "Export Gerbers, drill files, a BOM and a placement file, and a STEP so I can fit an enclosure around it."

## What your agent does

1. Reads the existing project first: parts, nets, outline and constraints from the saved files. It edits the native `.kicad_pcb` and `.kicad_sch` in place and keeps the companion `.kicad_pro`, `.kicad_dru` and libraries. There is no separate text-to-cad board model.
2. Starts from the schematic. It checks each sheet with ERC (electrical rules check) and a snapshot:

   ```bash
   cad kicad_sch erc board.kicad_sch
   cad kicad_sch snapshot board.kicad_sch tmp/sheet.png --sheet /Power/
   ```

3. Checks parts and footprints against the datasheet: pad numbering, pitch, polarity, connector mating side.
4. Lays out the board from the schematic's netlist, one part or functional group at a time, with rules set from the fab's limits and each net's current. Edits are Python scripts that state the result they want ("U1 at (10, 20)"), so running one twice is harmless:

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

   The script runs with `cad run board.py`.
5. Checks after every step with DRC (design rule check) and pictures:

   ```bash
   cad kicad_pcb drc board.kicad_pcb
   cad kicad_pcb snapshot board.kicad_pcb tmp/placement.png --display placement
   ```

   DRC exits 1 on errors or unconnected items. Your agent reads the warnings too, because a fab's CAM engineer flags them.
6. Reviews the board before you order. It uses the fab's capability page for your layer count, copper weight and finish, or JLCPCB's standard service if you name no fab. It covers fabrication limits, electrical points such as decoupling distance and track width for current, and assembly and BOM sourcing. Each finding is marked pass, fail, review or unverified, and the report lists what was not checked.
7. Exports only the files you asked for, from the revision it checked:

   ```bash
   cad kicad_pcb export board.kicad_pcb --to gerbers -o fab/gerbers
   ```

   The `--to` kinds are `gerbers`, `drill`, `pos`, `bom`, `step`, `glb`, `odb`, `ipc2581`, `pdf` and `dxf`. A schematic exports `pdf`, `svg`, `netlist` and `bom` with `cad kicad_sch export`.

## What you need

- Nothing to install for reading, viewing or taking snapshots of a board or schematic, except that showing a board or taking its snapshot starts the download below.
- DRC, ERC, every export and every edit run KiCad's command line through the `kicad` integration (`cad[kicad]`). text-to-cad installs it the first time a board command needs it: about 100 MB to download and 340 MB on disk, once. It runs headless and never opens the KiCad app. A KiCad you installed yourself is never run.
- Edits start a local KiCad server on a socket. A sandbox that refuses sockets, as Codex's default does, stops the edit, and your agent has to run the script outside the sandbox. Checks, exports and snapshots run inside it.

## What you get

- Your project's own files, changed in place.
- Fabrication files in the folder you choose: Gerbers, Excellon drill files, a placement CSV, a BOM CSV, ODB++, IPC-2581, PDFs, and a DXF of the outline and holes. The BOM comes from the schematic, so changes go in its fields and the BOM is exported again.
- A STEP or GLB of the board and its parts, for enclosure design. A part without a 3D model is named in the result and left out. The GLB also holds copper, mask and silkscreen.
- In the CAD Viewer: a board in 2D and 3D with layers, selection, Measure and annotations, and a schematic one sheet at a time with a parts, nets and hierarchy panel. See [the CAD Viewer](/docs/guides/cad-viewer).

## Limits

- A clean DRC proves the board meets its own rules. It does not prove the circuit is right or that a fab can make the board. A review is a guided check, not a fab's engineering approval, and no findings is not a manufacturability approval.
- A fab's standard tier is a price, not a physical limit. The review records the source and conditions of every limit it uses.
- DRC or ERC errors block writing fabrication files unless you explicitly say to go ahead. The report then names every error you went ahead with.
- Snapshots and the viewer approximate mask and paste openings. KiCad's DRC and exports are authoritative, so look at the exported Gerbers in a Gerber viewer before ordering.
- A board or schematic that text-to-cad saves is in KiCad's nightly format (10.99), which a stable KiCad app refuses. The viewer's Open in says which KiCad on your computer can open the file.
- Your agent never places an order for you.

## Go deeper

- [The pcb skill](repo:skills/pcb/SKILL.md), with [schematic](repo:skills/pcb/references/schematic.md), [parts](repo:skills/pcb/references/parts.md), [layout](repo:skills/pcb/references/layout.md), [placement](repo:skills/pcb/references/placement.md), [checks](repo:skills/pcb/references/checks.md) and [manufacturing](repo:skills/pcb/references/manufacturing.md).
- The pre-order reviews: [fabrication](repo:skills/pcb/references/review-fabrication.md), [electrical](repo:skills/pcb/references/review-electrical.md) and [assembly](repo:skills/pcb/references/review-assembly.md).
- Document types [`kicad_pcb`](/docs/document-types/kicad_pcb) and [`kicad_sch`](/docs/document-types/kicad_sch), and [the KiCad integration](/docs/integrations/kicad).
- [Parts and assemblies](/docs/guides/parts-and-assemblies), for the enclosure you fit round the board's STEP.
