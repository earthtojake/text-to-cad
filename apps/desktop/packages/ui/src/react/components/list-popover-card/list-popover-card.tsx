import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './list-popover-card.css';
import { card } from '@styles/recipes/card.css';

export type ListPopoverCardStatus = 'destructive' | 'warning' | 'info' | 'success';

export interface ListPopoverCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Optional status tint applied through the card recipe's status rooms. */
  status?: ListPopoverCardStatus;
}

/**
 * ListPopoverCard — a floating card pinned above the bottom edge of a list
 * container (which must be positioned). Used for selection action bars and
 * sync status banners that hover over list content.
 */
function ListPopoverCard({ status, className, children, ...props }: ListPopoverCardProps) {
  return (
    <div data-slot="list-popover-card" className={styles.positioner}>
      <div
        data-status={status}
        className={cx(
          card({ level: 'elevated', radius: 'md', padding: 'sm', status }),
          styles.inner,
          className
        )}
        {...props}
      >
        {children}
      </div>
    </div>
  );
}

export { ListPopoverCard };
