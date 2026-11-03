# Board renderer fixtures

`board.plot.json` is a `GET /api/v1/documents/kicad_pcb/<id>/plot` payload (schema version 3, `@cad/core`'s
`docs/plot-payload.md`): the test board of the Python suite
(`tests/python/support/kicad_board.py`, in the format KiCad 11's headless API saves) as
`cad.engine.formats.kicad.plot.build_plot` writes it, so the tests need neither KiCad nor a board. One
40 x 30 mm sheet on `#001023`, its layers back to front, and its `board` index:

- `J1`, a 1x02 pin header at (5, 15): through-hole pads `1` (VBUS, at (5, 15)) and `2` (GND,
  at (5, 17.54)), on both coppers, with their holes on `drills`;
- `R1`, an 0603 at (35, 15): pads `1` (VBUS, at 34.175) and `2` (LED, at 35.825);
- `D1`, an 0603 LED at (20, 24) turned a quarter turn: pads `1` (GND, at (20, 24.825)) and
  `2` (LED, at (20, 23.175));
- a 1 mm VBUS track across the middle, y = 15, x 5..34.175: KiCad's red, with nothing else
  on the column x = 30 that the browser test reads;
- a GND track from D1.1 to a via at (18, 27), and a GND pour on `B.Cu` over the bottom left
  (its fill (1.5, 16.5) to (19.5, 28.5));
- the LED net unrouted: one `ratsnest` line from D1.2 to R1.2 (`unrouted: 1`);
- the text `blinky` on the top silkscreen at (20, 5), and each part's reference and value;
- every item with the uuid KiCad saves it with (the support board's `UUIDS` for the board's own:
  the VBUS track `…0001`, the GND track `…0002`, the via `…0003`, the pour `…0004`, `blinky`
  `…0005`, the outline `…0006`; a footprint and its items `f00d0000-…` in the order written).

`BoardRenderer.browser.test.mjs` and `BoardRenderer.test.tsx` serve it as the route would.
Regenerate it when the payload's shape or the board changes (the Python suite asserts they
agree):

```sh
./.venv/bin/python -c "
import json, pathlib, sys, tempfile
sys.path.insert(0, 'packages/cad/src'); sys.path.insert(0, '.')
from tests.python.support.kicad_board import write_board
from cad.engine.formats.kicad.plot import build_plot
with tempfile.TemporaryDirectory() as folder:
    plot = build_plot(write_board(pathlib.Path(folder)))
pathlib.Path('packages/ui/src/renderers/board/__fixtures__/board.plot.json').write_text(json.dumps(plot, indent=1) + '\n')
"
```
