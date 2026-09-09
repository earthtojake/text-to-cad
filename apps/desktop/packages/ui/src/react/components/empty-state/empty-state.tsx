import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './empty-state.css';

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Short headline describing the empty condition. */
  label: string;
  /** Optional supporting copy below the label. */
  description?: string;
  /** Optional call-to-action rendered below the text stack. */
  action?: React.ReactNode;
  /**
   * Render without the panel background, for containers that paint their own
   * surface (for example `CollectionView`'s card).
   */
  bare?: boolean;
}

/**
 * EmptyState — centered label/description/action stack for empty panels,
 * lists, and tabs. Fills its container (height 100%).
 */
function EmptyState({ label, description, action, bare, className, ...props }: EmptyStateProps) {
  return (
    <div
      data-slot="empty-state"
      className={cx(styles.root, bare && styles.bare, className)}
      {...props}
    >
      <div className={styles.content}>
        <h2 className={styles.label}>{label}</h2>
        {description && <p className={styles.description}>{description}</p>}
        {action && <div className={styles.action}>{action}</div>}
      </div>
    </div>
  );
}

export { EmptyState };
