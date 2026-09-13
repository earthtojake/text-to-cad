import { MicroLabel } from '@react/primitives/label';
import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './card-grid.css';
import { card } from '@styles/recipes/card.css';

/**
 * CardGrid — a responsive auto-fit grid of cards. Columns are at least 16rem
 * wide (clamped to the container) and stretch to fill the row.
 */
function CardGrid({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div data-slot="card-grid" className={cx(styles.grid, className)} {...props}>
      {children}
    </div>
  );
}

export interface CardGridSectionProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Section heading rendered as a MicroLabel above the grid. */
  title: string;
}

/** CardGridSection — a MicroLabel heading followed by a CardGrid of children. */
function CardGridSection({ title, className, children, ...props }: CardGridSectionProps) {
  return (
    <div data-slot="card-grid-section" className={cx(styles.section, className)} {...props}>
      <MicroLabel>{title}</MicroLabel>
      <CardGrid>{children}</CardGrid>
    </div>
  );
}

/**
 * CardGridItem — an interactive card row for use inside CardGrid. Composes the
 * shared card recipe (elevation, border, hover state) with a horizontal
 * icon/content layout. Callers own the inner content and any hover-reveal
 * affordances.
 */
function CardGridItem({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="card-grid-item"
      className={cx(
        card({ padding: 'lg', radius: 'lg', interactive: true }),
        styles.item,
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export { CardGrid, CardGridSection, CardGridItem };
