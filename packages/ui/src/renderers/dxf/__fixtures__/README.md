# DXF renderer fixture

`sample.dxf` is a 100 x 60 mm drawing carrying one of each thing the renderer
has to get right: default-pen line-work, a red circle, a solid hatch with an
island, TEXT, and a bulged LWPOLYLINE. `sample.drawing.json` is exactly what
`GET /__cad/drawing` answers for it — what `DxfRenderer.browser.test.mjs`
serves, so the browser test needs neither Python nor ezdxf.

Regenerate both after changing the drawing or the payload shape, from the
repository root:

    .venv/bin/python packages/ui/src/renderers/dxf/__fixtures__/make_fixture.py
