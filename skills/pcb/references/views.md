# Board and schematic views

Read this for what the person can see and pick on a board's or a schematic's page, when
a part's 3D model is missing, or when a snapshot needs a particular layer, side or window.

## Contents

- [The board view](#the-board-view)
- [3D and part models](#3d-and-part-models)
- [Board snapshots](#board-snapshots)
- [The schematic view](#the-schematic-view)
- [What the views approximate](#what-the-views-approximate)

## The board view

In the board's view, in 2D and in 3D, the person can pick, measure, draw on the board and send a
Quick Edit. Picking works as in KiCad: a part, pad, track, via, zone, rule area, text, dimension or
graphic, as KiCad's Selection Filter allows (locked items only when the person allows them), or
everything a box touches. A box that takes nothing names an area on the active layer
(`#F.Cu@x10y5..x20y15`). The person can also pick a schematic block the footprints record (by kind
on a board that records none), which picks every part in it, or a whole net. What the person picks
arrives as a reference ([checks](checks.md#references) says what each names and how to resolve it).

The person chooses how the board is drawn: which layers show and which is active (drawn on top), the
other layers shown, dimmed or hidden as in KiCad's high-contrast modes (the outline, drills and vias
through an active copper layer stay at full strength), the copper pours, the zones' and tracks'
opacity, the parts' 3D models, the side seen, 2D or 3D, and the display mode. That is the display,
so a Quick Edit's packet draws the same. The board follows the app's theme: KiCad's
colours on the dark canvas, the same colours darkened to read on the light one.

## 3D and part models

In 3D the board is a slab whose two faces are drawn as the 2D view draws them, each part standing
on its 3D model. A pick there takes what the 2D view would take at that point of the face, or the
part whose body is in front of it.

A part's model is the STEP its footprint names, looked for only in these folders, in this order:

1. the board's folder (`${KIPRJMOD}`, and a relative name),
2. the folders `CAD_KICAD_3DMODELS` names (separated as `PATH` is),
3. KiCad's installed 3D library.

A name under any `${KICADn_3DMODEL_DIR}` is read in 2 and 3, a relative name the board's folder lacks
too, and a `.wrl` name as the `.step` or `.stp` beside it. `CAD_KICAD_3DMODELS` is read from the
server's environment, so set it before the server starts (`cad server stop`, then `cad server start`
with it set); a STEP or GLB export reads it from the command's environment. Where it names a KiCad
installation's `3dmodels` folder, that installation's stock symbol and footprint libraries are the
ones a project's library tables resolve to; otherwise the newest installed KiCad's are.

A part without a model stands as a block, and the viewer tells the person why:
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
plan camera, layer visibility and saved ink; it has no lit 3D preview, pose or transparency.

## The schematic view

`cad viewer --json board.kicad_sch` opens a schematic a sheet at a time, and the person can pick,
measure, draw on it and send a Quick Edit as on a board. They move between sheets as in KiCad's
Hierarchy Navigator, into a sheet symbol and back up. Picking works as in KiCad: a symbol, pin,
wire, label, sheet, junction or no-connect, or everything a box touches. The person can also pick a
part or a whole net from any sheet; a part on another sheet shows that sheet.

Each pick arrives as a schematic reference (`#R1`, `#R1.2`, `#net:/MID`, `#sheet:/Power/`,
`#wire:<uuid>`; [schematic](schematic.md#references) says what each names). Each sheet is on KiCad's
default drawing sheet, as its schematic editor shows it, the title block filled from that sheet's own
(a project's own `.kicad_wks` is not drawn). ERC findings are not drawn: run `cad kicad_sch erc`. The
person can export KiCad's PDF, SVGs, netlist and BOM from the viewer.

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
