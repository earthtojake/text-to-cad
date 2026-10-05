# Brand assets

`generate-logos.mjs` draws the blue C, CAD and TEXTTOCAD SVGs, and the stacked
TEXT TO CAD lockup, in `apps/docs/public/brand/` from its block alphabet, and writes the same front
outlines to `models/branding/src/profiles.json`. No fonts, raster tracing or
runtime dependencies. `animate-logos.mjs` draws each mark's animated build beside
it (see [Animation](#animation)). `export-logos.mjs` (uses the docs dependency `sharp`) then
turns the SVGs into every other logo file:

```sh
node scripts/brand/generate-logos.mjs
node scripts/brand/animate-logos.mjs
node scripts/brand/export-logos.mjs
```

The export writes transparent 512px PNGs beside the vectors, the PNG and multi-resolution
ICO favicons for the docs site and the web viewer, the viewer's CAD wordmark
(`packages/ui/src/assets/logo-cad.svg`, the navbar's home mark and the home page's
wordmark in both apps) and the Codex plugin logo (`.codex-plugin/logo.png`).
Ordinary builds consume the committed files.

`logoSvg(text, options)` also accepts a face palette, edge color and width,
`cShape` (`original`, `spine`, `arms` or `bold`) and `finish: 'flat'` for design
studies, plus `lighter`, the letter indices drawn in the lighter blue, and `words`
with `stacked` for the lockup (see [Stacked lockup](#stacked-lockup)).

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

## Stacked lockup

`logo-texttocad-stacked.svg` sets TEXT TO CAD as a film title does: TEXT, then a
half-size TO between two long rules, then CAD scaled up to the same width as TEXT.
The small letters keep their proportions, two units of extrusion becoming one, and
are tracked half a unit apart; the rules are half a unit thick and stop three
quarters of a unit short of the TO. TO and its rules are the lighter blue. Each row
sits a third of a unit below the one above, plus its own receding top faces. Scaled
pieces keep the 0.038 edge width of the rest.

## Animation

`logo-c-animated.svg`, `logo-cad-animated.svg`, `logo-texttocad-animated.svg` and
`logo-texttocad-stacked-animated.svg` build each mark the way its CAD model is made,
from the same outlines:

1. **Sketch.** A half-unit grid and dashed construction lines at each row's cap
   height and baseline fade in. A pen stroke draws each piece's sketch on the grid,
   dropping a sketch point at every corner, and the closed profile shades. Every
   letter but T starts as its 3 × 4 block, A, D and O with square corners; T is
   sketched as itself, since its shoulders are its silhouette. The rules draw
   outward from the TO.
2. **Extrude.** The profile sweeps back to full depth as a translucent preview body,
   which turns solid when it gets there; the sketch is consumed. From here on every
   piece is lit as the finished mark: its Soft relief gradients, inset highlights and
   contact shadow (the static generator's own `lightFaces` and `shadowFilter`).
3. **Cut.** Every opening is sketched on the front face in the edge navy, then cut:
   C's and E's slots, A's foot and X's four notches (each a run of the outline that
   leaves one side of the block and returns to it) and the counters of A, D and O.
   The part is the cut profile in front of the cut depth and the whole block behind
   it, so the floor sinks, the walls grow and the slots open through the sides
   until the cut goes through the back.
4. **Chamfer.** The corner edges are picked in amber, and half-unit 45° chamfers
   grow from them in an amber preview that switches off when they commit.
5. **Finish.** The grid fades out and the static artwork takes over from the build,
   which already matches it pixel for pixel (the finished letters draw their faces in
   the static art's order), so the lighting never changes at the end.

Each word runs the steps in turn, starting 0.45 s after the word before it, so the
words of TEXTTOCAD overlap; within a step, letters start a beat apart, left to
right. The builds take about 3.0 s (C), 4.0 s (CAD) and 4.9 s (TEXTTOCAD and the
lockup) and hold their last frame. They are SMIL, so they play inside an `<img>`
with no script. Every animated attribute's own value is its last frame, and every
layer but the final artwork starts hidden, so a renderer without SMIL shows the
static mark. `animate-logos.test.mjs` checks those properties, that path morphs
keep one command structure, and that the committed files match the generator.
Pages that show a build serve the static mark under `prefers-reduced-motion` (a
`<picture>` source); a fresh URL replays it.

The repository README shows `logo-texttocad-animated.svg` too: about 7 KB in Git, where a GIF
of the same build is about 2 MB that Git cannot compress.

## Loading icon

The animated loading mark is separate from these vectors: changing them must not
replace its images. See `packages/ui/src/assets/README.md` for its provenance.
