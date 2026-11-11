---
title: KiCad schematic
description: A KiCad schematic file, read with every sheet of its project, which text-to-cad checks, draws and edits in place.
---

A `.kicad_sch` is a KiCad schematic: the symbols, pins, wires, buses, labels and nets that say what connects to what on a board. A project can have a hierarchy of sheets, and text-to-cad reads all of them from whichever sheet you give it.

## Where you meet it

A schematic comes before the board. Your agent reads it to learn the connections, checks it, and then lays the board out to match. Like a [KiCad PCB](/docs/document-types/kicad_pcb), it is source: nothing builds it from a model, and your agent changes it in place through KiCad's API, or you provide one you already have.

Inspecting a schematic and drawing a snapshot of a sheet need no KiCad. KiCad's electrical rules check (ERC) and its exports (a PDF, an SVG per sheet, the netlist or a bill of materials) run KiCad's command line, installed on first need.

## Example

```bash
cad kicad_sch inspect board.kicad_sch
cad kicad_sch snapshot board.kicad_sch tmp/power.png --sheet /Power/
cad kicad_sch erc board.kicad_sch
cad kicad_sch export board.kicad_sch --to netlist -o tmp
```

To change one, use an edit in a script run with `cad run`. A second run should change nothing, so it places a symbol only when its reference is not there yet:

```python
from cad import kicad_sch

with kicad_sch.edit("board.kicad_sch") as s:
    ...  # place symbols and wires through KiCad's API
```

## Related

[Circuit boards](/docs/skills/circuit-boards) covers the flow from schematic to board, and the [KiCad](/docs/integrations/kicad) integration page says what runs on your computer. The [schematic reference](repo:skills/pcb/references/schematic.md) has the details.
