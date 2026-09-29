# Brand assets

`generate-logos.mjs` is the source for the blue C, CAD and TEXT2CAD SVGs in
`apps/docs/public/brand/` and the viewer's copy of C. Run it with Node from
any directory. No fonts, raster tracing or runtime dependencies.

All letters are three units wide, four tall, and extruded two units deep.
Most bodies use half-unit blocks. T uses quarter-unit horizontal alignment
to center its slimmer 1.5-unit stem. The selected C has a 1.5-unit spine and
1.5-unit arms, identically in the square icon and both wordmarks. The standalone
SVG centers it in a square viewBox without distorting it.

A’s two outer top corners and D’s two outer right corners have half-unit
straight chamfers. C retains square corners. Their inner openings stay square.
A’s counter is one unit wide and one unit tall, spanning 1–2 units below
the cap; its foot opening stays unchanged. D’s opening is one unit wide and
two units tall, leaving one-unit top and bottom caps. There are
no curved profile segments in any letter.

E has three full-width, one-unit horizontal bars and a 1.5-unit spine. The 2
matches these stroke weights, with one-unit horizontal bars, 1.5-unit side
strokes and half-unit gaps. X keeps four square corner blocks and a filled,
two-unit-wide midpoint. Half-unit 45° cuts meet at the outer waist at y=2;
quarter-unit 45° cuts ease its inner notch corners while retaining flat notch
bottoms. The bottom half mirrors the top half across y=2, with inner notch
bottoms at y=1.25 and y=2.75. The 2 has just one half-unit 45° cut, at its
top-right corner. Every other corner and inner opening stays square.
No letter uses fillets.
Coplanar faces are merged, so there are no decorative grid lines.

The sketch uses an oblique projection: the front face stays upright and depth
recedes at 45 degrees, shortened to 0.42 screen units per model unit. This is
not a strict equal-axis isometric projection. The solids are blue: front
`#249ddd`, top `#62b7ec`, side `#1475ad`, with thin dark-blue
STEP-style edges (`#123e59`, 0.038 model units). Transparent backgrounds work in both
the light and dark UI. The selected Soft relief finish adds gentle blue face
gradients, fine inset highlights and a subtle contact shadow. Export bounds
include the shadow; the underlying letter profiles stay unchanged.

Regenerate vectors and PNG/ICO exports (uses the docs dependency `sharp`):

```sh
node scripts/brand/generate-logos.mjs
node scripts/brand/bake-favicons.mjs
```

The vector generator also writes the same front outlines to
`models/branding/src/profiles.json`. Build the three matching STEP models with
the entrypoints documented in `models/branding/src/README.md`. Each block is
10 mm, and extrusion depth is 20 mm. CAD stores the solid geometry and blue
color; Soft relief is a rendering treatment.

The bake creates transparent 512px C, CAD and TEXT2CAD PNG downloads beside
the vectors, plus matching PNG and multi-resolution ICO favicons for both
apps. Ordinary builds consume the committed files.

`render-loading-icon.mjs` remains the independent recipe for the original
animated loading mark. Changing brand vectors must not replace those assets;
see `packages/ui/src/assets/README.md` for its provenance.

The pure `logoSvg(text, options)` export also accepts a face palette, optional
edge color, edge width, and `cShape` for design studies. Use `finish: 'flat'`
for unshaded palette studies; production defaults to `finish: 'soft-relief'`.
The C study options are `original`, `spine` (1.5-unit spine), `arms`
(1.5-unit horizontal strokes), and `bold` (both). All use half-unit cells
inside the same three-by-four bounds, with the full two-unit extrusion. These options do not change the
production palette. Only merged visible face boundaries are outlined; there are
no cube-grid or triangulation lines.
