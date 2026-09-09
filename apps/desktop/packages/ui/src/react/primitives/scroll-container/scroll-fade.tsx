import { cx } from '@styles/utilities/cx';
import * as React from 'react';

export type ScrollFadeProps = {
  /**
   * Override the fade gradient size. Accepts any CSS length string ('32px', '2rem')
   * or a number interpreted as pixels. Defaults to 24px.
   */
  size?: number | string;
  /**
   * Padding applied to the scrollable viewport. Numbers are interpreted as pixels.
   * Placed on the viewport (not the outer wrapper) so that padding-bottom is
   * respected by the browser during scroll and the last row is not clipped.
   */
  padding?: number | string;
  className?: string;
  viewportClassName?: string;
  style?: React.CSSProperties;
  /** Inline styles applied directly to the scrollable viewport div (not the wrapper). */
  viewportStyle?: React.CSSProperties;
  children?: React.ReactNode;
};

/**
 * ScrollFade wraps a scrollable viewport with a mask-based top fade.
 * The fade is driven by a CSS scroll-driven animation via a @property custom
 * property — it appears only once the user scrolls down, works correctly in
 * light and dark mode (no color-matching needed), and disappears automatically
 * when content does not overflow.
 *
 * The viewport ref is forwarded so callers can programmatically scroll it.
 *
 * @example
 * <ScrollFade className={cx(sx({ background: 'surface' }), s.h48)}>
 *   <VeryLongList />
 * </ScrollFade>
 */
const ScrollFade = React.forwardRef<HTMLDivElement, ScrollFadeProps>(function ScrollFade(
  { size, padding, className, viewportClassName, viewportStyle, style, children },
  ref
) {
  const fadeSize = size === undefined ? undefined : typeof size === 'number' ? `${size}px` : size;
  const resolvedPadding =
    padding === undefined ? undefined : typeof padding === 'number' ? `${padding}px` : padding;

  const wrapperStyle: React.CSSProperties = { ...style };

  const mergedViewportStyle: React.CSSProperties = {
    height: '100%',
    width: '100%',
    ...(fadeSize ? ({ '--fade-size': fadeSize } as React.CSSProperties) : {}),
    ...(resolvedPadding ? { padding: resolvedPadding } : {}),
    ...viewportStyle,
  };

  return (
    <div className={cx('scroll-fade', className)} style={wrapperStyle}>
      <div
        ref={ref}
        style={mergedViewportStyle}
        className={cx('scroll-fade__viewport', viewportClassName)}
      >
        {children}
      </div>
    </div>
  );
});

export { ScrollFade };
