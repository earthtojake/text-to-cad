import { cx } from '@styles/utilities/cx';
import { FolderGit2Icon, FolderIcon, GitBranchIcon, type LucideIcon } from 'lucide-react';
import * as React from 'react';
import * as styles from './workspace-icon.css';

export type WorkspaceIconType = 'directory' | 'repository' | 'worktree';

export type WorkspaceIconStatus = 'active' | 'idle' | 'setting-up' | 'tearing-down' | 'error';

export interface WorkspaceIconProps extends Omit<
  React.HTMLAttributes<HTMLSpanElement>,
  'children'
> {
  /** Workspace entry kind; determines the glyph. */
  type: WorkspaceIconType;
  /** Optional runtime status rendered as a colored dot on the tile corner. */
  status?: WorkspaceIconStatus;
  /**
   * Uniform size shorthand. Sets the tile bounding box; the glyph and status
   * dot scale with it. Numbers are treated as CSS px values.
   */
  size?: string | number;
}

const TYPE_ICONS: Record<WorkspaceIconType, LucideIcon> = {
  directory: FolderIcon,
  repository: FolderGit2Icon,
  worktree: GitBranchIcon,
};

const TYPE_LABELS: Record<WorkspaceIconType, string> = {
  directory: 'Directory',
  repository: 'Repository',
  worktree: 'Worktree',
};

const STATUS_LABELS: Record<WorkspaceIconStatus, string> = {
  active: 'Active',
  idle: 'Idle',
  'setting-up': 'Setting up',
  'tearing-down': 'Tearing down',
  error: 'Error',
};

function toCssLength(size: string | number) {
  return typeof size === 'number' ? `${size}px` : size;
}

/**
 * WorkspaceIcon — a rounded tile with a workspace-kind glyph (directory,
 * repository, or worktree) and an optional status dot on the bottom-right
 * corner, following the MachineStatus dot conventions.
 */
function WorkspaceIcon({
  type,
  status,
  size = '2.25rem',
  className,
  style,
  role = 'img',
  'aria-label': ariaLabel,
  ...props
}: WorkspaceIconProps) {
  const Icon = TYPE_ICONS[type];
  const defaultLabel = status
    ? `${TYPE_LABELS[type]} — ${STATUS_LABELS[status]}`
    : TYPE_LABELS[type];

  return (
    <span
      {...props}
      role={role}
      aria-label={ariaLabel ?? defaultLabel}
      data-type={type}
      data-status={status}
      className={cx(styles.root, className)}
      style={
        {
          '--workspace-icon-size': toCssLength(size),
          ...style,
        } as React.CSSProperties
      }
    >
      <Icon className={styles.icon} aria-hidden />
      {status !== undefined && (
        <span className={cx(styles.statusDot, styles.statusDotVariant[status])} aria-hidden />
      )}
    </span>
  );
}

export { WorkspaceIcon };
