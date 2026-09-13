import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './entity-header.css';

export interface EntityHeaderProps extends Omit<React.ComponentPropsWithoutRef<'header'>, 'title'> {
  /** Complete leading identity visual, such as a StatusIcon or MachineStatus. */
  icon: React.ReactNode;
  /** Title content. Callers provide the appropriate heading or inline editor. */
  title: React.ReactNode;
  /** Optional controls rendered as a right-aligned action group. */
  actions?: React.ReactNode;
}

/**
 * Horizontal identity header for entity overview and detail surfaces.
 *
 * The slots keep domain-specific identity, editing, and actions with the
 * caller while this pattern owns their shared alignment and overflow behavior.
 */
function EntityHeader({ icon, title, actions, className, ...props }: EntityHeaderProps) {
  return (
    <header {...props} data-slot="entity-header" className={cx(styles.root, className)}>
      <div data-slot="entity-header-icon" className={styles.icon}>
        {icon}
      </div>
      <div data-slot="entity-header-title" className={styles.title}>
        {title}
      </div>
      {actions ? (
        <div data-slot="entity-header-actions" className={styles.actions}>
          {actions}
        </div>
      ) : null}
    </header>
  );
}

export { EntityHeader };
