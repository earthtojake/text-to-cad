import { useId } from "react";

// The tools that pick in modes (Select, Measure) share one way of drawing them, whatever the file:
// each mode has ONE glyph, drawn on the 24-unit grid. A tool's panel shows the mode's glyph at full
// size in its mode menu — All shows the tool's own glyph, Select's pointer or Measure's ruler. The
// strip's button shows the tool's glyph with the mode's glyph shrunk to a badge in its top-right
// corner (none for All); the tool's glyph steps down to the bottom-left to make room, and the badge
// is cut out of it, so the two never touch at the strip's 14px. A renderer supplies its modes' glyphs
// (`glyphs`: mode id -> `weight => <svg content>`; `weight` thickens strokes for the badge, which is
// drawn at under half size), whatever its modes pick.
export const TOOL_GLYPHS = Object.freeze({
  select: <path d="M4.037 4.688a.495.495 0 0 1 .651-.651l16 6.5a.5.5 0 0 1-.063.947l-6.124 1.58a2 2 0 0 0-1.438 1.435l-1.579 6.126a.5.5 0 0 1-.947.063z" />,
  measure: <>
    <path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.41 2.41 0 0 1 0-3.4l2.6-2.6a2.41 2.41 0 0 1 3.4 0Z" />
    <path d="m14.5 12.5 2-2" /><path d="m11.5 9.5 2-2" /><path d="m8.5 6.5 2-2" /><path d="m17.5 15.5 2-2" />
  </>,
});
const SVG = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
// Where the badge sits: the mode's glyph at 0.44 of its size, centred on (18.5, 5.5).
const BADGE_SCALE = 0.44, BADGE_CENTRE = [18.5, 5.5];
const BADGE_TRANSFORM = `translate(${BADGE_CENTRE[0] - 12 * BADGE_SCALE} ${BADGE_CENTRE[1] - 12 * BADGE_SCALE}) scale(${BADGE_SCALE})`;

/** A mode's own glyph at full size, for the mode menu in the tool's panel: a mode with no glyph ("all") is the tool's (`tool`). */
export function ModeGlyph({ tool, glyphs, mode, ...props }) {
  const glyph = glyphs[mode];
  return <svg {...SVG} data-mode-glyph={glyph ? mode : tool} {...props}>{glyph ? glyph(1) : TOOL_GLYPHS[tool]}</svg>;
}

/** The strip's composite: the tool's glyph (`tool`, "select" or "measure") badged with `mode`'s glyph, none for "all". */
export function ToolModeIcon({ tool, glyphs, mode, ...props }) {
  const mask = `tool-mode-${useId().replace(/[^\w-]/g, "")}`;
  const glyph = glyphs[mode];
  return <svg {...SVG} data-tool-icon-base={tool} {...props}>
    {glyph ? <>
      <mask id={mask}><rect width="24" height="24" fill="white" /><circle cx={BADGE_CENTRE[0]} cy={BADGE_CENTRE[1]} r="6.25" fill="black" /></mask>
      <g mask={`url(#${mask})`}><g transform="translate(0 4) scale(0.84)" strokeWidth="2.3">{TOOL_GLYPHS[tool]}</g></g>
      <g data-tool-icon-badge={mode} transform={BADGE_TRANSFORM}>{glyph(1.7)}</g>
    </> : TOOL_GLYPHS[tool]}
  </svg>;
}

/** A tool's modes as `ToolModeMenu` rows, each with its glyph at full size. */
export function modeMenuItems(tool, glyphs, modes) {
  return modes.map(item => ({ id: item.id, label: item.label,
    icon: <ModeGlyph tool={tool} glyphs={glyphs} mode={item.id} className="size-3.5" aria-hidden="true" /> }));
}
