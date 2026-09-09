import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './list-row.css';

// ── Row ───────────────────────────────────────────────────────────────────────

export interface RowProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Whether this row has hover/click affordance. */
  interactive?: boolean;
  /** Whether this row is in a selected state. */
  selected?: boolean;
  /** Suppresses the bottom border on the final row of a list. */
  isLast?: boolean;
  /** Divider color: 'default' (border) or 'subtle' (borderSubtle). */
  divider?: 'default' | 'subtle';
  /** When true the inner padding wrapper is omitted so you control layout. */
  bare?: boolean;
}

/**
 * ListView.Row — a bordered, optionally interactive list row.
 *
 * Generalizes the `MultiLineListItem` pattern used throughout the desktop app:
 * border-bottom divider, hover state, selected state, and optional bare mode
 * for custom inner layout.
 *
 * Usage:
 *   <ListView.Row interactive onClick={...}>
 *     <MyRowContent />
 *   </ListView.Row>
 */
function Row({
  interactive = false,
  selected = false,
  isLast = false,
  divider = 'default',
  bare = false,
  className,
  children,
  ...props
}: RowProps) {
  return (
    <div
      data-slot="list-row"
      data-selected={selected || undefined}
      className={cx(styles.row({ interactive, selected, isLast, divider }), className)}
      {...props}
    >
      {bare ? children : <div className={styles.rowInner}>{children}</div>}
    </div>
  );
}

// ── SectionHeader ─────────────────────────────────────────────────────────────

export interface SectionHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Section label text. */
  label: React.ReactNode;
  /** Optional count shown in muted text after the label. */
  count?: number;
}

/**
 * ListView.SectionHeader — a styled section label with an optional item count.
 *
 * Mirrors the `SectionLabel` pattern from `CliAgentsList.tsx`:
 *   <SectionHeader label="Recommended" count={4} />
 *   → "Recommended (4)"
 */
function SectionHeader({ label, count, className, ...props }: SectionHeaderProps) {
  return (
    <div data-slot="list-section-header" className={cx(styles.sectionHeader, className)} {...props}>
      <span className={styles.sectionHeaderLabel}>{label}</span>
      {count !== undefined && <span className={styles.sectionHeaderCount}>({count})</span>}
    </div>
  );
}

export { Row, SectionHeader };
