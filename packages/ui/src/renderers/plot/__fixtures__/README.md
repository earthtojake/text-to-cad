# Plot renderer fixtures

Hand-made `GET /__cad/plot` payloads in KiCad's and WireViz's shape — SVG sheets in
millimetres, y down, each with the background its tool draws it on — small enough to
read, so the tests need neither KiCad, WireViz nor a board:

- `board.plot.json`: one 40 x 30 mm sheet on `#001023`, a 1 mm red track across
  its middle (y = 15, x 5..35), a yellow silkscreen box and a thin grey ratsnest line.
- `schematic.plot.json`: two sheets on `#F5F4EF`, A4 (297 x 210) then A5
  (210 x 148), each with a dark red frame 10 mm in and a green wire across its middle.
- `harness.plot.json`: a WireViz-shaped sheet (Graphviz's SVG: a size in points, the
  graph translated to y-up) of 216 x 108 pt — 76.2 x 38.1 mm — on `#ffffff`, a connector
  box at its left and a 6 pt red wire across its middle.

`PlotRenderer.browser.test.mjs` and `PlotRenderer.test.tsx` serve them as the route
would. Edit them by hand; nothing generates them.
