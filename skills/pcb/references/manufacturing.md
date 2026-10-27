# Fabrication and mechanical exports

Use the chosen manufacturer's current capability page for the specific layer count, copper
weight, finish and assembly service. Compare those limits with `.kicad_pro` and `.kicad_dru`;
DRC checks the project's rules, not a manufacturer's catalog. Record unresolved findings.

Run `cadgen pcb drc board.kicad_pcb --json` after saving and refilling zones. DRC reports include
violations and unconnected items, with severity and board positions. No report is cached and
the board source is not rewritten. KiCad may create a local `.kicad_prl` during file commands. An exit code of zero does not establish circuit correctness.

KiCad exports the same saved source. See its versioned
[CLI manual](https://docs.kicad.org/9.0/en/cli/cli.html) and the installed command's `--help`:

```bash
kicad-cli pcb export gerbers -o fabrication/ board.kicad_pcb
kicad-cli pcb export drill -o fabrication/ board.kicad_pcb
kicad-cli pcb export pos --format csv --units mm -o fabrication/placement.csv board.kicad_pcb
kicad-cli pcb export step --force --subst-models --user-origin 0x0mm -o mechanical/board.step board.kicad_pcb
```

Confirm the fab's required layers and drill format. Include the schematic/project BOM with
verified MPNs, quantities, DNP flags and assembler placement conventions. Inspect generated
Gerbers/drills; a 2D viewer approximation is not a manufacturing plot.

## STEP and mesh for an enclosure

Choose and record the STEP origin explicitly: `--user-origin XxYmm`, `--grid-origin`, or
`--drill-origin`. KiCad's board plane uses y down; STEP uses its mechanical frame. Measure the
exported outline, holes and thickness and a known connector location before designing against
it. Use `--board-only` only for a deliberately bare-board export and state that limitation.

The STEP is an ordinary foreign CAD file; it is not the PCB's source. View it with `cad_show`
or `cadgen viewer`, and use `cadgen export mechanical/board.step mechanical/board.glb` (or STL,
3MF) for requested meshes. A cadgen model can use `read_step` to fit an enclosure around it.
Check geometry and millimetre scale after conversion. Re-export after native board edits;
do not copy STEP changes back into the PCB by guessing at their meaning.
