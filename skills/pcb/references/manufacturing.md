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
| `pos` | `<board>-pos.csv`: placement of both sides, mm |
| `bom` | `<board>-bom.csv` from the schematic beside the board (`<board>.kicad_sch`), grouped by value and footprint, DNP parts left out: `Reference` (every designator, no ranges), `Value`, `Footprint`, `Quantity`, then `MPN` and `LCSC` where any part carries one (read from fields named `MPN`, `Manufacturer_Part_Number`, `LCSC`, `LCSC Part`, ...) |
| `step`, `glb` | `<board>.step` / `<board>.glb`: the board and its parts, STEP models in place of VRML ones; parts without a model are named |
| `odb` | `<board>-odb.zip`: ODB++, mm |
| `ipc2581` | `<board>-ipc2581.xml`: IPC-2581 rev C, mm |
| `pdf` | `<board>-front.pdf` and `<board>-back.pdf` (mirrored): copper, silkscreen and fab layers over the outline |
| `dxf` | `<board>-outline.dxf`: Edge.Cuts and every drilled hole, mm, for an enclosure |

`cad.kicad_pcb.export(board, to, out)` is the same in a script run with `cad run` whose header names
`cad[kicad]` (its result's `written` and `warnings`). For anything else (another origin, other layers), run KiCad's command line
itself: `kicode.executable()` with `kicode.environment(root)`, as the
[CLI manual](https://docs.kicad.org/9.0/en/cli/cli.html) and its `--help` describe:

```bash
kicad-cli pcb export step --force --subst-models --user-origin 0x0mm -o mechanical/board.step board.kicad_pcb
```

Confirm the fab's required layers and drill format. Include the BOM with verified MPNs,
quantities, DNP flags and assembler placement conventions. Inspect generated Gerbers/drills; a 2D
viewer approximation is not a manufacturing plot.

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
