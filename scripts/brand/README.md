# Brand assets

`generate-logos.mjs` draws the blue C, CAD and TEXTTOCAD SVGs in
`apps/docs/public/brand/` from its block alphabet, and writes the same front
outlines to `models/branding/src/profiles.json`. No fonts, raster tracing or
runtime dependencies. `export-logos.mjs` (uses the docs dependency `sharp`) then
turns the SVGs into every other logo file:

```sh
node scripts/brand/generate-logos.mjs
node scripts/brand/export-logos.mjs
```

The export writes transparent 512px PNGs beside the vectors, the PNG and multi-resolution
ICO favicons for the docs site and the web viewer, the viewer's CAD wordmark
(`packages/ui/src/assets/logo-cad.svg`, the navbar's home mark and the home page's
wordmark in both apps) and the Codex plugin logo (`.codex-plugin/logo.png`).
Ordinary builds consume the committed files.

`logoSvg(text, options)` also accepts a face palette, edge color and width,
`cShape` (`original`, `spine`, `arms` or `bold`) and `finish: 'flat'` for design
studies, plus `lighter`, the letter indices drawn in the lighter blue.

## Letters

All letters are three units wide, four tall, extruded two units deep, and set
half a unit apart, so each letter's extrusion tucks behind the next. Most bodies
use half-unit blocks. T uses quarter-unit horizontal alignment to center its
slimmer 1.5-unit stem. C has a 1.5-unit spine and 1.5-unit arms, identically in
the square icon and both wordmarks; the standalone SVG centers it in a square
viewBox without distorting it.

A’s two outer top corners and D’s two outer right corners have half-unit
straight chamfers; O has them on all four corners. C retains square corners.
A, D and O share one square opening, one unit on a side and centered on the
letter (y 1.5–2.5); A’s foot opening is one unit wide and half a unit tall.
E has three full-width, one-unit horizontal bars and a 1.5-unit spine.

X is a solid body with a 45° V-notch cut into each side, mirrored across both
axes: the top and bottom notches are half a unit deep, the side notches 0.75. It
is the one letter off the half-unit grid. No letter uses fillets or curves, and
coplanar faces are merged, so there are no decorative grid lines.

## Projection and color

The art uses an oblique projection: the front face stays upright and depth
recedes at 45 degrees, shortened to 0.42 screen units per model unit. This is
not a strict equal-axis isometric projection. The solids are blue: front
`#249ddd`, top `#62b7ec`, side `#1475ad`, with thin dark-blue STEP-style edges
(`#123e59`, 0.038 model units). TEXTTOCAD draws "TO" in a lighter blue: front
`#8fd3f5`, top `#bce5f9`, side `#4b9fcd`, with the same edges; its sides shade
toward the brand blue rather than black, so it reads as the same material in a
lighter tint.

The Soft relief finish adds gentle face gradients, fine inset highlights and a
subtle contact shadow. Export bounds include the shadow; the letter profiles
stay unchanged. Transparent backgrounds work in both the light and dark UI.

## CAD models

The generator's `models/branding/src/profiles.json` holds the same front
outlines in block units. Rebuild the matching STEP models with the entrypoints
in `models/branding/src/README.md`. Each block is 10 mm
and the extrusion is 20 mm. CAD stores the solid geometry and the two
blues; Soft relief is a rendering treatment.

## Loading icon

`render-loading-icon.mjs` remains the independent recipe for the original
animated loading mark. Changing brand vectors must not replace those assets;
see `packages/ui/src/assets/README.md` for its provenance.
