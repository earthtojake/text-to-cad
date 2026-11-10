# Fabrication and mechanical exports

Use the chosen manufacturer's current capability page for the specific layer count, copper
weight, finish and assembly service. Compare those limits with `.kicad_pro` and `.kicad_dru`;
DRC checks the project's rules, not a manufacturer's catalog. Record unresolved findings.

Run `cad kicad_pcb drc board.kicad_pcb --json` after saving and refilling zones. DRC reports include
violations and unconnected items, with severity and board positions. No report is cached and
the board source is not rewritten. KiCad may create a local `.kicad_prl` during file commands. An exit code of zero does not establish circuit correctness.

KiCad exports the same saved source, with `cad kicad_pcb export BOARD --to KIND -o DIR` (kicode's
`kicad-cli`, headless; `--json` lists the files written). One kind a run:

| `--to` | Writes into DIR |
| --- | --- |
| `gerbers` | every plot layer the board's own plot settings choose, and a job file |
| `drill` | Excellon drill files, mm |
| `pos` | `<board>-pos.csv`: placement of both sides, mm, from KiCad's page origin, every placed part (DNP ones too): KiCad's columns `Ref`, `Val`, `Package`, `PosX`, `PosY`, `Rot`, `Side` |
| `bom` | `<board>-bom.csv` from the schematic beside the board (`<board>.kicad_sch`), grouped by value and footprint, DNP parts left out: `Reference` (every designator, no ranges), `Value`, `Footprint`, `Quantity`, then `MPN` and `LCSC` where any part carries one (read from fields named `MPN`, `Manufacturer_Part_Number`, `LCSC`, `LCSC Part`, ...) |
| `step`, `glb` | `<board>.step` / `<board>.glb`: the board and its parts, each part's STEP model read where the board view reads it (the board's folder, KiCad's installed 3D library, `CAD_KICAD_3DMODELS`; a `.wrl` name as the STEP beside it); parts without a model are named. The GLB holds the board's copper, mask and silkscreen too, each KiCad's own mesh named by its layer (`<board>_copper`, `_pad`, `_via`, `_silkscreen`, `_soldermask`, `_PCB`), so it is the larger and slower of the two (tens of MB on a four-layer board) |
| `odb` | `<board>-odb.zip`: ODB++, mm |
| `ipc2581` | `<board>-ipc2581.xml`: IPC-2581 rev C, mm |
| `pdf` | `<board>-front.pdf` and `<board>-back.pdf` (mirrored): copper, silkscreen and fab layers over the outline |
| `dxf` | `<board>-outline.dxf`: Edge.Cuts and every drilled hole, mm, for an enclosure |

`cad.kicad_pcb.export(board, to, out)` is the same in a script run with `cad run` whose header names
`cad[kicad]` (its result's `written` and `warnings`). For anything else (another origin, other layers), run KiCad's command line
itself, `cad run kicad-cli …`, as the [CLI manual](https://docs.kicad.org/9.0/en/cli/cli.html) and its
`--help` describe. It reads KiCad's 3D library as KiCad does (the first library folder; a `.wrl` name
only where its `.wrl` file is there), so check its parts against `cad kicad_pcb inspect --json`'s `models`:

```bash
cad run kicad-cli pcb export step --force --subst-models --user-origin 0x0mm -o mechanical/board.step board.kicad_pcb
```

Confirm the fab's required layers and drill format. Include the BOM with verified MPNs,
quantities, DNP flags and assembler placement conventions.

Review the files the fab will receive, not the editor's view: open the exported Gerbers and drill
files in a Gerber viewer (the fab's own upload preview, or KiCad's GerbView) and look for shorts,
vias that collide or land in pads, and missing layers (both masks, both silkscreens, the outline, the
drill). The board view and its snapshots approximate those layers; they are not a manufacturing plot.

A placement file without the DNP parts, or from the drill/place origin, is KiCad's command line run
yourself: `cad run kicad-cli pcb export pos --format csv --units mm --side both --exclude-dnp
--use-drill-file-origin -o out/board-pos.csv board.kicad_pcb`. JLCPCB's assembly reads `Designator`,
`Mid X`, `Mid Y`, `Layer` (`Top` or `Bottom`) and `Rotation` in millimetres and degrees
([its placement file guide](https://jlcpcb.com/help/article/pick-place-file-for-pcb-assembly)):
rename KiCad's columns in a script, never by hand in the file, and check the rotations in the order
page's preview.

## Standard-tier limits

From each fab's capability page, read 2026-11-04; recheck the page for anything near a limit. The
standard tier is a price, not a physical limit: finer work is often made at a surcharge.

| Limit | [JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities) 1–2 layers | JLCPCB 4 layers | [PCBWay](https://www.pcbway.com/capabilities.html) standard | [OSH Park](https://docs.oshpark.com/services/) 2 layers | OSH Park 4 layers |
| --- | --- | --- | --- | --- | --- |
| Track / space, 1 oz | 0.10 / 0.10 mm | 0.09 / 0.09 mm | 0.10 / 0.10 mm minimum | 0.152 / 0.152 mm (6 mil) | 0.127 / 0.127 mm (5 mil) |
| Smallest drill | 0.15 mm (0.1 mm costs more) | 0.15 mm | 0.2 mm (smaller costs more) | 0.254 mm (10 mil) | 0.254 mm |
| Via, hole / pad | 0.15 / 0.25 mm minimum; a 0.15 mm hole, or a 0.2–0.25 mm one on a pad under 0.45 mm, costs more | as 1–2 layers | (drill above) | (drill above) | (drill above) |
| Annular ring | 0.18 mm minimum, 0.25 mm advised (plated holes) | 0.15 mm minimum, 0.20 mm advised | 0.15 mm (vias) | 0.127 mm (5 mil) | 0.102 mm (4 mil) |
| Copper to a routed edge | 0.2 mm | 0.2 mm | 0.25 mm | not stated | not stated |
| Silkscreen text height / stroke | 1.0 / 0.15 mm | 1.0 / 0.15 mm | 0.8 / 0.15 mm | not stated | not stated |

Map each to the board's rules: track and space to the netclass's track width and clearance, the drill
and via to the via size and hole, the ring to Board Setup's minimum annular width, the edge to its
copper-to-edge clearance.

## STEP and mesh for an enclosure

Choose and record the STEP origin explicitly: `--user-origin XxYmm`, `--grid-origin`, or
`--drill-origin`. KiCad's board plane uses y down; STEP uses its mechanical frame. Measure the
exported outline, holes and thickness and a known connector location before designing against
it. Use `--board-only` only for a deliberately bare-board export and state that limitation.

The STEP is an ordinary foreign CAD file; it is not the PCB's source. View it with `cad_show`
or `cad viewer`, and use `cad step export mechanical/board.step mechanical/board.glb` (or STL,
3MF) for requested meshes. A text-to-cad model can use `step.read` to fit an enclosure around it.
Check geometry and millimetre scale after conversion. Re-export after native board edits;
do not copy STEP changes back into the PCB by guessing at their meaning.
