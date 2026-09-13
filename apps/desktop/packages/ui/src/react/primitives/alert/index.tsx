import type { SurfaceStatusName } from '@emdash/theme';
import { cx } from '@styles/utilities/cx';
import { AlertCircleIcon, AlertTriangleIcon, CheckCircleIcon, InfoIcon, XIcon } from 'lucide-react';
import * as React from 'react';
import { Surface } from '../surface/surface';
import * as styles from './alert.css';

// ── Status icon map ───────────────────────────────────────────────────────────

const STATUS_ICONS: Record<SurfaceStatusName, React.ReactNode> = {
  info: <InfoIcon />,
  success: <CheckCircleIcon />,
  warning: <AlertTriangleIcon />,
  destructive: <AlertCircleIcon />,
};

// ── Sub-components ────────────────────────────────────────────────────────────

function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p data-slot="alert-title" className={cx(styles.alertTitle, className)} {...props} />;
}

function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      data-slot="alert-description"
      className={cx(styles.alertDescription, className)}
      {...props}
    />
  );
}

/**
 * AlertAction — free-form action slot pinned to the alert's top-right corner
 * (e.g. a "Fix" or "Retry" button). The root reserves horizontal room for it.
 */
function AlertAction({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div data-slot="alert-action" className={cx(styles.alertAction, className)} {...props} />;
}

// ── Root ──────────────────────────────────────────────────────────────────────

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  status: SurfaceStatusName;
  icon?: React.ReactNode | null;
  onDismiss?: () => void;
}

function AlertRoot({ status, icon, onDismiss, className, children, ...props }: AlertProps) {
  const resolvedIcon = icon === null ? null : (icon ?? STATUS_ICONS[status]);

  return (
    <Surface
      role="alert"
      status={status}
      data-slot="alert"
      className={cx(styles.alertRoot, className)}
      {...props}
    >
      {resolvedIcon != null && (
        <span className={styles.alertIcon} aria-hidden>
          {resolvedIcon}
        </span>
      )}
      <div className={styles.alertBody}>{children}</div>
      {onDismiss != null && (
        <button
          type="button"
          aria-label="Dismiss"
          className={styles.alertDismiss}
          onClick={onDismiss}
        >
          <XIcon aria-hidden />
        </button>
      )}
    </Surface>
  );
}

export const Alert = {
  Root: AlertRoot,
  Title: AlertTitle,
  Description: AlertDescription,
  Action: AlertAction,
};
