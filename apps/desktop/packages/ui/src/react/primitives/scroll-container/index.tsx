import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import { ScrollFade } from './scroll-fade';

export type ScrollContainerProps = {
  /**
   * Maximum height of the container. Numbers are interpreted as pixels.
   * Applied to the scrollable viewport so that it is genuinely constrained
   * and will scroll (and fade) when content overflows.
   */
  maxHeight?: number | string;
  /**
   * Padding applied to the scrollable viewport. Numbers are interpreted as pixels.
   * Placed on the viewport so that padding-bottom is honored during scroll
   * and the last row is not clipped.
   */
  padding?: number | string;
  /** Show the top fade when scrolled down. Defaults to true. */
  topFade?: boolean;
  size?: number | string;
  className?: string;
  viewportClassName?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
};

/**
 * ScrollContainer wraps ScrollFade with a top-fade toggle and an optional
 * maxHeight constraint. Fade visibility is handled entirely in CSS via a
 * scroll-driven @property animation — no JavaScript overflow detection needed.
 *
 * When content does not overflow the scroll timeline is inactive and the
 * @property var stays at its initial-value 0, so no fade appears. When content
 * overflows the top fade appears as soon as the user scrolls down.
 */
const ScrollContainer = React.forwardRef<HTMLDivElement, ScrollContainerProps>(
  function ScrollContainer(
    { maxHeight, padding, topFade = true, size, className, viewportClassName, style, children },
    ref
  ) {
    const resolvedMaxHeight =
      maxHeight === undefined
        ? undefined
        : typeof maxHeight === 'number'
          ? `${maxHeight}px`
          : maxHeight;

    // maxHeight targets the scrollable viewport div (not the outer wrapper) so that
    // the viewport is genuinely height-constrained and overflow: auto kicks in.
    const viewportStyle: React.CSSProperties | undefined = resolvedMaxHeight
      ? { maxHeight: resolvedMaxHeight }
      : undefined;

    return (
      <ScrollFade
        ref={ref}
        size={size}
        padding={padding}
        className={className}
        viewportClassName={cx(!topFade && 'sf-no-top', viewportClassName)}
        viewportStyle={viewportStyle}
        style={style}
      >
        {children}
      </ScrollFade>
    );
  }
);

export { ScrollContainer };
