/**
 * Preview's icon, a play triangle (lucide's Play, its path), drawn to stand beside Display's cube
 * (`../camera/ProjectionModeIcons.js`) as one pair: on the same 24-unit grid, in the cube's stroke (1.45 units, where
 * lucide's own is 2), and at 15/16 of lucide's size, so the triangle is as tall on screen as the cube (18 units of
 * path against the cube's 17, each with its stroke) at whatever size the pair is drawn — the navbar's and the
 * strip's 16px, a touch strip's 18px, a menu row's. Scaled about the grid's centre, so it keeps lucide's place in
 * its box: a little right of centre, where a triangle's weight reads as centred.
 */
const PLAY_PATH = "M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z";
const PLAY_SCALE = 15 / 16;

export function PreviewIcon({ className, strokeWidth = 1.45 }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false" data-preview-icon="">
      <path
        d={PLAY_PATH}
        transform={`translate(12 12) scale(${PLAY_SCALE}) translate(-12 -12)`}
        stroke="currentColor"
        strokeWidth={strokeWidth / PLAY_SCALE}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
