import * as React from 'react';
import * as styles from './segmented-spinner.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface SegmentedSpinnerIconProps extends React.SVGProps<SVGSVGElement> {
  /**
   * Uniform size shorthand. Sets both `width` and `height` when neither is
   * provided explicitly. Accepts any CSS length value. Defaults to `1em` so
   * the icon scales with the surrounding text size.
   */
  size?: string | number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SEGMENTS = 8;

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * SegmentedSpinnerIcon — an 8-segment radial activity indicator.
 *
 * Each segment animates its opacity with a staggered delay so the "bright head"
 * appears to sweep clockwise around the icon. The SVG itself never rotates,
 * which produces a calmer, more intentional motion than a spinning icon.
 *
 * Color is inherited via `currentColor` — place the icon inside any element
 * that sets a foreground color and it will match automatically.
 *
 * `aria-hidden="true"` is set by default because the icon is decorative; the
 * surrounding label element should carry the accessible description.
 *
 * ```tsx
 * <span aria-label="Loading">
 *   <SegmentedSpinnerIcon size="1rem" />
 * </span>
 * ```
 */
function SegmentedSpinnerIcon({
  size = '1em',
  width,
  height,
  ...props
}: SegmentedSpinnerIconProps) {
  const w = width ?? size;
  const h = height ?? size;

  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" width={w} height={h} {...props}>
      {Array.from({ length: SEGMENTS }, (_, index) => (
        <line
          key={index}
          x1="12"
          y1="2.5"
          x2="12"
          y2="5.5"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          transform={`rotate(${index * (360 / SEGMENTS)} 12 12)`}
          className={styles.segment[index]}
        />
      ))}
    </svg>
  );
}

export { SegmentedSpinnerIcon };
