/**
 * SelectableCard — a flat, bordered button card with hover and selected states.
 *
 * Renders as a `<button>` by default. Uses a fixed elevated surface background
 * and a neutral border that becomes more prominent when selected. Text color
 * shifts from muted (unselected) to foreground (selected); non-interactive cards
 * use passive text.
 */

import { cx } from '@styles/utilities/cx';
import * as React from 'react';
// Relative type import: the dts emitter rewrites `@styles/*` type imports to a
// dangling relative path, silently degrading the sprinkle prop types.
import type { Sprinkles } from '../../../styles/utilities/sprinkles.css';
import { selectableCard } from './selectable-card.css';
import { sx } from '@styles/utilities/sprinkles.css';

export interface SelectableCardProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Horizontal alignment of the card content. */
  justifyContent?: Sprinkles['justifyContent'];
  /** Selected / active state. */
  selected?: boolean;
  /** Enables hover + selected styling. */
  interactive?: boolean;
  /** Padding scale token. */
  padding?: Sprinkles['padding'];
  /** Border radius scale token. */
  borderRadius?: Sprinkles['borderRadius'];
}

export const SelectableCard = React.forwardRef<HTMLButtonElement, SelectableCardProps>(
  function SelectableCard(
    {
      justifyContent,
      selected = false,
      interactive = true,
      padding,
      borderRadius,
      className,
      children,
      type = 'button',
      ...rest
    },
    ref
  ) {
    const sprinkles: Partial<Sprinkles> = {};
    if (justifyContent != null) sprinkles.justifyContent = justifyContent;
    if (padding != null) sprinkles.padding = padding;
    if (borderRadius != null) sprinkles.borderRadius = borderRadius;
    const sprinkleClass =
      Object.keys(sprinkles).length > 0 ? sx(sprinkles as Sprinkles) : undefined;

    return (
      <button
        ref={ref}
        type={type}
        data-selected={selected ? 'true' : undefined}
        aria-selected={selected}
        data-interactive={interactive ? 'true' : 'false'}
        className={cx(selectableCard, sprinkleClass, className)}
        {...rest}
      >
        {children}
      </button>
    );
  }
);
