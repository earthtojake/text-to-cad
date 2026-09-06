import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './page-layout.css';
import type { ContentVariants } from './page-layout.css';

export interface PageLayoutProps {
  /**
   * When provided the layout switches to the two-column sidebar+content grid
   * (Library / Settings style). When absent, a single centered column is used
   * (Automations style).
   */
  sidebar?: React.ReactNode;
  /**
   * Adds an Electron window drag region to the scroll container so the
   * titlebar area remains draggable when the cursor is over the layout.
   * Default: false.
   */
  draggable?: boolean;
  className?: string;
  children: React.ReactNode;
}

/**
 * PageLayout — the scroll-owning page shell used by Library, Settings, and
 * Automations-style views.
 *
 * With `sidebar`:
 *   max-w-[1060px] two-column grid (13rem sidebar + flex content)
 *
 * Without `sidebar`:
 *   single centered column, max-w-4xl
 *
 * Usage:
 * ```tsx
 * <PageLayout sidebar={<PageLayout.SidebarMenu items={...} activeId={...} onSelect={...} />}>
 *   <PageLayout.Content>
 *     <PageLayout.Header title="Prompts" />
 *     …
 *   </PageLayout.Content>
 * </PageLayout>
 * ```
 */
function PageLayoutRoot({ sidebar, draggable = false, className, children }: PageLayoutProps) {
  return (
    <div className={cx(styles.outer, className)}>
      <div className={cx(styles.scroll, draggable && styles.dragRegion)}>
        {sidebar ? (
          <div className={styles.containerGrid}>
            {sidebar}
            {children}
          </div>
        ) : (
          <div className={styles.containerSingle}>{children}</div>
        )}
      </div>
    </div>
  );
}

// ── Sidebar (bare slot) ───────────────────────────────────────────────────────

export interface PageSidebarProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * Adds an Electron window drag region so the sidebar is draggable.
   * Default: false.
   */
  draggable?: boolean;
}

/**
 * PageLayout.Sidebar — a bare sticky wrapper for custom sidebar content.
 *
 * Use this when you need full control over the sidebar contents.
 * For a standard nav-item list, prefer `PageLayout.SidebarMenu` instead.
 */
function Sidebar({ draggable = false, className, children, ...props }: PageSidebarProps) {
  return (
    <div
      className={cx(styles.sidebarWrapper, draggable && styles.dragRegion, className)}
      {...props}
    >
      {children}
    </div>
  );
}

// ── Content ───────────────────────────────────────────────────────────────────

export interface PageContentProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * Maximum width of the content column.
   * - `3xl` (768px) — Library-style
   * - `4xl` (896px) — Settings / Automations-style (default)
   */
  maxWidth?: ContentVariants['maxWidth'];
}

/**
 * PageLayout.Content — the centered content column inside a `PageLayout`.
 *
 * Applies horizontal padding and an optional max-width cap.
 */
function Content({ maxWidth = '4xl', className, ...props }: PageContentProps) {
  return <div className={cx(styles.content({ maxWidth }), className)} {...props} />;
}

export { PageLayoutRoot, Sidebar, Content };
