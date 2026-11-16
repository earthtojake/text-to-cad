# Schematic renderer fixtures

`schematic.plot.json` is a `GET /api/v1/documents/kicad_sch/<id>/plot` payload with every sheet (schema
version 4, `@cad/core`'s `docs/plot-payload.md`): the test schematic of the Python suite
(`tests/python/support/kicad_schematic.py`, the project `divider`, in KiCad 9's format) as
`cad.engine.formats.kicad.schematic_plot.build_schematic_plot` writes it, so the tests need neither KiCad
nor a schematic. Two A4 pages, each on KiCad's drawing sheet (its frame and title block, as the route sends
it), and the hierarchy's `schematic` index:

- the root sheet `/` (`divider.kicad_sch`, page 1): `R1` and `R2` (10k) from `+5V` to `GND`, the `MID`
  node (a junction, the local label `MID`) running to the pin `IN` of the sheet `Load` at
  (127, 57.15), 31.75 x 19.05; `J1` on the global label `VOUT` and a second `GND`;
- the sheet `/Load/` (`load.kicad_sch`, page 2): `C1` (100n) on `IN` and `GND`, `R3` (1k) on `VOUT`, its
  pin 2 under a no-connect (`unconnected-(R3-Pad2)`).

`SchematicRenderer.test.tsx` and `SchematicRenderer.browser.test.mjs` serve it a sheet at a time, as the
route does with `?sheet=`. Regenerate it when the payload's shape or the schematic changes (the Python
suite asserts they agree):

```sh
./.venv/bin/python -c "
import json, pathlib, sys, tempfile
sys.path.insert(0, 'packages/cad/src'); sys.path.insert(0, '.')
from tests.python.support.kicad_schematic import write_schematic
from cad.engine.formats.kicad.schematic_plot import build_schematic_plot
with tempfile.TemporaryDirectory() as folder:
    plot = build_schematic_plot(write_schematic(pathlib.Path(folder) / 'divider'), drawing_sheet=True)
pathlib.Path('packages/ui/src/renderers/schematic/__fixtures__/schematic.plot.json').write_text(json.dumps(plot, indent=1) + '\n')
"
```
