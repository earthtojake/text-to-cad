import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './separated-list.css';

export interface SeparatedListProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * Gap between each item and the separator on both sides.
   * Accepts any CSS length value. Default: `'0.5rem'` (≈ gap-2).
   */
  gap?: string;
  /**
   * Layout direction.
   * - `column` (default): items stacked vertically, separators are horizontal lines.
   * - `row`: items laid out horizontally, separators are vertical lines.
   */
  direction?: 'row' | 'column';
}

/**
 * SeparatedList — renders a flex list with a 1px separator between each item.
 * The separator is never added before the first or after the last child.
 * Falsy children (`null`, `undefined`, `false`) are filtered out before
 * inserting separators so conditional items don't produce orphan dividers.
 *
 * Usage:
 *   <SeparatedList gap="0.75rem">
 *     <Item />
 *     {showExtra && <ExtraItem />}
 *     <Item />
 *   </SeparatedList>
 */
export function SeparatedList({
  children,
  gap = '0.5rem',
  direction = 'column',
  className,
  style,
  ...props
}: SeparatedListProps) {
  const items = React.Children.toArray(children).filter(Boolean);

  return (
    <div
      data-slot="separated-list"
      className={cx(styles.root, className)}
      style={{ flexDirection: direction, gap, ...style }}
      {...props}
    >
      {items.map((child, i) => (
        <React.Fragment key={(child as React.ReactElement).key ?? i}>
          {i > 0 && (
            <div
              aria-hidden
              className={direction === 'row' ? styles.separatorV : styles.separatorH}
            />
          )}
          {child}
        </React.Fragment>
      ))}
    </div>
  );
}
