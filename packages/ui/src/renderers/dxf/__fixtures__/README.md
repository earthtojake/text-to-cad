# DXF renderer fixture

`sample.dxf` is a 100 x 60 mm drawing carrying one of each thing the renderer
has to get right: default-pen line-work, a red circle, a solid hatch with an
island, TEXT, and a bulged LWPOLYLINE. `sample.drawing.json` is exactly what
`GET /__cad/drawing` answers for it — what `DxfRenderer.browser.test.mjs`
serves, so the browser test needs neither Python nor ezdxf.

`layered.dxf` is the drawing with the structure a Layers section is for — five layers, a block
placed twice with its centre line on another layer, and a dimension — and `layered.drawing.json`
its payload, what `DxfRenderer.test.tsx` and `drawingReferences.test.js` read.

Regenerate all four after changing a drawing or the payload shape, from the
repository root:

    .venv/bin/python packages/ui/src/renderers/dxf/__fixtures__/make_fixture.py
