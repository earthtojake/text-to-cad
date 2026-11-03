# The plot payload (schema 4)

`GET /api/v1/documents/kicad_pcb/<id>/plot` (the board opened by its absolute path) and `cad <type> snapshot` draw a KiCad board from
one payload, built by `cad.engine.formats.kicad.plot` from the `.kicad_pcb` and drawn by
`@cad/core/lib/plot2d` on a 2D canvas. Its pours are KiCad's refill of them, not the fills the file
saved, which go stale: KiCad refills the zones of a temporary copy of the board (kicode's headless
api-server, in the environment of `cad[kicad]`) and the plot is drawn from the copy's bytes, under the
board's own name and project (`cad.engine.formats.kicad.poured`, the one function the page and the
snapshot share); the person's file is never written. The payload is geometry per layer; what
colour a layer is drawn in is the renderer's (`plot2d/theme.js`, KiCad's default theme). It is a
function of the board's, its project's and its rules' bytes (and the plotting code): the engine keeps
it by a sha256 of them (`poured.key`; in memory, and gzipped under `<cache>/kicad/<key>/`), so a changed
file is a new key and nothing stale is served. The route answers 202 `{"state": "plotting", "retryMs"}`
while it is made (the client asks again), `etag: "<key>"` with every 200 and 304 to a request naming it,
`cache-control: no-store` as every engine answer, and the body zstd- or gzip-coded for a browser that
accepts it. `schemaVersion` is `cad.engine.formats.kicad.PLOT_SCHEMA_VERSION` = `plot2d.PLOT_SCHEMA_VERSION`;
a mismatch is refused by name on both sides.

The picture is KiCad's PCB editor's with the display it opens a board with: every layer shown, the
front copper the active layer, KiCad's drawing order for that (`pcbnew/pcb_draw_panel_gal.cpp`), its
colours, zones at its 60% opacity, a plated hole seen through to the board's background, a pad's
number and net name over it, and the board on its page, KiCad's drawing sheet round it.

```jsonc
{
  "schemaVersion": 4,
  "kind": "board",                 // words only: what the payload draws
  "generator": "pcbnew 10.99",     // what wrote the file, for words
  "unrouted": 1,                   // connections still to make: the ratsnest's lines
  "sheets": [{
    "name": "blinky", "width": 40.0, "height": 30.0, "background": "#001023",
    "page": [0.0, 0.0, 297.0, 210.0],  // the paper KiCad draws the board on, in sheet millimetres
    "layers": [ { "id": "sheet", "kind": "sheet", "side": "both", "items": [ ... ] }, ... ]
  }],
  "board": { ... },                // the board's index, in sheet millimetres
  "pours": { "refilled": true }    // KiCad refilled them; else { "refilled": false, "warning": "why" }: as saved
}
```

## The DRC beside it

`GET /api/v1/documents/kicad_pcb/<id>/drc` is KiCad's design rule check of the saved board, kept by the
same key and made off the request the same way (202 `{"state": "checking", "retryMs"}` while it runs):
the `CheckResult` `cad kicad_pcb check --json` prints, as data.

```jsonc
{
  "ok": false, "path": "/boards/blinky.kicad_pcb", "summary": "",
  "findings": [ { "severity": "error", "code": "unconnected_items", "message": "...", "location": "(20, 23.175) mm", "hint": null } ],
  "measurements": { "drc": [ {
    "check": "unconnected",          // violation, unconnected or parity
    "severity": "error", "type": "unconnected_items", "description": "Missing connection between items",
    "at": [20.0, 23.175],            // the first item's position: millimetres in KiCad's frame, y down
    "items": [ { "uuid": "...", "description": "Pad 2 [LED] of D1 on F.Cu", "pos": [20.0, 23.175],
                 "ref": "#D1.2" } ]   // the board reference it names, where the index has one
  } ] }
}
```

## The sheet

One sheet, in millimetres, y DOWN: KiCad's own frame moved so the board's outline (`Edge.Cuts`)
has its top-left corner at (0, 0); `width` and `height` are the outline's box. A board with no
outline is framed on everything it draws, 1 mm around. Every coordinate is rounded to four
decimals. The sheet is what the renderer frames; the whole canvas is its background, KiCad's. It
clips nothing: an item past the outline — a fab note off the edge, as KiCad draws one, the drawing
sheet — is drawn where it falls (`layoutPlot`'s `extent` is the box of everything drawn). `page` is
the paper's box (`(paper "A4")`, `(paper "User" w h)`, portrait turned): KiCad's page origin is its
top-left corner.

## The layers

Bottom to top, as KiCad draws them with the front copper active: `sheet` (the drawing sheet),
`area` (the board's area), the back side (`B.Fab`, `B.CrtYd`, `B.Adhes`, `B.Paste`, `B.SilkS`,
`B.Mask`, `B.Cu`), the inner coppers deepest first (`In4.Cu` … `In1.Cu`), the user layers and the
outline (`User.N` … `User.1`, `Margin`, `Edge.Cuts`, `Eco2.User`, `Eco1.User`, `Cmts.User`,
`Dwgs.User`), the front side in the back's order (`F.Fab` … `F.Mask`, `F.Cu`), then four layers of
what goes through the board: `drills` (pads' and unplated holes), `vias` (vias' holes), `ratsnest`,
and `names` (the numbers and nets of the pads through the board, and the vias' nets). A layer the
board declares but draws nothing on is left out, except the copper layers, which are always present
so a view can name them, and `names` while anything is named.

Within a copper layer the items stand in KiCad's order too: the pours' fills, then the tracks,
graphics and pour outlines, the via rings, the pads, then the names written on that copper (a
surface pad's).

| field | meaning |
| --- | --- |
| `id` | KiCad's layer name, or `sheet`, `area`, `drills`, `vias`, `ratsnest`, `names` |
| `kind` | `sheet`, `area`, `copper`, `silk`, `fab`, `courtyard`, `mask`, `paste`, `adhesive`, `user`, `margin`, `outline`, `drill`, `via`, `ratsnest`, `names` |
| `side` | `front` (`F.*`), `back` (`B.*`) or `both` (inner copper, the outline, the user layers, the page and the board's area, and what goes through the board) |
| `items` | what the layer draws, bottom to top |

A view (`plot2d.drawPlot`'s `view`) chooses layers by id and orders them: without one, every layer
(KiCad's default); seen from below, the board's stack reverses while `sheet` and `area` stay under
it and the `drill`, `via`, `ratsnest` and `names` kinds stay on top, each layer mirrored about the
sheet's vertical centre line — the drawing sheet's page moved where the mirrored board lies and
read the right way round, as KiCad draws its title block in a flipped view. A via's copper is drawn
while `vias` is, and a name while `names` is, so a view hides a via, or every name, as one. The
board's Display (`plot2d/boardDisplay.js`: `{ mode, side, poured, layers }`, the viewer's and
`cad <type> snapshot --display`'s one contract) is a view over these ids: a mode is a set of layer
kinds, `layers` an explicit set of ids (one that differs from its mode's reads as Custom), `poured`
and `side` switches of their own. What is drawn ON the board — an annotation's ink, Measure's ends
— is kept in sheet millimetres, so it stays on what it marks from either side; the view's plan is
the sheet with y negated, mirrored about its middle from below (`plot2d/boardView.js`), the frame a
Quick Edit's plan-view camera speaks.

## The items

Each item has `t`, its type; every point is sheet millimetres.

| `t` | fields | draws |
| --- | --- | --- |
| `poly` | `pts` (3+ vertices), optional `w`, optional `holes` (rings of 3+ points) | a filled polygon, its holes left open, its outline also stroked `w` wide when `w` > 0 (a mask opening grown by its margin, a graphic drawn with a pen) |
| `path` | `pts` (2+ points), `w`, optional `closed`, optional `pairs` | a stroked polyline, round caps and joins; with `pairs`, separate segments, the points taken two by two; `w` 0 is a hairline (one CSS pixel at any zoom) |
| `circle` | `at`, `r`, `w` | a filled disc (`w` 0) or a ring `w` wide centred on `r` |
| `text` | `text`, `w`, `strokes` (polylines of 2+ points), optional `knockout` | the string's strokes, `w` wide; knocked out (`knockout`: the four corners of its box), the box filled and the letters cut from it |
| `label` | `kind` (`pad`, `via`), `text`, `at`, `size` (height, width), `angle`, `w`, `lod` | a name the renderer lays out in the stroke font (`plot2d/strokeFont.js`, the engine's `stroke_font` point for point), centred on `at`, `angle` degrees counter-clockwise, its strokes `w` wide; drawn once the view shows `lod` CSS pixels per millimetre, and from below laid out to read the right way round |

Flags any item may carry: `ref`, the board reference of what drew it (`#R1` for a footprint's
graphics and text, `#R1.2` for a pad and its mask and paste); `net`, the net of a piece of copper;
`pour: true`, a zone's fill, which a view with `poured: false` leaves out and which is drawn at
KiCad's zone opacity, and `teardrop: true` on a teardrop's, drawn opaque as KiCad draws teardrops;
`via` (`through`, `blind`, `micro`) on a via's copper and its hole; `hole` (`pad`, `via`, `npth`) on
a hole, whose `w` is then its plated wall's width and `span` (a blind or buried via's) its top and
bottom copper; `clearance` on a front-copper pad; `page` on the page's own edge. A graphic (`gr_*`,
`fp_*`) carries `id`, the uuid KiCad saved it with (`<footprint uuid>/<uuid>` where copies of a
footprint share its items' uuids), which the viewer picks it by (`#shape:<id>`), and `shape` when it
is not a line (`rect`, `circle`, `arc`, `poly`, `curve`): what the board index would otherwise repeat
of every graphic is drawn here once.

What each thing becomes:

- **Pads** are their padstack's outline (rect, roundrect, oval, circle, trapezoid, chamfered,
  custom: the hull of its primitives) as a `poly` on every copper layer they flash on, with `ref`
  and `net`: a pad through the board whose unused copper is removed keeps it on the outer layers
  (when it keeps its end layers), where a zone connects it (`zone_layer_connections`) and where a
  track ends on it, as KiCad's `FlashLayer` decides. A front-copper pad carries its `clearance` (its
  own, its footprint's, else its net class's): KiCad outlines it there, a hairline that far out. A
  pad's number and net name are `label`s fitted to it as KiCad fits them (`pcb_painter.cpp`): the
  number above the net, centred, turned to read upwards on a pad taller than wide, `x` for a
  no-connect pin and `*` for a free one; a surface pad's on its copper (in that copper's name
  colour), a through pad's on `names`. A through-hole pad's hole is a `circle` (a slot, a `poly`) on
  `drills`, `hole: "pad"`, its wall 30 µm (KiCad's 20 µm of plating, painted 1.5 times); an
  unplated hole `hole: "npth"`, with copper only where its pad is larger than the hole.
- **Tracks and arcs** are `path`s of their width on their layer, with `net`; an arc is sampled.
  A track's net name is not in the payload: where KiCad writes it (`renderNetNameForSegment`)
  depends on the size of the view, so the renderer lays it out from the track as it draws it
  (`plot2d/trackNames.js`; the engine's `labels.py` `track_labels`, by the same rule): the short
  net name, 0.55 of the width tall, along the track at its middle (one per view a long segment
  spans), once the view shows 4 mm over its width at KiCad's zoom 1, on top of its copper.
- **Vias** are a ring on each copper layer they flash on (`circle`, `w` the annular width, `via`
  and `net`; the same unused-copper rules as a pad's), their hole on `vias` (`hole: "via"`, golden in
  a white wall; a blind or buried via's hole the two colours of its end layers), and their net (a
  blind via's layer pair too, `2-3`) a `label` on `names`. A via that names no drill (KiCad 5) takes
  its net class's.
- **Pours** are the fills KiCad saved, `poly` with `pour: true` and `net`, and their drawn outline
  as a closed hairline `path` with KiCad's border hatch (`pairs`: an edge hatch's short strokes or a
  full hatch's lines, every pitch). A teardrop has no outline. A rule area (keepout) is its outline
  and hatch on every layer it keeps out of, and no fill. The author must refill changed zones in
  KiCad and save them; the reader does not repair stale fills.
- **Graphics** (`gr_*`, `fp_*`: lines, rectangles, circles, arcs, polygons, curves) are `path`s of
  their stroke width, or a `poly` with that width when filled; a footprint's carry `ref`.
- **Dimensions** (aligned, orthogonal, leader, centre, radial, and KiCad 5's) are the lines KiCad
  builds for them (`pcb_dimension.cpp`: extension lines, crossbar, arrowheads, leader), `path`s of
  the dimension's line width, its crossbar stopped at its text's box, and the text KiCad last wrote
  for it where it wrote it.
- **Text** (footprint fields and `fp_text` that are not hidden, `gr_text`) is its strokes in Hershey
  Simplex (`cad.engine.formats.kicad.stroke_font`: public domain; KiCad's own font is GPL) at KiCad's
  position, size, thickness, angle, justification, mirroring and slant; a footprint's kept upright
  unless unlocked, as KiCad keeps it. `${REFERENCE}`, `${VALUE}`, a footprint's fields and the
  title block's variables are substituted, and KiCad 5's `%R` and `%V`. Same places, different glyphs.
- **Mask** openings and **paste** are derived from the pads: a pad's outline grown by its mask
  margin (the pad's, its footprint's, else the board's `pad_to_mask_clearance`), as a `poly`
  with `w` = twice the margin; a pad's outline for paste, grown by a positive paste margin or
  scaled in by a negative one. Close to KiCad's plotter, not its offsets.
- **The ratsnest** is the engine's connectivity over the copper (`cad.engine.formats.kicad.connectivity`): per net,
  the pieces of copper that touch on a shared layer form a cluster, and the clusters that hold a
  pad are joined by their shortest tree, one hairline `path` per line between the nearest pads.
  No DRC, no clearance: touching copper is joined.
- **The board's area** is a `poly` on `area`: the outline's largest closed loop, the loops inside it
  (cutouts) its `holes`, drawn in KiCad's board-area shadow.
- **The drawing sheet** is KiCad's default one (`cad.engine.formats.kicad.drawing_sheet`), on `sheet`:
  the page's grey edge (`page`), the frame 10 mm in and the one 2 mm inside it, the grid references
  every 50 mm, and the title block (title, date, revision, company, comments, the file's name and
  the paper's) as `path`s and `text`. A project's own drawing sheet file is not read.

Not drawn: text boxes, tables, images, barcodes, targets, points, locked-item shadows, and the
clearance outlines of tracks.

## The board index

`board` is `cad.engine.formats.kicad.board_index.BoardIndex.as_json()` in sheet millimetres: `parts` (ref,
value, footprint, side, `at`, `rotation`, `fields`, `dnp`, `outline`), `pads` (part, number, name,
net, type, side, `at`, `polygon`, `drill`), `tracks` (net, layer, width, `points`, `arc` for an arc),
`vias` (net, `at`, diameter, drill, the two `layers` it joins, `type`: `through`, `blind`, `buried`,
`micro`), `zones` (net, layer, `outline`, `name`, `priority`, `filled`: the mm² of copper KiCad filled
that layer with; a zone on several layers is one entry per layer, alike but for its layer), `holes`,
`outline` (Edge.Cuts chained into polylines), `nets` (name, class), `texts` (a board's text and each
footprint's shown fields and `fp_text`: `text` as drawn, layer, `at`, `angle`, `size` (the letters'
height), `polygon` (the box its letters fill), `part`) and `dimensions` (`type`, layer, `value`: the
text KiCad shows for it, `lines`: what it is drawn from, `polygon`: its value's box, `part`). Tracks,
vias, zones, texts and dimensions carry `id`, the uuid KiCad saved them with, as graphics do: what a
pick names them by (`#track:<id>`, `#via:`, `#zone:`, `#text:`, `#dimension:`). `origin` is where KiCad's
page origin (0, 0) lies on the sheet, so the viewer's index (`board2d/boardIndex.js`) reads every
position and every reference (`#net:VBUS@x40.1y21.6`, `#@x3.5y3.5`, `#F.Cu@x1y2..x3y4`) back in
KiCad's own frame, millimetres, y down: a point the viewer copies pastes straight into a script's
`Vector2.from_xy_mm`.
