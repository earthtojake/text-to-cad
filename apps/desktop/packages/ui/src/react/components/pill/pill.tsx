import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './pill.css';

export type PillVariant = 'neutral' | 'success' | 'warning' | 'error' | 'info';

export interface PillProps extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'children'> {
  /** Visual treatment of the pill. */
  variant?: PillVariant;
  /** Show a leading status dot. */
  dot?: boolean;
  /** Pulse the leading dot (useful for pending/initializing states). */
  pulsing?: boolean;
  children: React.ReactNode;
}

function Pill({
  variant = 'neutral',
  dot = false,
  pulsing = false,
  children,
  className,
  ...props
}: PillProps) {
  return (
    <span
      {...props}
      data-variant={variant}
      className={cx(styles.root, styles.variant[variant], className)}
    >
      {dot && <span className={cx(styles.dot, pulsing && styles.pulsingDot)} aria-hidden="true" />}
      <span className={styles.label}>{children}</span>
    </span>
  );
}

export { Pill };
