---
title: KiCad PCB
description: A KiCad printed circuit board file, which text-to-cad reads, checks, draws and edits in place.
---

A `.kicad_pcb` is a KiCad printed circuit board: its outline, layers, footprints, pads, nets, tracks, vias, zones and design rules. KiCad is the open source electronics design suite. text-to-cad reads it together with the `.kicad_pro` project file beside it.

## Where you meet it

A board is source, not a build product. No model script builds it. Your agent edits the file in place, through KiCad's own API, or you hand it a board you already have. It is never turned into a CAD model and written back.

The usual loop is: change the board, check it, look at it. Inspecting a board needs no KiCad. Showing a board or taking its snapshot does need it, to refill the copper pours on a copy before drawing. KiCad's design rule check (DRC) and the fabrication and 3D exports also run KiCad's command line. text-to-cad installs KiCad's command line the first time a board command needs it.

## Example

An edit is a `with` block. It saves at the end only if the block changed something:

```python
from cad import kicad_pcb
from kicode.util.units import from_mm

with kicad_pcb.edit("board.kicad_pcb") as b:
    power = [t for t in b.get_tracks() if t.net.name in {"+5V", "+3V3"}]
    for track in power:
        track.width = from_mm(0.8)
    b.update_items(power)
```

Then check and export:

```bash
cad kicad_pcb drc board.kicad_pcb
cad kicad_pcb snapshot board.kicad_pcb tmp/copper.png --display copper
cad kicad_pcb export board.kicad_pcb --to gerbers -o fab/gerbers
```

Run the script with `cad run`. It gives the script the [KiCad](/docs/integrations/kicad) integration.

## Related

[Circuit boards](/docs/skills/circuit-boards) covers the whole flow. See the [pcb skill](repo:skills/pcb/SKILL.md) and its [native files reference](repo:skills/pcb/references/board-api.md).
