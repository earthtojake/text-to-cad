import { cx } from '@styles/utilities/cx';
import { BookIcon, CheckIcon, CircleMinusIcon, RefreshCwIcon, XIcon } from 'lucide-react';
import * as React from 'react';
import * as styles from './status-icon.css';
import type { StatusIconIconVariants } from './status-icon.css';

export type StatusIconSeverity = 'success' | 'error' | 'warning' | 'info' | 'neutral';
export type StatusIconSize = NonNullable<StatusIconIconVariants['size']>;

export interface StatusIconProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Visual severity of the status icon. */
  severity?: StatusIconSeverity;
  /** Optional size of the status icon badge. */
  size?: StatusIconSize;
  /** Custom icon element. If omitted, a default icon is chosen based on severity. */
  icon?: React.ReactNode;
}

const DEFAULT_ICONS: Record<StatusIconSeverity, (size: StatusIconSize) => React.ReactNode> = {
  success: (size) => <CheckIcon className={styles.icon({ size })} strokeWidth={2} />,
  error: (size) => <XIcon className={styles.icon({ size })} strokeWidth={2} />,
  warning: (size) => <RefreshCwIcon className={styles.icon({ size })} strokeWidth={2} />,
  info: (size) => <BookIcon className={styles.icon({ size })} strokeWidth={2} />,
  neutral: (size) => <CircleMinusIcon className={styles.icon({ size })} strokeWidth={2} />,
};

/**
 * StatusIcon — a small rounded square badge that communicates a semantic state.
 *
 * Each severity maps to a default icon and a semantic background/foreground pair
 * from the design-system theme. Callers can override the icon by passing a
 * React node to the `icon` prop.
 */
function StatusIcon({
  severity = 'neutral',
  size = 'md',
  icon,
  className,
  ...props
}: StatusIconProps) {
  return (
    <span
      {...props}
      data-severity={severity}
      data-size={size}
      className={cx(styles.statusIcon({ severity, size }), className)}
    >
      {icon ?? DEFAULT_ICONS[severity](size)}
    </span>
  );
}

export { StatusIcon };
