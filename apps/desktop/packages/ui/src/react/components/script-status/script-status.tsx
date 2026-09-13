import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './script-status.css';

export type ScriptStatusKind = 'success' | 'error' | 'in-progress' | 'waiting' | 'cancelled';

export interface ScriptStatusProps extends Omit<React.HTMLAttributes<HTMLSpanElement>, 'children'> {
  status: ScriptStatusKind;
  /**
   * Uniform size shorthand. Sets the shared status bounding box.
   * Numbers are treated as CSS px values.
   */
  size?: string | number;
}

const STATUS_LABELS: Record<ScriptStatusKind, string> = {
  success: 'Success',
  error: 'Error',
  'in-progress': 'In Progress',
  waiting: 'Waiting',
  cancelled: 'Cancelled',
};

// Clockwise animation order for a matrix laid out as:
// [1, 2]
// [3, 4]
// The pulse therefore travels 1 → 2 → 4 → 3 → 1.
const DOT_POINTS = [
  [7.5, 7.5],
  [16.5, 7.5],
  [16.5, 16.5],
  [7.5, 16.5],
] as const;

function toCssLength(size: string | number) {
  return typeof size === 'number' ? `${size}px` : size;
}

function ScriptStatus({
  status,
  size = '1.5rem',
  className,
  style,
  role = 'img',
  'aria-label': ariaLabel,
  ...props
}: ScriptStatusProps) {
  return (
    <span
      {...props}
      role={role}
      aria-label={ariaLabel ?? STATUS_LABELS[status]}
      data-status={status}
      className={cx(styles.root, className)}
      style={
        {
          '--script-status-size': toCssLength(size),
          ...style,
        } as React.CSSProperties
      }
    >
      <ScriptStatusGlyph status={status} />
    </span>
  );
}

function ScriptStatusGlyph({ status }: { status: ScriptStatusKind }) {
  switch (status) {
    case 'success':
      return (
        <svg
          className={cx(styles.icon, styles.successIcon)}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M20 6 9 17l-5-5" />
        </svg>
      );

    case 'error':
      return (
        <svg
          className={cx(styles.icon, styles.errorIcon)}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M18 6 6 18" />
          <path d="m6 6 12 12" />
        </svg>
      );

    case 'in-progress':
      return (
        <svg
          className={cx(styles.icon, styles.inProgressIcon)}
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          {DOT_POINTS.map(([cx, cy], index) => (
            <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="2" className={styles.dot[index]} />
          ))}
        </svg>
      );

    case 'waiting':
      return (
        <svg className={cx(styles.icon, styles.waitingIcon)} viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="3" fill="currentColor" />
        </svg>
      );

    case 'cancelled':
      return (
        <svg
          className={cx(styles.icon, styles.cancelledIcon)}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <path d="M6 12h12" />
        </svg>
      );
  }
}

export { ScriptStatus };
