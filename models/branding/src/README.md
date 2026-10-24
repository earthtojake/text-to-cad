# Logo CAD sources

`models/branding` on cadgen 0.8: the brand's block-letter logos as solids, each a
plain `@model`, and `exports.py`, which writes the STEP each delivers: this corpus's
example of a STEP deliverable kept current by an `exports.py`.

| Model | Delivers (`exports.py`) | Solids |
| --- | --- | --- |
| `logo_c.py` | `STEP/logo_c.step` | 1 |
| `logo_cad.py` | `STEP/logo_cad.step` | 3 |
| `logo_texttocad.py` | `STEP/logo_texttocad.step` | 9 |

Build from this folder, in any order, and write the deliverables (`../STEP/`, gitignored):

```
python logo_c.py
python logo_cad.py
python logo_texttocad.py
python exports.py
```

Each block is 10 mm. Every letter is 30 mm wide, 40 mm tall and extruded 20 mm in
+Z. The letter fronts lie in XY with the bottom at Y=0; consecutive letters have a
5 mm gap. Letters are separate named blue solids, with through-openings in A, D and
O. TEXTTOCAD's "TO" is the lighter blue. There is no background plate or support
geometry.

`profiles.json` is the vector generator's exact front outlines, which
`scripts/brand/generate-logos.mjs` writes here. The models read it through
`lib/logo_shape.py`, so a change to it rebuilds the logos.

The port: `@step(out=...)` -> `@model`, the STEP written by `exports.py`; cadgen's
build123d proxy -> `import build123d as bd`; `cadgen.srgb("#…")` -> the hex itself, which
a shape takes as it is. Each script's `__main__` calls its model.
