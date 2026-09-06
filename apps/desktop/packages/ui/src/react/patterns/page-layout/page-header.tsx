import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import { Text } from '../../primitives/typography/Text';
import * as styles from './page-header.css';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PageHeaderProps {
  /** Primary heading for this page section. */
  title: string;
  /** Optional muted description below the title. */
  description?: string;
  /**
   * Toolbar / action content rendered below the title block, above the
   * separator. Typically a `SearchInput` + `Button` row.
   */
  actions?: React.ReactNode;
  /**
   * When true the header becomes `sticky top-0` so it stays visible while
   * the user scrolls through the content below.
   * Default: false.
   */
  sticky?: boolean;
  /**
   * Adds an Electron window drag region to the title block.
   * Default: false.
   */
  draggable?: boolean;
  className?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * PageLayout.Header — a page-section heading with an optional description,
 * action slot, and bottom separator.
 *
 * Generalizes `PageHeader` from the desktop app: title + description + actions
 * (e.g. SearchInput + Button) + a 1px separator. The `sticky` variant pins the
 * header to `top: 0` so it stays visible during scroll, matching the behavior
 * of Library and Settings tab headers.
 *
 * Usage:
 * ```tsx
 * <PageLayout.Header
 *   title="Prompts"
 *   description="Manage reusable prompts."
 *   sticky
 *   actions={<SearchInput ... />}
 * />
 * ```
 */
function PageHeader({
  title,
  description,
  actions,
  sticky = false,
  draggable = false,
  className,
}: PageHeaderProps) {
  // The title block always gets the drag class if draggable; it is reset on
  // the actions slot so interactive controls inside remain clickable.
  // When not draggable the extra inline style is omitted entirely.
  const titleBlockStyle: React.CSSProperties = draggable
    ? ({ WebkitAppRegion: 'drag' } as React.CSSProperties)
    : {};

  const actionsStyle: React.CSSProperties = draggable
    ? ({ WebkitAppRegion: 'no-drag' } as React.CSSProperties)
    : {};

  const body = (
    <div className={styles.header}>
      <div className={styles.titleBlock} style={titleBlockStyle}>
        <Text as="h2" variant="h1" tone="default">
          {title}
        </Text>
        {description && (
          <Text as="p" variant="description" tone="muted">
            {description}
          </Text>
        )}
      </div>
      {actions && (
        <div className={styles.actions} style={actionsStyle}>
          {actions}
          <div className={styles.separator} />
        </div>
      )}
      {!actions && <div className={styles.separator} />}
    </div>
  );

  if (!sticky) return body;

  return <div className={cx(styles.headerSticky, className)}>{body}</div>;
}

export { PageHeader };
