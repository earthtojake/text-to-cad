# The plot payload (schema 3)

`GET /__cad/plot?file=<absolute .kicad_pcb>` and `cadgen pcb snapshot` draw a KiCad board from
one payload, built by `cadgen.engine.formats.kicad.plot` from the `.kicad_pcb` alone (no KiCad process) and
drawn by `@text-to-cad/core/lib/plot2d` on a 2D canvas. The payload is geometry per layer; what
colour a layer is drawn in is the renderer's (`plot2d/theme.js`, KiCad's default theme). It is a
function of the saved board and companion project bytes. Every request rereads them; no
parsed-board cache is kept. `schemaVersion` is `cadgen.plot.PLOT_SCHEMA_VERSION` = `plot2d.PLOT_SCHEMA_VERSION`;
a mismatch is refused by name on both sides.

```jsonc
{
  "schemaVersion": 3,
  "kind": "board",                 // words only: what the payload draws
  "generator": "pcbnew 10.99",     // what wrote the file, for words
  "unrouted": 1,                   // connections still to make: the ratsnest's lines
  "sheets": [{
    "name": "blinky", "width": 40.0, "height": 30.0, "background": "#001023",
    "layers": [ { "id": "B.Cu", "kind": "copper", "side": "back", "items": [ ... ] }, ... ]
  }],
  "board": { ... }                 // the board's index, in sheet millimetres
}
```

## The sheet

One sheet, in millimetres, y DOWN: KiCad's own frame moved so the board's outline (`Edge.Cuts`)
has its top-left corner at (0, 0); `width` and `height` are the outline's box. A board with no
outline is framed on everything it draws, 1 mm around. Every coordinate is rounded to four
decimals. The sheet is what the renderer frames and fills with the board's background; it clips
nothing to it. An item past the outline — a fab note off the edge, as KiCad draws one — is drawn
where it falls, over the surround (`layoutPlot`'s `extent` is the box of everything drawn).

## The layers

Back to front as seen from the top: `B.CrtYd`, `B.Fab`, `B.SilkS`, `B.Paste`, `B.Adhes`, `B.Mask`,
`B.Cu`, the inner coppers deepest first (`In4.Cu` … `In1.Cu`), `F.Cu`, `F.Mask`, `F.Adhes`,
`F.Paste`, `F.SilkS`, `F.Fab`, `F.CrtYd`, the user layers (`Dwgs.User`, `Cmts.User`, `Eco1.User`,
`Eco2.User`, `User.N`), `Margin`, `Edge.Cuts`, then three layers of what goes through the board:
`vias`, `ratsnest`, `drills`. A layer the board declares but draws nothing on is left out, except
the copper layers, which are always present so a view can name them.

| field | meaning |
| --- | --- |
| `id` | KiCad's layer name, or `vias`, `ratsnest`, `drills` |
| `kind` | `copper`, `silk`, `fab`, `courtyard`, `mask`, `paste`, `adhesive`, `user`, `margin`, `outline`, `via`, `ratsnest`, `drill` |
| `side` | `front` (`F.*`), `back` (`B.*`) or `both` (inner copper, the outline, and what goes through the board) |
| `items` | what the layer draws, in file order |

A view (`plot2d.drawPlot`'s `view`) chooses layers by id and orders them: without one, the board
as it is made is every layer but the `courtyard`, `mask` and `paste` kinds; seen from below, the
stack reverses and the `outline`, `via`, `ratsnest` and `drill` kinds stay on top, each layer
mirrored about the sheet's vertical centre line. The board's Display (`plot2d/boardDisplay.js`:
`{ mode, side, poured, layers }`, the viewer's and `cadgen pcb snapshot --display`'s one contract)
is a view over these ids: a mode is a set of layer kinds, `layers` an explicit set of ids (one
that differs from its mode's reads as Custom), `poured` and `side` switches of their own. What is
drawn ON the board — an annotation's ink, Measure's ends — is kept in sheet millimetres, so it
stays on what it marks from either side; the view's plan is the sheet with y negated, mirrored
about its middle from below (`plot2d/boardView.js`), the frame a Quick Edit's plan-view camera
speaks.

## The items

Each item has `t`, its type; every point is sheet millimetres.

| `t` | fields | draws |
| --- | --- | --- |
| `poly` | `pts` (3+ vertices), optional `w` | a filled polygon, its outline also stroked `w` wide when `w` > 0 (a mask opening grown by its margin, a graphic drawn with a pen) |
| `path` | `pts` (2+ points), `w`, optional `closed` | a stroked polyline, round caps and joins; `w` 0 is a hairline (one CSS pixel at any zoom) |
| `circle` | `at`, `r`, `w` | a filled disc (`w` 0) or a ring `w` wide |
| `text` | `text`, `w`, `strokes` (polylines of 2+ points) | the string's strokes, `w` wide |

Flags any item may carry: `ref`, the board reference of what drew it (`#R1` for a footprint's
graphics and text, `#R1.2` for a pad and its mask and paste); `net`, the net of a piece of copper;
`pour: true`, a zone's fill, which a view with `poured: false` leaves out; `via`
(`through`, `blind`, `micro`) on a via's disc and `hole` (`pad`, `via`, `npth`) on a drill
hole, which the theme colours by kind.

What each thing becomes:

- **Pads** are their padstack's outline (rect, roundrect, oval, circle, trapezoid, chamfered,
  custom: the hull of its primitives) as a `poly` on every copper layer they are on, with `ref`
  and `net`. A through-hole pad's hole is a `circle` (a slot, a `poly`) on `drills`, `hole: "pad"`;
  an unplated hole `hole: "npth"`.
- **Tracks and arcs** are `path`s of their width on their layer, with `net`; an arc is sampled.
- **Vias** are a filled `circle` on `vias` (`via` kind, `net`) and their hole on `drills`
  (`hole: "via"`).
- **Pours** are the fills KiCad saved, `poly` with `pour: true` and `net`, and their drawn outline
  as a closed hairline `path`. The author must refill changed zones in KiCad and save them; the reader does not repair stale fills.
- **Graphics** (`gr_*`, `fp_*`: lines, rectangles, circles, arcs, polygons, curves) are `path`s of
  their stroke width, or a `poly` with that width when filled; a footprint's carry `ref`.
- **Text** (footprint fields and `fp_text` that are not hidden, `gr_text`) is its strokes in Hershey
  Simplex (`cadgen.kicad.stroke_font`: public domain; KiCad's own font is GPL) at KiCad's position,
  size, thickness, angle, justification and mirroring. `${REFERENCE}` and `${VALUE}` are
  substituted. Same places, different glyphs.
- **Mask** openings and **paste** are derived from the pads: a pad's outline grown by its mask
  margin (the pad's, its footprint's, else the board's `pad_to_mask_clearance`), as a `poly`
  with `w` = twice the margin; a pad's outline for paste, grown by a positive paste margin or
  scaled in by a negative one. Close to KiCad's plotter, not its offsets.
- **The ratsnest** is cadgen's connectivity over the copper (`cadgen.kicad.connectivity`): per net,
  the pieces of copper that touch on a shared layer form a cluster, and the clusters that hold a
  pad are joined by their shortest tree, one hairline `path` per line between the nearest pads.
  No DRC, no clearance: touching copper is joined.

Not drawn: dimensions, text boxes, images, rule areas (keepouts) and a zone's hatch.

## The board index

`board` is `cadgen.engine.formats.kicad.board_index.BoardIndex.as_json()` in sheet millimetres: `parts` (ref,
value, footprint, side, `at`, `rotation`, `fields`, `dnp`, `outline`), `pads` (part, number, name,
net, type, side, `at`, `polygon`, `drill`), `tracks`, `vias`, `zones` (outlines), `holes`,
`outline` (Edge.Cuts chained into polylines) and `nets` (name, class). `origin` is where KiCad's
page origin (0, 0) lies on the sheet, so the viewer's index (`board2d/boardIndex.js`) reads every
position and every reference (`#net:VBUS@x40.1y21.6`, `#@x3.5y3.5`) back in KiCad's own frame,
millimetres, y down: a point the viewer copies pastes straight into a script's `Vector2.from_xy_mm`.
