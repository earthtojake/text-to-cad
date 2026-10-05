# Logo CAD sources

| Model | STEP output | Solids |
| --- | --- | --- |
| `logo_c.py` | `../STEP/logo_c.step` | 1 |
| `logo_cad.py` | `../STEP/logo_cad.step` | 3 |
| `logo_texttocad.py` | `../STEP/logo_texttocad.step` | 9 |

Each block is 10 mm. Every letter is 30 mm wide, 40 mm tall and extruded
20 mm in +Z. The letter fronts lie in XY with the bottom at Y=0; consecutive
letters have a 5 mm gap. Letters are separate named blue solids, with
through-openings in A, D and O. TEXTTOCAD's "TO" is the lighter blue. There is no background plate or support geometry.

`profiles.json` is generated from the vector generator's exact front outlines.
Edit the alphabet in `scripts/brand/generate-logos.mjs` at the repository root,
then regenerate the vectors and profiles before rebuilding these entrypoints:

```sh
node scripts/brand/generate-logos.mjs
node scripts/brand/animate-logos.mjs
node scripts/brand/export-logos.mjs
.venv/bin/python models/branding/src/logo_c.py
.venv/bin/python models/branding/src/logo_cad.py
.venv/bin/python models/branding/src/logo_texttocad.py
```

STEP outputs are generated locally and ignored by Git; only these sources and
the generated profile input are committed. The exported STEP files stand alone. Soft relief gradients, inset highlights
and contact shadows are artwork/rendering effects, not extra cuts in the solids.
The SVG uses an oblique projection; CAD viewers can choose other camera angles.
