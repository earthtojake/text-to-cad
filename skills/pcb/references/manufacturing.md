# Fabrication and mechanical exports

Read this to write the files a fab, an assembler or an enclosure design takes from the saved board, and for
the fabs' standard limits.

## Exports

`cad kicad_pcb export BOARD --to KIND -o DIR` writes one kind a run from the saved board, which it never
changes (`--json` lists the files written). `kicad_pcb.export(board, to, out)` is the same in a script run
with `cad run` (its result's `written` and `warnings`).

| `--to` | Writes into DIR |
| --- | --- |
| `gerbers` | every plot layer the board's own plot settings choose, and a job file |
| `drill` | Excellon drill files, mm |
| `pos` | `<board>-pos.csv`: placement of both sides, mm, from KiCad's page origin with y up (`PosY` is the board's y negated), every placed part (DNP ones too): KiCad's columns `Ref`, `Val`, `Package`, `PosX`, `PosY`, `Rot`, `Side` |
| `bom` | `<board>-bom.csv` from the schematic beside the board (`<board>.kicad_sch`), grouped by value and footprint, DNP parts left out: `Reference` (every designator, no ranges), `Value`, `Footprint`, `Quantity`, then `MPN` and `LCSC` where any part carries one (read from fields named `MPN`, `Manufacturer_Part_Number`, `LCSC`, `LCSC Part`, ...) |
| `step`, `glb` | `<board>.step` / `<board>.glb`: the board and each part whose 3D model is found ([where it is looked for](views.md#3d-and-part-models)); a warning names the parts without one. The GLB holds the board's copper, mask and silkscreen too, each KiCad's own mesh named by its layer (`<board>_copper`, `_pad`, `_via`, `_silkscreen`, `_soldermask`, `_PCB`), so it is the larger and slower of the two (tens of MB on a four-layer board) |
| `odb` | `<board>-odb.zip`: ODB++, mm |
| `ipc2581` | `<board>-ipc2581.xml`: IPC-2581 rev C, mm |
| `pdf` | `<board>-front.pdf` and `<board>-back.pdf` (mirrored): copper, silkscreen and fab layers over the outline |
| `dxf` | `<board>-outline.dxf`: Edge.Cuts and every drilled hole, mm, for an enclosure |

KiCad writes a STEP or GLB through a temporary file of a fixed name in the output folder, so two such
exports into one folder at once can collide: give each a folder of its own.

For anything else (another origin, other layers, a placement file without the DNP parts), run KiCad's own
command line, `cad run kicad-cli ...`, as its [manual](https://docs.kicad.org/9.0/en/cli/cli.html) and
`--help` describe:

```bash
cad run kicad-cli pcb export step --force --subst-models --user-origin 0x0mm -o mechanical/board.step board.kicad_pcb
cad run kicad-cli pcb export pos --format csv --units mm --side both --exclude-dnp --use-drill-file-origin -o out/board-pos.csv board.kicad_pcb
```

Its STEP holds only the models KiCad itself finds, so check its parts against `cad kicad_pcb inspect
--json`'s `models`.

JLCPCB's assembly reads `Designator`, `Mid X`, `Mid Y`, `Layer` (`Top` or `Bottom`) and `Rotation` in
millimetres and degrees
([its placement file guide](https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly)): rename
KiCad's columns in a script, never by hand in the file.

Review the files the fab will receive, not the editor's view. Confirm the fab's required layers and drill
format, then open the exported Gerbers and drill files in a Gerber viewer (the fab's own upload preview, or
KiCad's GerbView) and look for shorts, vias that collide or land in pads, and missing layers (both masks,
both silkscreens, the outline, the drill).

## Standard-tier limits

From each fab's capability page, read 2026-11-04; recheck the page for anything near a limit.

| Limit | [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) 1–2 layers | JLCPCB 4 layers | [PCBWay](https://www.pcbway.com/capabilities.html) standard | [OSH Park](https://docs.oshpark.com/services/) 2 layers | OSH Park 4 layers |
| --- | --- | --- | --- | --- | --- |
| Track / space, 1 oz | 0.10 / 0.10 mm | 0.09 / 0.09 mm | 0.10 / 0.10 mm minimum | 0.152 / 0.152 mm (6 mil) | 0.127 / 0.127 mm (5 mil) |
| Smallest drill | 0.15 mm (0.1 mm costs more) | 0.15 mm | 0.2 mm (smaller costs more) | 0.254 mm (10 mil) | 0.254 mm |
| Via, hole / pad | 0.15 / 0.25 mm minimum; a 0.15 mm hole, or a 0.2–0.25 mm one on a pad under 0.45 mm, costs more | as 1–2 layers | (drill above) | (drill above) | (drill above) |
| Annular ring | 0.18 mm minimum, 0.25 mm advised (plated holes) | 0.15 mm minimum, 0.20 mm advised | 0.15 mm (vias) | 0.127 mm (5 mil) | 0.102 mm (4 mil) |
| Copper to a routed edge | 0.2 mm | 0.2 mm | 0.25 mm | not stated | not stated |
| Silkscreen text height / stroke | 1.0 / 0.15 mm | 1.0 / 0.15 mm | 0.8 / 0.15 mm | not stated | not stated |

Map each to the board's rules ([where they live](board-api.md#design-rules)): track and space to the
netclass's track width and clearance, the drill and via to the via size and hole, the ring to the minimum
annular width, the edge to the copper-to-edge clearance.

## STEP and mesh for an enclosure

The STEP's origin is KiCad's page origin unless you choose one (`cad run kicad-cli pcb export step` with
`--user-origin XxYmm`, `--grid-origin` or `--drill-origin`): record which. Its y is the board's y negated
(a board drawn from (0, 0) to (40, 30) spans y −30 to 0), and its board body is the substrate without
copper or mask (1.51 mm for a default 1.6 mm two-layer board). Measure the exported outline, holes and
thickness and a known connector location before designing against it. `--board-only` leaves the parts
out: say so when you use it.

The STEP is an ordinary CAD file, not the board's source. Show it as any file
([Show the model](../SKILL.md#show-the-model): `cad_show` where your tools include it, else its page
from `cad viewer`), convert it with `cad step export mechanical/board.step mechanical/board.glb` (or STL,
3MF) for a requested mesh, and read it into an enclosure model with `step.read`. Check geometry and
millimetre scale after a conversion. Export again after a board edit; never carry a change made to the
STEP back into the board by guessing at its meaning.
