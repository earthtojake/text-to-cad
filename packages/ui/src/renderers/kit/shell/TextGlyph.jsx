// A glyph that is a word: two or three characters drawn as an icon ("2D", "3D"), where a picture would
// be less clear than the word, as KiCad, EasyEDA and the maps apps label their 3D switch. It is an icon in
// every way that matters to what holds it: Lucide's 24-unit grid in an `svg`, so the strip's tile sizes it
// as it sizes a Lucide icon (14px, a phone's 18px, `kit/tools/stripTouch.js`) and a More row's slot does
// (16px), and the word grows and shrinks with the slot; in `currentColor`, with no fill behind it, so it
// takes the tile's colour, hovered or not, light or dark; `aria-hidden`, the button holding it named.
//
// Its size and weight are measured against the Lucide icons beside it on a board's strip (their 2-unit line,
// 1.17px at 14px): set at 17 units (9.9px in a 14px slot), semibold, "2D" inks 12px across, as wide as Shapes'
// square, and 7.2px tall (a capital's height), and lays down as much ink as that square does (46px² to its
// 47; the pointer, pencil and ruler 34-37, Display 42, Flip 67), its stems about the icons' line; at 18 units
// it would ink about 52px², more than every icon but Flip. Tabular figures, so "2D" and "3D" are one
// width and nothing moves when the state does; letter-spacing a little tight, so the two characters read as
// one mark rather than a word set in a line of text. Three characters are set smaller (13 units), to stay
// inside the same span.

const FONT_UNITS = Object.freeze({ 2: 17, 3: 13 });
// Where the capitals' middle sits: the baseline a little over a third of the size under the grid's middle
// (a sans serif's capitals stand about 0.7 of its size), so the word is centred by its ink, not its em box.
const CAP_MIDDLE = 0.355;
// The tracking, in ems. It follows every character, the last too, so the advance the anchor centres ends that much
// short of the ink: the word is drawn half of it to the left to centre its ink.
const TRACKING = -0.04;

/**
 * @param {{ text: string, className?: string } & import("react").SVGProps<SVGSVGElement>} props
 *   `text`: the two or three characters drawn, the same in every language ("2D").
 */
export default function TextGlyph({ text, className, ...props }) {
  const size = FONT_UNITS[Math.min(3, Math.max(2, text.length))];
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" stroke="none" overflow="visible" aria-hidden="true"
      focusable="false" data-text-glyph={text} {...props}>
      <text x={12 + (size * TRACKING) / 2} y={12 + size * CAP_MIDDLE} textAnchor="middle" fontSize={size} fontWeight={600}
        style={{ fontVariantNumeric: "tabular-nums", letterSpacing: `${TRACKING}em`, whiteSpace: "pre" }}>{text}</text>
    </svg>
  );
}

/** A `TextGlyph` of `text` as an icon component, which a control handed an icon (`StateButton.jsx`'s `icon`) draws. */
export function textGlyphIcon(text) {
  const Icon = props => <TextGlyph text={text} {...props} />;
  Icon.displayName = `TextGlyph(${text})`;
  return Icon;
}
