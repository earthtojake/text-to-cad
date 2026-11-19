# Board and schematic views

Read this when the person asks how to do something in the CAD Viewer's board or schematic page, when
a part's 3D model is missing, or when a snapshot needs a particular layer, side or window.

## Contents

- [The board view](#the-board-view)
- [3D and part models](#3d-and-part-models)
- [Board snapshots](#board-snapshots)
- [The schematic view](#the-schematic-view)
- [What the views approximate](#what-the-views-approximate)

## The board view

The board view has layers, selection, Measure, annotations and Quick Edit, in 2D and in 3D. Select
works as KiCad's: a click picks a part, pad, track, via, zone, rule area, text, dimension or graphic,
as its Selection Filter ticks them (locked items only when ticked), and a drag draws a box that takes
anything it touches. A box that takes nothing names an area on the active layer
(`#F.Cu@x10y5..x20y15`). What the person picks arrives as a reference
([checks](checks.md#references) says what each names and how to resolve it).

The panel at the left (Cmd+\ or Ctrl+\ hides it, / searches it) has one search over three tabs:

- **Parts**: the parts in the schematic blocks their footprints record (by kind on a board that
  records none). A block picks every part in it.
- **Nets**: a net picks the whole net.
- **Layers**: each layer's eye, and a press for the active layer (drawn on top). Under them, how the
  board is drawn: Other layers (KiCad's high-contrast modes, **Shown**, **Dimmed** or **Hidden**,
  Ctrl+H cycling them; the outline, drills and vias through an active copper layer stay at full
  strength), the copper pours, the zones' and tracks' opacity, and **3D models**.

Under the tabs are the picked part's or net's pads. The tool strip ends with **Flip** (the side seen,
Shift+F), **2D/3D** and **Display** (the preset); the zoom is the pill at the bottom-right. These are
the display, so a Quick Edit's packet draws the same. The board follows the app's theme: KiCad's
colours on the dark canvas, the same colours darkened to read on the light one.

## 3D and part models

In 3D (**2D/3D**, or the key 3) the board is a slab whose two faces are drawn as the 2D view draws
them, each part standing on its 3D model. A press picks what the 2D view picks where the pointer's
ray meets the face, or the part whose body is in front of it; a drag turns the view; **Flip** turns
the camera over.

A part's model is the STEP its footprint names, looked for only in:

1. the board's folder (`${KIPRJMOD}`),
2. KiCad's installed 3D library (every `${KICADn_3DMODEL_DIR}`),
3. the folders `CAD_KICAD_3DMODELS` names (separated as `PATH` is).

A `.wrl` name is read as the `.step` or `.stp` beside it. `CAD_KICAD_3DMODELS` is read from the
server's environment, so set it before the server starts (`cad server stop`, then `cad server start`
with it set); a STEP or GLB export reads it from the command's environment. Where it names a KiCad
installation's `3dmodels` folder, that installation's stock symbol and footprint libraries are the
ones a project's library tables resolve to; otherwise the newest installed KiCad's are.

A part without a model stands as a block, and **Parts** lists it under **No 3D model** with why:
VRML only, not found, outside the folders above, too large, not a STEP, embedded in the board, or
too many models. `cad kicad_pcb inspect board.kicad_pcb --json` reports each model the same way
(`models`), and a STEP or GLB export (`cad kicad_pcb export --to step|glb`, `kicad_pcb.export`) holds
exactly the models found. `cad run kicad-cli` reads KiCad's library as KiCad does, where a `.wrl`
name needs its `.wrl` file (KiCad 10's library ships STEP alone), so prefer the typed export.

## Board snapshots

`cad kicad_pcb snapshot` draws a still, always on the light canvas whatever the viewer's theme.
Display modes are `board`, `copper`, `assembly` and `placement`, or JSON for the layers, the side and
the active layer:

```bash
cad kicad_pcb snapshot board.kicad_pcb tmp/copper.png --display copper
cad kicad_pcb snapshot board.kicad_pcb tmp/bottom.png --display '{"mode":"copper","side":"bottom","poured":false}'
cad kicad_pcb snapshot board.kicad_pcb tmp/front.png --display '{"layers":["F.Cu","Edge.Cuts"]}'
cad kicad_pcb snapshot board.kicad_pcb tmp/inner.png --display '{"active":"In1.Cu","others":"dimmed","zones":0.3}'
cad kicad_pcb snapshot board.kicad_pcb tmp/front-only.png --display '{"active":"F.Cu","others":"hidden"}'
cad kicad_pcb snapshot board.kicad_pcb tmp/u1.png --window 108,42,132,66 --width 1600
```

`--window X0,Y0,X1,Y1` draws only that box of the board, filling the picture: two opposite corners in
KiCad's millimetres (y down, the box `board.area(x0, y0, x1, y1)` names), as close as a fan-out or a
finding needs (`--window=-10,5,20,30` when the first is negative). With `--width` alone the height
follows the box's shape. It goes with any display and takes no `--camera`. `--job` draws a packet
Quick Edit saved. Bottom views mirror the board and its annotations. A 2D snapshot has the board's
plan camera, layer visibility and saved ink; it has no 3D Preview, pose or transparency.

## The schematic view

`cad viewer --json board.kicad_sch` opens a schematic a sheet at a time, with the board view's
selection, Measure, annotations and Quick Edit. Its panel has one search over **Parts** (by the sheet
they are placed on, each with its pins), **Nets** (with the pins on them) and, for more than one
sheet, the **Hierarchy**, KiCad's Hierarchy Navigator: a press shows that sheet, and a double-click on
a sheet symbol enters it. A net picked there lights across the sheet shown, and a part on another
sheet shows that sheet. Select works as KiCad's: a click picks a symbol, pin, wire, label, sheet,
junction or no-connect, and a drag draws a box.

Each pick arrives as a schematic reference (`#R1`, `#R1.2`, `#net:/MID`, `#sheet:/Power/`,
`#wire:<uuid>`; [schematic](schematic.md#references) says what each names). Each sheet is on KiCad's
default drawing sheet, as its schematic editor shows it, the title block filled from that sheet's own
(a project's own `.kicad_wks` is not drawn). ERC findings are not drawn: run `cad kicad_sch erc`. The
file menu's Export offers KiCad's PDF, SVGs, netlist and BOM.

A still is always on KiCad's light paper. A Quick Edit packet carries the sheet the view showed, on
the whole drawing sheet (`border`); `"title": false` leaves the title block out:

```bash
cad kicad_sch snapshot board.kicad_sch tmp/power.png --display '{"sheet":"/Power/","border":true}'
cad kicad_sch snapshot board.kicad_sch tmp/power-plain.png --sheet /Power/ --display '{"title":false}'
```

## What the views approximate

The viewer and snapshots draw the board as KiCad's PCB editor shows it: front copper active, pours at
60%, pad numbers and net names on pads, vias and tracks, dimensions, no drawing sheet. Mask and paste
openings are approximate, lettering is stroke lettering, and KiCad's text markup (`~{RESET}`,
`IO_{3}`, `x^{2}`) is drawn as KiCad draws it; text boxes, tables and embedded images are not drawn.
KiCad's DRC and manufacturing exports stay authoritative for fabrication, and an enclosure is
designed against KiCad's STEP export, never a solid inferred from the 2D plot.
