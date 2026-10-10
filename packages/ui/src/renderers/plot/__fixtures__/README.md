# Plot renderer fixtures

`GET /__cad/plot` payloads (schema version 2) in KiCad's and WireViz's shape — SVGs in
millimetres, y down, each sheet with the background its tool draws it on — so the tests
need neither KiCad, WireViz nor a board:

- `board.plot.json`: KiCad 10's own plot of a small draft board, as
  `cadgen.kicad.plot.build_plot` writes it: one 40 x 30 mm sheet (39.98 x 30.00, KiCad's
  page rounds to the mil) on `#001023`, its layers back to front — `B.Fab`, `B.SilkS`,
  `B.Cu` (a GND pour in the bottom left, so the layer has an `unpoured` picture), `F.Cu`
  (a 1 mm VBUS track across the middle, y = 15, x 5..35, from J1 pin 1 to R1 pin 1, and a
  GND track from D1 to J1 pin 2), `F.SilkS`, `F.Fab`, `Edge.Cuts`, `ratsnest` (the one
  unrouted connection, D1 pin 2 to R1 pin 2) and `drills` — and its `board` index:
  J1, R1 and D1, their pads, the tracks, the pour, the nets and that one `unconnected`
  finding with its pads' references. Nothing sits on the middle of the track or in the
  sheet's corners, which the browser test reads.
- `schematic.plot.json`: two sheets on `#F5F4EF`, A4 (297 x 210) then A5
  (210 x 148), each with a dark red frame 10 mm in and a green wire across its middle.
- `harness.plot.json`: a WireViz-shaped sheet (Graphviz's SVG: a size in points, the
  graph translated to y-up) of 216 x 108 pt — 76.2 x 38.1 mm — on `#ffffff`, a connector
  box at its left and a 6 pt red wire across its middle.

`PlotRenderer.browser.test.mjs` and `PlotRenderer.test.tsx` serve them as the route
would. Edit the schematic and the harness by hand; plot the board again with
`build_plot` when the payload's shape changes.
