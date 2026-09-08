/**
 * The wordmark, drawn live so it can move: JetBrains Mono ExtraBold Italic,
 * the ink over a copy in the icon's blue offset down-right (the geometry
 * `scripts/make-brand.mjs` renders to PNG). Hovering runs the shadow through
 * red, green and blue, fast, as one colour across every letter; the ink and
 * the offset hold still. `.brand-wordmark` in globals.css does the drawing;
 * `.reduce-motion` stills it.
 */
const TEXT = "HARDCORE";

export function Wordmark() {
  return (
    <span aria-label="Hardcore" className="brand-wordmark app-no-drag" data-text={TEXT} role="img">
      <span aria-hidden className="brand-wordmark-shadow">
        {TEXT}
      </span>
      <span aria-hidden className="brand-wordmark-ink">
        {TEXT}
      </span>
    </span>
  );
}
